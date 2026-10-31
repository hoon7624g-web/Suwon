"""변화 감시 — 지난 실행 뒤 TourAPI에 새로 나오거나 바뀐 행사와 곧 낡을 자동 자료를 점검해 reports/watch/YYYY-MM-DD.md에
쓴다(보고만 한다 — 데이터 파일은 고치지 않는다). 도시 값(이름·지역 코드)은 모두 <data>/site.json에서 온다.

    TOURAPI_KEY=… python tools/watch_updates.py --data data/suwon        # 점검·보고서만
        --only festival,crowd (이것만)   --max-calls 150 (이번 실행의 호출 상한, 재시도 포함)
        --no-state (상태 파일을 바꾸지 않는다)   --today YYYY-MM-DD   --state data/watch/state.json   --report-dir reports/watch

점검
(festival) TourAPI searchFestival2(site.json tourapi.base_url, eventStartDate 오늘)를 site.json의 시·도
    (tourapi.ldong_regn_name, 없으면 region_admin)와 구·군(districts)으로 묻는다. 지역 코드는 코드나 설정에 적지 않고
    실행마다 ldongCode2 응답에서 이름으로 찾는다(pipeline.tourapi.resolve_ldong — tools/tourapi_harvest.py와 같은 방식).
    구·군마다 한 번씩(시 코드가 따로 있으면 그것도) 묻고 contentid로 합친다. 상태 파일의 contentid별 제목·기간과 비교해
    새 행사·바뀐 일정·목록에서 빠진 행사를 알리고, events.json에 그 contentid(contentid·tourapi_contentid)나 같은 해의
    같은 행사(이름)가 없으면 '사이트에 없음'.
(crowd) crowd.json(관광지 집중률 예측)의 마지막 날짜까지 남은 날, almanac.json의 해 자료 마지막 날짜. 파일이 없으면 '없음'.

공개 여부(status)·검수일·행사·장소의 사실 문장은 절대 바꾸지 않는다 — 새 행사는 보고서를 보고 사람이 넣는다.

키·호출
- 키는 환경 변수로만: TOURAPI_KEY(없으면 DATA_GO_KR_KEY). 저장소의 .env도 읽는다(pipeline.enrich.load_dotenv — 이미 있는
  환경 변수가 먼저). 보고서·출력에서는 키 문자열만 가리고 공급자 오류 메시지는 그대로 보인다.
- 이번 실행의 호출 상한 --max-calls(재시도도 센다)를 넘으면 그 점검을 멈추고 보고서에 적는다. 프록시·서버가 연결을 끊으면
  (연결 재설정·원격 끊김·시간 초과·5xx) 세 번까지 다시 부른다.
- 상태 파일(data/watch/state.json)은 점검을 끝까지 마친 항목만 옮긴다. 정기 실행이면 보고서와 함께 상태 파일도 남겨야
  다음 실행이 '새것'만 본다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.city import of as city_of  # noqa: E402
from pipeline.tourapi import (DEFAULT_MOBILE_APP, LDong, TourAPIError, parse_items,  # noqa: E402
                              resolve_ldong)
from tools.tourapi_details import event_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")
UA = "WebforAI watch (travel site; contact via site)"
DEFAULT_BASE_URL = "https://apis.data.go.kr/B551011/KorService2"

DEFAULT_MAX_CALLS = 150
CROWD_WARN_DAYS = 7
ALMANAC_MIN_DAYS = 60
SECTIONS = ("festival", "crowd")


# ---------------------------------------------------------------- network

class CallCapError(RuntimeError):
    """This run's call cap is used up."""


class FetchError(RuntimeError):
    """A provider or network failure after the retries; the message is the provider's own, the keys masked."""


class Budget:
    def __init__(self, max_calls: int):
        self.max, self.used = max_calls, 0

    def spend(self) -> None:
        if self.used >= self.max:
            raise CallCapError(f"호출 상한 {self.max}회")
        self.used += 1


RETRY_ERRORS = (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout, http.client.RemoteDisconnected,
                http.client.IncompleteRead)


def gateway_error(text: str) -> str | None:
    """'errMsg returnAuthMsg (code)' of a data.go.kr gateway refusal (XML or JSON), else None."""
    if "OpenAPI_ServiceResponse" not in text and "cmmMsgHeader" not in text:
        return None
    try:
        j = json.loads(text)
        h = (j.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader") or {}
    except ValueError:
        try:
            el = ET.fromstring(text).find(".//cmmMsgHeader")
            h = {c.tag: (c.text or "").strip() for c in el} if el is not None else {}
        except ET.ParseError:
            return text[:300]
    return f"{h.get('errMsg', '')} {h.get('returnAuthMsg', '')} ({h.get('returnReasonCode', '')})".strip()


def _urlopen(url: str, data: bytes | None, timeout: int) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class Net:
    """GET/POST with a shared call budget, retries on a dropped connection or a 5xx (each attempt counts), and every
    secret masked in the error text. `opener(url, data, timeout) -> bytes` is replaceable for tests."""

    def __init__(self, budget: Budget, secrets=(), opener=None, sleep=time.sleep, tries: int = 3):
        self.budget, self.opener, self.sleep, self.tries = budget, opener or _urlopen, sleep, tries
        self.secrets = [s for s in secrets if s]

    def mask(self, text) -> str:
        text = str(text)
        for s in self.secrets:
            for form in {s, urllib.parse.quote(s, safe=""), urllib.parse.quote_plus(s)}:
                text = text.replace(form, "«KEY»")
        return text

    def fetch(self, url: str, params: dict | None = None, form: dict | None = None, timeout: int = 60) -> str:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
        err = ""
        for i in range(self.tries):
            self.budget.spend()
            try:
                return self.opener(url, data, timeout).decode("utf-8-sig", "replace")
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", "replace")
                except Exception:   # noqa: BLE001
                    body = ""
                err = f"HTTP {e.code} {gateway_error(body) or body[:300]}".strip()
                if e.code < 500:
                    break
            except RETRY_ERRORS as e:
                err = f"{type(e).__name__}: {e}"
            if i < self.tries - 1:
                self.sleep(2 + 2 * i)
        raise FetchError(self.mask(err))


def squash(s) -> str:
    return " ".join(str(s or "").split())


# ---------------------------------------------------------------- TourAPI 행사

class WatchAPI:
    """The two KorService2 calls this tool needs (ldongCode2, searchFestival2) over Net — the same method names as
    pipeline.tourapi.TourAPI, so pipeline.tourapi.resolve_ldong finds the region codes by name."""

    def __init__(self, net: Net, key: str, site: dict):
        t = site.get("tourapi") if isinstance(site.get("tourapi"), dict) else {}
        self.net, self.key = net, key
        self.base_url = (t.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.op_suffix = str(t.get("op_suffix", "2"))
        self.mobile_app = t.get("mobile_app") or DEFAULT_MOBILE_APP

    def call(self, op: str, **params) -> list[dict]:
        q = {"serviceKey": self.key, "MobileOS": "ETC", "MobileApp": self.mobile_app, "_type": "json",
             **{k: v for k, v in params.items() if v not in (None, "")}}
        name = f"{op}{self.op_suffix}"
        text = self.net.fetch(f"{self.base_url}/{name}", q)
        try:
            return parse_items(json.loads(text), name)
        except ValueError:
            raise FetchError(self.net.mask(f"{name}: JSON이 아닌 응답 {gateway_error(text) or text[:300]}"))
        except TourAPIError as e:
            raise FetchError(self.net.mask(str(e)))

    def ldong_code(self, l_dong_regn_cd: str | None = None, rows: int = 100) -> list[dict]:
        return self.call("ldongCode", lDongRegnCd=l_dong_regn_cd, numOfRows=rows, pageNo=1)

    def search_festival(self, event_start_date: str, l_dong_regn_cd: str | None = None,
                        l_dong_signgu_cd: str | None = None, rows: int = 100, page: int = 1) -> list[dict]:
        return self.call("searchFestival", eventStartDate=event_start_date, lDongRegnCd=l_dong_regn_cd,
                         lDongSignguCd=l_dong_signgu_cd, numOfRows=rows, pageNo=page, arrange="A")


def signgu_codes(ldong: LDong) -> list[str | None]:
    """The 시군구 codes to ask: none for a whole 시·도, else every 구·군 and the parent 시 when it has its own code."""
    if ldong.whole_region:
        return [None]
    codes = [c for c, _ in ldong.signgu]
    if ldong.locality_cd and ldong.locality_cd not in codes:
        codes.append(ldong.locality_cd)
    return codes


def region_label(ldong: LDong, site: dict) -> str:
    names = [n for _, n in ldong.signgu]
    loc = squash(site.get("locality"))
    head = " ".join(w for w in (ldong.regn_name, loc if loc and loc != ldong.regn_name else "") if w)
    if ldong.whole_region:
        return f"{head} 전역"
    return f"{head} {'·'.join(names)}".strip() + (f" + {loc} 코드" if ldong.locality_cd else "")


def festivals(api: WatchAPI, ldong: LDong, start: str, rows: int = 100, max_pages: int = 5) -> list[dict]:
    """searchFestival2 from start for every code of signgu_codes, every page until a short one, deduplicated by
    contentid (the first kept)."""
    out, seen = [], set()
    for code in signgu_codes(ldong):
        for page in range(1, max_pages + 1):
            got = api.search_festival(start, ldong.regn_cd, code, rows=rows, page=page)
            new = [it for it in got if str(it.get("contentid")) not in seen]
            seen.update(str(it.get("contentid")) for it in new)
            out += new
            if len(got) < rows or not new:
                break
    return out


def festival_view(it: dict) -> dict:
    return {"title": squash(it.get("title")), "start": str(it.get("eventstartdate") or ""),
            "end": str(it.get("eventenddate") or ""), "modified": str(it.get("modifiedtime") or ""),
            "addr": squash(it.get("addr1")), "tel": squash(it.get("tel"))}


def event_ids_by_contentid(events: list[dict]) -> dict[str, str]:
    out = {}
    for e in events:
        for k in ("contentid", "tourapi_contentid"):
            if e.get(k):
                out.setdefault(str(e[k]), e.get("id", ""))
    return out


def same_series(events: list[dict], title: str, start: str) -> str:
    """An events.json record of the same series (event_key) and year, else ''."""
    k, year = event_key(title), start[:4]
    for e in events:
        names = [e.get("name"), e.get("series")]
        if any(n and event_key(n) == k for n in names) and (e.get("start_date") or "")[:4] == year:
            return e.get("id", "")
    return ""


def compare_festivals(items: list[dict], old: dict, events: list[dict], today: str) -> dict:
    by_cid = event_ids_by_contentid(events)
    now = {str(it["contentid"]): festival_view(it) for it in items if it.get("contentid")}
    new, changed, gone = [], [], []
    for cid, v in now.items():
        site = by_cid.get(cid) or same_series(events, v["title"], v["start"])
        row = {"contentid": cid, **v, "site": site}
        if cid not in old:
            new.append(row)
        else:
            diff = {f: (old[cid].get(f), v[f]) for f in ("title", "start", "end") if old[cid].get(f) != v[f]}
            if diff:
                changed.append({**row, "diff": diff})
    ymd = today.replace("-", "")
    for cid, v in old.items():
        if cid not in now and (v.get("end") or "") >= ymd:
            gone.append({"contentid": cid, **v, "site": by_cid.get(cid, "")})
    missing = [{"contentid": cid, **v} for cid, v in now.items()
               if not (by_cid.get(cid) or same_series(events, v["title"], v["start"]))]
    return {"items": now, "new": new, "changed": changed, "gone": gone, "missing": missing}


# ---------------------------------------------------------------- crowd · almanac

def crowd_status(data: Path, today: dt.date) -> dict:
    f = data / "crowd.json"
    if not f.is_file():
        return {"exists": False}
    c = json.loads(f.read_text("utf-8"))
    end = (c.get("period") or {}).get("end") or ""
    left = (dt.date.fromisoformat(end) - today).days if end else None
    return {"exists": True, "generated": c.get("generated") or "", "end": end, "days_left": left,
            "places": len(c.get("places") or {})}


def almanac_status(data: Path, today: dt.date) -> dict:
    f = data / "almanac.json"
    if not f.is_file():
        return {"exists": False, "sun_days_left": None}
    a = json.loads(f.read_text("utf-8"))
    days = sorted(a.get("sun") or {})
    last = days[-1] if days else ""
    return {"exists": True, "sun_last": last,
            "sun_days_left": (dt.date.fromisoformat(last) - today).days if last else None}


# ---------------------------------------------------------------- report

def md_cell(s) -> str:
    return squash(s).replace("|", "\\|")


def report(today: str, res: dict, calls: tuple[int, int], brand: str = "") -> str:
    L = [f"# {brand + ' ' if brand else ''}변화 감시 {today}", "",
         f"tools/watch_updates.py · 호출 {calls[0]}회(상한 {calls[1]}) · 데이터 파일은 고치지 않음", ""]
    todo = []
    f = res.get("festival")
    if f and f.get("error"):
        todo.append(f"TourAPI 행사 점검 못 함 — {f['error']}")
    elif f:
        todo += [f"TourAPI 행사 {x['contentid']} {x['title']}" for x in f["missing"]]
        todo += [f"TourAPI 일정 바뀜 {x['contentid']} {x['title']}" for x in f["changed"]]
    L += ["## 사람이 볼 것", ""]
    L += [f"- {t}" for t in todo] or ["- 없음"]
    L.append("")
    if f:
        L += [f"## TourAPI 행사(searchFestival2{', ' + f['region'] if f.get('region') else ''})", ""]
        if f.get("error"):
            L += [f"받지 못함 — {f['error']}", ""]
        else:
            L += [(f"목록 {len(f['items'])}건 · 새로 보임 {len(f['new'])} · 일정 바뀜 {len(f['changed'])} · 목록에서 빠짐 "
                   f"{len(f['gone'])} · events.json에 없음 {len(f['missing'])}"), ""]
            rows = ([("새로 보임", x) for x in f["new"]] + [("일정 바뀜", x) for x in f["changed"]]
                    + [("목록에서 빠짐", x) for x in f["gone"]])
            if rows:
                L += ["| 구분 | contentid | 행사 | 기간 | 바뀐 값 | 사이트 |", "|---|---|---|---|---|---|"]
                for kind, x in rows:
                    diff = "; ".join(f"{k}: {a} → {b}" for k, (a, b) in (x.get("diff") or {}).items())
                    L.append(f"| {kind} | {x['contentid']} | {md_cell(x['title'])} | {x['start']}~{x['end']} | "
                             f"{md_cell(diff)} | {x.get('site') or '없음'} |")
                L.append("")
    c, a = res.get("crowd"), res.get("almanac")
    if c is not None:
        L += ["## 자동 자료의 남은 기간", ""]
        if c.get("exists"):
            warn = " — 곧 끝남, 다시 받기" if c["days_left"] is not None and c["days_left"] <= CROWD_WARN_DAYS else ""
            L.append(f"- crowd.json: {c['generated']}에 받은 예측, 마지막 날 {c['end']}(남은 {c['days_left']}일){warn}")
        else:
            L.append("- crowd.json: 없음")
        if a and a.get("exists"):
            warn = " — 다시 받기 권장" if a["sun_days_left"] is not None and a["sun_days_left"] < ALMANAC_MIN_DAYS else ""
            L.append(f"- almanac.json: 해 자료 마지막 날 {a['sun_last'] or '없음'}(남은 {a['sun_days_left']}일){warn}")
        else:
            L.append("- almanac.json: 없음")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- main

def load_json(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.is_file() else default


def check_festival(net: Net, key: str, site: dict, state: dict, events: list[dict], today: dt.date) -> dict:
    api = WatchAPI(net, key, site)
    try:
        ldong = resolve_ldong(api, city_of(site))
    except (FetchError, CallCapError, TourAPIError) as e:
        return {"error": f"지역 코드(ldongCode2) — {net.mask(e)}"}
    region = region_label(ldong, site)
    try:
        items = festivals(api, ldong, today.strftime("%Y%m%d"))
    except (FetchError, CallCapError) as e:
        return {"error": str(e), "region": region}
    return {**compare_festivals(items, state.get("items") or {}, events, today.isoformat()), "region": region}


def run(data: Path, state_path: Path, report_dir: Path, today: dt.date, only: set[str], max_calls: int,
        keep_state: bool, opener=None, sleep=time.sleep) -> dict:
    from pipeline.enrich import load_dotenv
    load_dotenv(ROOT / ".env")
    key = os.environ.get("TOURAPI_KEY", "").strip() or os.environ.get("DATA_GO_KR_KEY", "").strip()
    key = urllib.parse.unquote(key) if "%" in key else key
    budget = Budget(max_calls)
    net = Net(budget, (key,), opener=opener, sleep=sleep)
    site = load_json(data / "site.json", {})
    state = load_json(state_path, {})
    events = load_json(data / "events.json", [])
    iso = today.isoformat()
    res: dict = {}
    if "festival" in only:
        if not key:
            res["festival"] = {"error": "키 없음 — 환경 변수 TOURAPI_KEY(또는 DATA_GO_KR_KEY)"}
        else:
            res["festival"] = check_festival(net, key, site, state.get("festival") or {}, events, today)
            if not res["festival"].get("error"):
                state["festival"] = {"items": res["festival"]["items"], "checked_at": iso}
    if "crowd" in only:
        res["crowd"], res["almanac"] = crowd_status(data, today), almanac_status(data, today)
    text = report(iso, res, (budget.used, budget.max), squash(site.get("brand")))
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"{iso}.md"
    out.write_text(net.mask(text), "utf-8")
    if keep_state:
        state["_about"] = ("tools/watch_updates.py의 지난 점검 상태 — festival.items(TourAPI 행사 contentid별 제목·기간), "
                           "festival.checked_at(마지막으로 끝까지 본 날). 사람이 고치지 않는다.")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(dict(sorted(state.items())), ensure_ascii=False, indent=1) + "\n", "utf-8")
    res["report"] = str(out)
    res["calls"] = budget.used
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data/suwon"))
    ap.add_argument("--state", type=Path, default=Path("data/watch/state.json"))
    ap.add_argument("--report-dir", type=Path, default=Path("reports/watch"))
    ap.add_argument("--only", help="쉼표로: " + ",".join(SECTIONS))
    ap.add_argument("--today", help="오늘 YYYY-MM-DD(기본: 한국 시각)")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--no-state", action="store_true", help="상태 파일을 바꾸지 않는다")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else set(SECTIONS)
    if only - set(SECTIONS):
        ap.error(f"--only: {','.join(sorted(only - set(SECTIONS)))}")
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(KST).date()
    res = run(a.data, a.state, a.report_dir, today, only, a.max_calls, not a.no_state)
    f = res.get("festival")
    print(f"보고서: {res['report']} (호출 {res['calls']}회)")
    if f:
        print("  TourAPI 행사: " + (f["error"] if f.get("error") else
                                   f"{len(f['items'])}건, 새 {len(f['new'])}, 바뀜 {len(f['changed'])}, 사이트에 없음 "
                                   f"{len(f['missing'])}"))
    c = res.get("crowd")
    if c is not None:
        print("  crowd.json " + (f"남은 {c['days_left']}일" if c.get("exists") else "없음")
              + " · almanac.json " + ("있음" if (res.get("almanac") or {}).get("exists") else "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
