"""군산각 변화 감시 — 지난 실행 뒤 새로 나온 공식 정보와 곧 낡을 자동 자료를 점검해 reports/watch/YYYY-MM-DD.md에
쓴다(운영자 요청 2026-10-31 '군산 불꽃축제 외에도 놓친 정보 없는지 확인하고, 앞으로 계속 자동으로 트래킹').

    DATA_GO_KR_KEY=… TOURAPI_KEY=… python tools/watch_updates.py --data data/gunsan               # 점검·보고서만
    DATA_GO_KR_KEY=… TOURAPI_KEY=… python tools/watch_updates.py --data data/gunsan --apply-safe  # + 자동 자료 재수집
        --only press,festival,license,tide,crowd  (이것만)   --since YYYY-MM-DD (상태 파일이 없을 때 시작일, 기본 14일 전)
        --max-calls 150 (이번 실행의 호출 상한, 재시도 포함)   --max-press-pages 10   --max-details 30
        --no-state (상태 파일을 바꾸지 않는다)   --today YYYY-MM-DD   --state data/watch/state.json   --report-dir reports/watch

점검(기본은 보고만 — 데이터 파일은 고치지 않는다)
(a) press: 군산시 보도자료(eminwon '보도 및 대응자료', 공개분)를 최신부터 100건씩 받아 상태 파일의 마지막 번호
    (news_epct_no)까지 내려간다. 제목에 여행 낱말(STRONG_WORDS, 또는 SKIP_WORDS 없이 WEAK_WORDS)이 있는 글은 상세를 받아 전체 제목·부서·날짜·본문에 나온
    날짜를 보이고, events.json(source_news_epct_no·also_sources·source_name의 '보도자료 번호')에 이미 쓴 번호면 '반영됨'.
    끝까지 못 내려가면(호출 상한·오류) 마지막 번호를 옮기지 않는다 — 다음 실행이 같은 범위를 다시 본다.
(b) festival: TourAPI searchFestival2(KorService2, lDongRegnCd 52 · lDongSignguCd 130, eventStartDate 오늘)를 상태 파일의
    contentid별 제목·기간·modifiedtime과 비교해 새 행사·바뀐 일정·목록에서 빠진 행사를 알리고, events.json에 그 contentid
    (contentid·tourapi_contentid)가 없으면 '사이트에 없음'.
(c) license: 행정안전부 인허가 12종(군산시)에서 지난 점검일 뒤 바뀐 행만(cond[DAT_UPDT_PNT::GTE]) 받아
    data/raw/<지역>/licenses/ 원자료에 덮어 tools/mois_licenses_gunsan.py의 매칭(build)을 다시 돌리고, 공개 장소의 상태가
    licenses.json의 '영업'에서 '휴업'·'폐업 확인'으로 바뀐 곳을 알린다. 알린 곳은 상태 파일에 남아 licenses.json이 바뀔
    때까지 다시 보인다. licenses.json·places.json은 고치지 않는다(폐업 반영은 사람이 `mois_licenses_gunsan.py fetch` 뒤 결정).
(d) tide: 국립해양조사원 조석예보(고·저조) 군산(DT_0018) 오늘 값을 한 번 불러 기관 서버가 살아났는지 본다.
(e) crowd·almanac: crowd.json(관광지 집중률 30일 예측)의 마지막 날짜까지 남은 날, almanac.json의 해 자료 마지막 날짜와
    조석 유무.

--apply-safe는 사람 판단이 필요 없는 자동 자료만 다시 받는다: crowd.json(오늘 받은 것이 아니면 tools/tourapi_related.py
crowd --apply), almanac.json(조석 서버가 살아났는데 조석이 없거나, 해 자료가 ALMANAC_MIN_DAYS일보다 적게 남았을 때
tools/almanac_gunsan.py --apply; 조석이 죽어 있으면 --only sun). 공개 여부(status)·검수일·행사·장소의 사실 문장은 절대
바꾸지 않는다 — 보도자료·TourAPI 행사·폐업은 보고서를 보고 사람이 넣는다.

키·호출
- 키는 환경 변수로만: DATA_GO_KR_KEY(인허가·조석·집중률), TOURAPI_KEY(KorService2 searchFestival2; 없으면 DATA_GO_KR_KEY).
  저장소의 .env도 읽는다(pipeline.enrich.load_dotenv — 이미 있는 환경 변수가 먼저). 보고서·출력에서는 키 문자열만 가리고
  공급자 오류 메시지는 그대로 보인다.
- 이번 실행의 호출 상한 --max-calls(재시도도 센다)를 넘으면 그 점검을 멈추고 보고서에 적는다. 프록시·서버가 연결을 끊으면
  (연결 재설정·원격 끊김·시간 초과·5xx) 세 번까지 다시 부른다. --apply-safe가 부르는 두 도구는 저마다의 상한을 쓴다.
- 상태 파일(data/watch/state.json)은 점검을 끝까지 마친 항목만 옮긴다. 정기 실행이면 보고서와 함께 상태 파일도 남겨야
  다음 실행이 '새것'만 본다.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import html
import http.client
import io
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tourapi import TourAPIError, parse_items  # noqa: E402
from tools import almanac_gunsan as almanac  # noqa: E402
from tools import mois_licenses_gunsan as mois  # noqa: E402
from tools.tourapi_details import event_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")
UA = "WebforAI watch (gunsan travel site; contact via site)"

EMINWON_ACTION = "https://eminwon.gunsan.go.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
EMINWON_LIST = "https://eminwon.gunsan.go.kr/emwp/jsp/ofr/OfrNewsEpctLSub.jsp?news_epct_yn=1,2"   # what events.json cites
PRESS_FORM = {"jndinm": "OfrBcAdvNewsEJB", "context": "NTIS", "subCheck": "Y", "news_epct_yn": "1,2",
              "data_open_yn": "1", "countYn": "Y"}
PAGE_SIZE = 100   # ofr_pageSize: 100 answers 100 rows (2026-10-31)

FESTIVAL_API = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
REGION = {"lDongRegnCd": "52", "lDongSignguCd": "130"}   # 전북특별자치도 군산시 (법정동 코드)

DEFAULT_MAX_CALLS = 150
DEFAULT_SINCE_DAYS = 14
CROWD_WARN_DAYS = 7
ALMANAC_MIN_DAYS = 60
SECTIONS = ("press", "festival", "license", "tide", "crowd")

# Title words (2026-10-31, tried on the 648 press releases since 2026-07-01). A title with a STRONG word is kept; one with
# only WEAK words is kept unless it also has a SKIP word (a donation, an appointment, a meeting …). Broad on purpose:
# the report is read by a person, and an unrelated hit costs one line.
STRONG_WORDS = (
    "축제", "페스티벌", "페스타", "공연", "콘서트", "음악회", "연주회", "버스킹", "전시", "展", "박람회", "야시장", "장터",
    "마켓", "개장", "개관", "재개관", "개통", "휴관", "휴장", "폐장", "폐관", "운영시간", "관람", "입장료", "시티투어", "투어",
    "탐험", "여객선", "도선", "운항", "결항", "항로", "섬잇길", "야행", "미디어아트", "불꽃", "해넘이", "해맞이", "마라톤",
    "관광", "여행", "체험", "캠핑", "야영장", "해수욕장", "박물관", "미술관", "예술의전당", "오션팔레트", "시간여행",
    "군산항1981", "노선", "셔틀", "통제", "참가자 모집", "교향악단", "합창단", "예술단", "연극", "뮤지컬", "발레",
)
WEAK_WORDS = (
    "행사", "개최", "개막", "대회", "놀이", "섬", "고군산", "선유도", "장자도", "신시도", "무녀도", "어청도", "개야도", "연도",
    "말도", "방축도", "관리도", "비응", "새만금", "근대", "공원", "호수", "구불길", "둘레길", "걷기", "등산", "숲", "노을",
    "일출", "빛", "크리스마스", "레트로", "영화", "상영", "북페어", "도서관", "짬뽕", "맥주", "빵", "먹거리", "맛집", "음식",
    "벚꽃", "꽃", "단풍", "국화", "철새", "버스", "주차", "주정차", "숙박", "호텔", "레일바이크", "짚라인", "유람선", "낚시",
    "갯벌", "명소", "무료", "요금", "임시", "개방", "스탬프", "클라이밍",
)
SKIP_WORDS = (
    "임명", "취임", "기탁", "성금", "후원", "장학", "수상", "표창", "간담회", "협약", "회의", "교육", "설명회", "예산", "착한가게",
    "나눔", "위문", "봉사", "캠페인", "지원사업", "채용", "세무", "체납", "보조금", "예방",
)


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
                err = f"HTTP {e.code} {almanac.gateway_error(body) or body[:300]}".strip()
                if e.code < 500:
                    break
            except RETRY_ERRORS as e:
                err = f"{type(e).__name__}: {e}"
            if i < self.tries - 1:
                self.sleep(2 + 2 * i)
        raise FetchError(self.mask(err))


# ---------------------------------------------------------------- (a) 군산시 보도자료

def squash(s) -> str:
    return " ".join(str(s or "").split())


def strip_tags(s: str) -> str:
    s = re.sub(r"(?i)<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\xa0", " ")


def parse_press_list(text: str) -> tuple[int, list[dict]]:
    """(total count, rows) of one list page: {no (news_epct_no), seq, title (may end in '...'), dept, date, views}."""
    m = re.search(r"전체게시물\s*:\s*([\d,]+)", text)
    total = int(m.group(1).replace(",", "")) if m else 0
    rows = []
    for chunk in re.split(r"(?i)<tr\b", text):
        no = re.search(r"searchDetail\('(\d+)'\)", chunk)
        if not no:
            continue
        cells = [squash(strip_tags(c)) for c in re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", chunk)]
        if len(cells) < 4 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[3]):
            continue
        rows.append({"no": no.group(1), "seq": cells[0], "title": cells[1], "dept": cells[2], "date": cells[3],
                     "views": cells[4] if len(cells) > 4 else ""})
    return total, rows


def parse_press_detail(text: str, no: str) -> dict:
    """{no, title, dept, date, body, attachments} of one press release page (values as written; body as plain text)."""
    def cell(label: str) -> str:
        m = re.search(rf"(?is)>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>", text)
        return squash(strip_tags(m.group(1))) if m else ""
    m = re.search(r"(?is)<td\s+style='word-break:break-all;'[^>]*>(.*?)</td>", text)
    body = strip_tags(m.group(1)) if m else ""
    body = "\n".join(squash(line) for line in body.split("\n")).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    files = re.findall(r"goDownLoad\('([^']*)'", text)
    return {"no": str(no), "title": cell("제목"), "dept": cell("작성부서"), "date": cell("등록일자"), "body": body,
            "attachments": files}


def press_list(net: Net, page: int, size: int = PAGE_SIZE, query: str = "") -> tuple[int, list[dict]]:
    form = {**PRESS_FORM, "method": "selectListOfrNews", "methodnm": "selectListOfrNewsHomepage",
            "ofr_pageSize": str(size), "pageIndex": str(page), "data_sj": query}
    return parse_press_list(net.fetch(EMINWON_ACTION, form=form))


def press_detail(net: Net, no: str) -> dict:
    form = {**PRESS_FORM, "method": "selectOfrNews", "methodnm": "selectOfrNewsMgt", "news_epct_no": str(no)}
    return parse_press_detail(net.fetch(EMINWON_ACTION, form=form), no)


def new_press(net: Net, last_no: int | None, since: str, max_pages: int = 10) -> tuple[list[dict], bool, str]:
    """Rows newer than last_no (or, without one, dated on or after since), newest first: (rows, complete, error)."""
    out: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        try:
            _, rows = press_list(net, page)
        except (FetchError, CallCapError) as e:
            return list(out.values()), False, f"{page}쪽: {e}"
        if not rows:
            return list(out.values()), True, ""
        done = False
        for r in rows:
            if (last_no is not None and int(r["no"]) <= last_no) or (last_no is None and r["date"] < since):
                done = True
                continue
            out[r["no"]] = r
        if done:
            return list(out.values()), True, ""
    return list(out.values()), False, f"{max_pages}쪽까지 받았지만 지난번 번호에 닿지 못함(--max-press-pages)"


def travel_words(title: str) -> list[str]:
    """The travel words of a title ([] when it is not worth a look) — see STRONG_WORDS."""
    title = (title or "").replace("문화체육관광부", "")   # the ministry's name is not a travel word
    strong = [w for w in STRONG_WORDS if w in title]
    weak = [w for w in WEAK_WORDS if w in title]
    if strong:
        return strong + weak
    return weak if weak and not any(w in title for w in SKIP_WORDS) else []


def body_dates(body: str) -> list[str]:
    """Dates written in the body ('11월 14일(토)', '2026. 11. 14.(토)') — shown to the reader, nothing inferred."""
    rx = (r"(?:20\d\d\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일(?:\s*\([월화수목금토일]\))?"
          r"|20\d\d\.\s*\d{1,2}\.\s*\d{1,2}\.(?:\s*\([월화수목금토일]\))?")
    seen: list[str] = []
    for m in re.finditer(rx, body or ""):
        s = squash(m.group(0))
        if s not in seen:
            seen.append(s)
    return seen[:8]


def known_press_numbers(events: list[dict]) -> dict[str, str]:
    """{news_epct_no: event id} of every press release events.json already cites."""
    out = {}
    for e in events:
        nos = [e.get("source_news_epct_no")] + [s.get("news_epct_no") for s in e.get("also_sources") or []]
        names = [e.get("source_name")] + [s.get("name") for s in e.get("also_sources") or []]
        nos += [m for n in names for m in re.findall(r"보도자료 번호 (\d+)", n or "")]
        for n in nos:
            if n:
                out.setdefault(str(n), e.get("id", ""))
    return out


def check_press(net: Net, state: dict, events: list[dict], since: str, max_pages: int, max_details: int) -> dict:
    last = state.get("last_no")
    rows, complete, err = new_press(net, int(last) if last else None, since, max_pages)
    known = known_press_numbers(events)
    hits, failed, tried, capped = [], [], 0, ""
    for r in sorted(rows, key=lambda r: -int(r["no"])):
        words = travel_words(r["title"])
        if not words:
            continue
        item = {**r, "words": words, "in_events": known.get(r["no"], "")}
        if tried < max_details and not capped:
            tried += 1
            try:
                d = press_detail(net, r["no"])
                item.update(title=d["title"] or r["title"], body=d["body"], dates=body_dates(d["body"]),
                            attachments=d["attachments"])
            except FetchError as e:
                failed.append(f"{r['no']}: {e}")
            except CallCapError as e:
                capped = f"{e} — 상세는 {r['no']}부터 받지 못함"
        hits.append(item)
    newest = max((int(r["no"]) for r in rows), default=int(last) if last else None)
    details_err = "; ".join(([capped] if capped else []) + [f"상세 {f}" for f in failed])
    return {"rows": len(rows), "hits": hits, "complete": complete, "error": err, "details_error": details_err,
            "last_no": newest if complete else (int(last) if last else None), "prev_last_no": last}


# ---------------------------------------------------------------- (b) TourAPI 행사

def festivals(net: Net, key: str, start: str, end: str | None = None, rows: int = 100, max_pages: int = 5) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        params = {"serviceKey": key, "MobileOS": "ETC", "MobileApp": "WebforAI", "_type": "json",
                  "eventStartDate": start, "eventEndDate": end, **REGION, "numOfRows": rows, "pageNo": page,
                  "arrange": "A"}
        text = net.fetch(FESTIVAL_API, {k: v for k, v in params.items() if v not in (None, "")})
        try:
            items = parse_items(json.loads(text), "searchFestival2")
        except ValueError:
            raise FetchError(net.mask(f"searchFestival2: JSON이 아닌 응답 {almanac.gateway_error(text) or text[:300]}"))
        except TourAPIError as e:
            raise FetchError(net.mask(str(e)))
        out += items
        if len(items) < rows:
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


# ---------------------------------------------------------------- (c) 행정안전부 인허가 — 공개 장소의 새 폐업·휴업

def license_updates(net: Net, key: str, since: str, services=None, rows: int = 100, max_pages: int = 20) -> list[dict]:
    """Licence rows of 군산시 whose DAT_UPDT_PNT is on or after since (YYYY-MM-DD), every service, prepped for matching."""
    out = []
    for svc in services or mois.SVC:
        page = 1
        while page <= max_pages:
            q = {"serviceKey": key, "pageNo": page, "numOfRows": rows, "returnType": "json",
                 "cond[OPN_ATMY_GRP_CD::EQ]": mois.GROUP, "cond[DAT_UPDT_PNT::GTE]": since.replace("-", "")}
            text = net.fetch(mois.BASE.format(svc=svc), q)
            try:
                resp = json.loads(text)["response"]
            except (ValueError, KeyError):
                raise FetchError(net.mask(f"{svc}: {almanac.gateway_error(text) or text[:300]}"))
            head = resp.get("header") or {}
            if str(head.get("resultCode", "0")) not in ("0", "00"):
                raise FetchError(net.mask(f"{svc}: resultCode {head.get('resultCode')} {head.get('resultMsg')}"))
            body = resp.get("body") or {}
            items = (body.get("items") or {}).get("item") or [] if isinstance(body.get("items"), dict) else []
            if isinstance(items, dict):
                items = [items]
            out += [mois.prep({k: "" if v is None else str(v) for k, v in it.items()}, svc) for it in items]
            if len(items) < rows or page * rows >= int(body.get("totalCount") or 0):
                break
            page += 1
    return out


def license_changes(places: list[dict], base_rows: list[dict], updated: list[dict], licenses: dict,
                    today: str) -> list[dict]:
    """Published places whose licence status was '영업' in licenses.json and is '휴업' or '폐업 확인' once the updated rows
    replace the old ones (by MNG_NO). Only places an updated row could touch are matched again."""
    if not updated:
        return []
    by_no = {r["MNG_NO"]: r for r in base_rows}
    for r in updated:
        by_no[r["MNG_NO"]] = r
    rows = list(by_no.values())
    old = licenses.get("places") or {}
    upd_nos = {r["MNG_NO"] for r in updated}
    upd_names = {n for r in updated for n in r["_names"]}
    upd_keys = {k for r in updated for k in r["_keys"]}
    touched = []
    for p in places:
        if p.get("status") != "published" or not mois.place_group(p):
            continue
        if ((old.get(p["id"]) or {}).get("mng_no") in upd_nos or mois.place_names(p) & upd_names
                or mois.addr_keys((p.get("facts") or {}).get("address")) & upd_keys):
            touched.append(p)
    if not touched:
        return []
    result = mois.build(touched, rows, [], {}, None, today)
    out = []
    for p in touched:
        was = (old.get(p["id"]) or {}).get("status")
        now = result["places"].get(p["id"])
        if not now or now["status"] == "영업" or was == now["status"]:
            continue
        out.append({"id": p["id"], "name": p["name"], "was": was or "(licenses.json에 없음)", "now": now["status"],
                    "license_name": now["name"], "kind": now["kind"], "closed_at": now.get("closed_at") or "",
                    "mng_no": now["mng_no"], "road_addr": now["road_addr"], "match": now["match"]})
    return out


# ---------------------------------------------------------------- (d) 조석예보 · (e) crowd · almanac

def tide_alive(net: Net, key: str, day: dt.date, obs: str = "DT_0018") -> tuple[bool, str]:
    """One getTideFcstHghLwApi call (today, 군산): (answered with values, message)."""
    try:
        text = net.fetch(almanac.TIDE["api"], {"serviceKey": key, "obsCode": obs, "reqDate": day.strftime("%Y%m%d"),
                                               "type": "xml", "numOfRows": 10, "pageNo": 1}, timeout=30)
    except (FetchError, CallCapError) as e:
        return False, str(e)
    gw = almanac.gateway_error(text)
    if gw:
        return False, net.mask(f"포털 게이트웨이: {gw}")
    try:
        code, msg, items = almanac.xml_items(text)
    except Exception as e:   # noqa: BLE001 — not XML: show the start of what came back
        return False, net.mask(f"{type(e).__name__}: {text[:200]}")
    if code in ("00", "0") and items:
        return True, f"{code} {msg} — {len(items)}건(예: {items[0].get('predcDt', '')} {items[0].get('predcTdlvVl', '')}cm)"
    return False, net.mask(f"{code} {msg} (항목 {len(items)})")


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
        return {"exists": False, "has_tide": False, "sun_days_left": None}
    a = json.loads(f.read_text("utf-8"))
    days = sorted(a.get("sun") or {})
    last = days[-1] if days else ""
    return {"exists": True, "sun_last": last, "has_tide": bool(a.get("tide")),
            "sun_days_left": (dt.date.fromisoformat(last) - today).days if last else None}


# ---------------------------------------------------------------- --apply-safe

def run_tool(main, argv: list[str], net: Net) -> tuple[int, str]:
    """Run another tool's main(argv), its output captured with the keys masked."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = main(argv) or 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if not isinstance(e.code, int) and e.code:
                print(e.code)
        except Exception as e:   # noqa: BLE001 — reported, never hides the provider's message
            code = 1
            print(f"{type(e).__name__}: {e}")
    return code, net.mask(buf.getvalue()).strip()


def apply_safe(data: Path, crowd: dict, alm: dict, tide_ok: bool | None, today: dt.date, net: Net) -> list[dict]:
    from tools import tourapi_related
    done = []
    if crowd.get("exists") is False or (crowd.get("generated") or "") < today.isoformat():
        code, out = run_tool(tourapi_related.main, ["--data", str(data), "crowd", "--apply"], net)
        done.append({"what": "crowd.json 재수집(tools/tourapi_related.py crowd --apply)", "code": code, "out": out})
    want_tide = bool(tide_ok) and not alm.get("has_tide")
    short = alm.get("sun_days_left") is None or alm["sun_days_left"] < ALMANAC_MIN_DAYS
    if want_tide or short:
        argv = ["--data", str(data), "--apply"] + ([] if tide_ok else ["--only", "sun"])
        code, out = run_tool(almanac.main, argv, net)
        done.append({"what": f"almanac.json 재수집(tools/almanac_gunsan.py {' '.join(argv[2:])})", "code": code,
                     "out": out})
    return done


# ---------------------------------------------------------------- report

def md_cell(s) -> str:
    return squash(s).replace("|", "\\|")


def report(today: str, res: dict, calls: tuple[int, int]) -> str:
    L = [f"# 군산각 변화 감시 {today}", "",
         f"tools/watch_updates.py · 호출 {calls[0]}회(상한 {calls[1]}) · 데이터 파일은 고치지 않음"
         + (" · --apply-safe" if res.get("applied") is not None else ""), ""]
    todo = []
    p = res.get("press")
    if p:
        todo += [f"보도자료 {h['no']} {h['title']}" for h in p["hits"] if not h["in_events"]]
    f = res.get("festival")
    if f and not f.get("error"):
        todo += [f"TourAPI 행사 {x['contentid']} {x['title']}" for x in f["missing"]]
        todo += [f"TourAPI 일정 바뀜 {x['contentid']} {x['title']}" for x in f["changed"]]
    lic = res.get("license")
    if lic and not lic.get("error"):
        todo += [f"인허가 {x['now']}: {x['name']}" for x in lic["changes"] + lic["still"]]
    L += ["## 사람이 볼 것", ""]
    L += [f"- {t}" for t in todo] or ["- 없음"]
    L.append("")
    if p:
        L += ["## (a) 군산시 보도자료", "",
              (f"새 글 {p['rows']}건(지난 번호 {p['prev_last_no'] or '없음'} → {p['last_no'] or '-'}), 여행 낱말이 있는 글 "
               f"{len(p['hits'])}건. 목록: {EMINWON_LIST}"), ""]
        if p["error"]:
            L += [f"주의: 끝까지 받지 못함 — {p['error']}. 마지막 번호를 옮기지 않았다.", ""]
        if p["details_error"]:
            L += [f"주의: {p['details_error']}", ""]
        if p["hits"]:
            L += ["| 번호 | 날짜 | 부서 | 제목 | 본문의 날짜 | 사이트 |", "|---|---|---|---|---|---|"]
            for h in sorted(p["hits"], key=lambda h: -int(h["no"])):
                L.append(f"| {h['no']} | {h['date']} | {md_cell(h['dept'])} | {md_cell(h['title'])} | "
                         f"{md_cell(', '.join(h.get('dates') or []))} | {h['in_events'] or '없음'} |")
            L.append("")
    if f:
        L += ["## (b) TourAPI 행사(searchFestival2, 군산)", ""]
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
    if lic:
        L += ["## (c) 행정안전부 인허가 — 공개 장소", ""]
        if lic.get("error"):
            L += [f"받지 못함 — {lic['error']}", ""]
        else:
            L += [f"{lic['since']} 뒤 바뀐 인허가 행 {lic['updated']}건. 공개 장소 상태 바뀜 {len(lic['changes'])}곳"
                  + (f", 이전에 알렸고 licenses.json에 아직 반영 안 됨 {len(lic['still'])}곳" if lic["still"] else ""), ""]
            rows = [("새로", x) for x in lic["changes"]] + [("이전 알림", x) for x in lic["still"]]
            if rows:
                L += ["| 구분 | 장소 id | 장소 | licenses.json → 지금 | 인허가 상호 | 폐업일 | 관리번호 |",
                      "|---|---|---|---|---|---|---|"]
                for kind, x in rows:
                    L.append(f"| {kind} | {x['id']} | {md_cell(x['name'])} | {x['was']} → {x['now']} | "
                             f"{md_cell(x['license_name'])} | {x.get('closed_at') or ''} | {x['mng_no']} |")
                L += ["", ("반영: `python tools/mois_licenses_gunsan.py --data data/gunsan fetch` → `--apply` 뒤 공개 여부는 "
                           "사람이 정한다."), ""]
    t = res.get("tide")
    if t:
        L += ["## (d) 조석예보 서버", "", f"{'응답함' if t['ok'] else '응답 없음'} — {md_cell(t['msg'])}", ""]
    c, a = res.get("crowd"), res.get("almanac")
    if c is not None:
        L += ["## (e) 자동 자료의 남은 기간", ""]
        if c.get("exists"):
            warn = " — 곧 끝남, 다시 받기(`--apply-safe` 또는 tools/tourapi_related.py crowd --apply)" \
                if c["days_left"] is not None and c["days_left"] <= CROWD_WARN_DAYS else ""
            L.append(f"- crowd.json: {c['generated']}에 받은 예측, 마지막 날 {c['end']}(남은 {c['days_left']}일){warn}")
        else:
            L.append("- crowd.json: 없음")
        if a and a.get("exists"):
            warn = " — 다시 받기 권장" if a["sun_days_left"] is not None and a["sun_days_left"] < ALMANAC_MIN_DAYS else ""
            L.append(f"- almanac.json: 해 자료 마지막 날 {a['sun_last']}(남은 {a['sun_days_left']}일){warn}, 조석 "
                     f"{'있음' if a['has_tide'] else '없음'}")
        L.append("")
    if res.get("applied") is not None:
        L += ["## --apply-safe", ""]
        if not res["applied"]:
            L += ["다시 받을 것 없음", ""]
        for d in res["applied"]:
            out = d["out"].splitlines()
            L += [f"- {d['what']}: 종료 코드 {d['code']}", "", "```", *out[-15:], "```", ""]
    if p and p["hits"]:
        L += ["## 부록: 보도자료 본문 첫머리(확인용 — 사이트에 옮기지 않는다)", ""]
        for h in sorted(p["hits"], key=lambda h: -int(h["no"])):
            if h.get("body"):
                L += [f"- {h['no']} {md_cell(h['title'])}: {md_cell(h['body'][:240])}…"]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- main

def load_json(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.is_file() else default


def run(data: Path, state_path: Path, report_dir: Path, today: dt.date, only: set[str], since: str, max_calls: int,
        max_press_pages: int, max_details: int, apply: bool, keep_state: bool, opener=None, sleep=time.sleep) -> dict:
    from pipeline.enrich import load_dotenv
    load_dotenv(ROOT / ".env")
    dkey = os.environ.get("DATA_GO_KR_KEY", "").strip()
    tkey = os.environ.get("TOURAPI_KEY", "").strip() or dkey
    dkey, tkey = (urllib.parse.unquote(k) if "%" in k else k for k in (dkey, tkey))
    budget = Budget(max_calls)
    net = Net(budget, (dkey, tkey), opener=opener, sleep=sleep)
    state = load_json(state_path, {})
    events = load_json(data / "events.json", [])
    places = load_json(data / "places.json", [])
    iso = today.isoformat()
    res: dict = {}
    if "press" in only:
        st = state.get("press") or {}
        res["press"] = check_press(net, st, events, since, max_press_pages, max_details)
        if res["press"]["last_no"] is not None:
            state["press"] = {"last_no": res["press"]["last_no"], "checked_at": iso}
    if "festival" in only:
        st = state.get("festival") or {}
        if not tkey:
            res["festival"] = {"error": "키 없음 — 환경 변수 TOURAPI_KEY(또는 DATA_GO_KR_KEY)"}
        else:
            try:
                items = festivals(net, tkey, today.strftime("%Y%m%d"))
                res["festival"] = compare_festivals(items, st.get("items") or {}, events, iso)
                state["festival"] = {"items": res["festival"]["items"], "checked_at": iso}
            except (FetchError, CallCapError) as e:
                res["festival"] = {"error": str(e)}
    if "tide" in only:
        if not dkey:
            res["tide"] = {"ok": False, "msg": "키 없음 — 환경 변수 DATA_GO_KR_KEY"}
        else:
            ok, msg = tide_alive(net, dkey, today)
            res["tide"] = {"ok": ok, "msg": msg}
            state["tide"] = {"ok": ok, "msg": msg, "checked_at": iso,
                             "last_ok": iso if ok else (state.get("tide") or {}).get("last_ok")}
    if "crowd" in only:
        res["crowd"], res["almanac"] = crowd_status(data, today), almanac_status(data, today)
    if "license" in only:
        st = state.get("license") or {}
        lic_dir, _ = mois.raw_dirs(data)
        log = load_json(lic_dir / mois.FETCH_LOG, {})
        lsince = st.get("since") or max((v.get("fetched_at", "") for v in log.values()), default="") or since
        licenses = load_json(data / "licenses.json", {})
        if not dkey:
            res["license"] = {"error": "키 없음 — 환경 변수 DATA_GO_KR_KEY"}
        elif not licenses:
            res["license"] = {"error": f"{data / 'licenses.json'} 없음 — 먼저 tools/mois_licenses_gunsan.py"}
        else:
            try:
                updated = license_updates(net, dkey, lsince)
                changes = license_changes(places, mois.load_rows(lic_dir), updated, licenses, iso)
                alerted = dict(st.get("alerted") or {})
                old = licenses.get("places") or {}
                pub = {p["id"] for p in places if p.get("status") == "published"}
                fresh_ids = {x["id"] for x in changes}
                still = [x for pid, x in alerted.items() if pid not in fresh_ids and pid in pub
                         and (old.get(pid) or {}).get("status") == x["was"]]
                for x in changes:
                    alerted[x["id"]] = {**x, "first_seen": (alerted.get(x["id"]) or {}).get("first_seen", iso)}
                alerted = {pid: x for pid, x in alerted.items()
                           if pid in pub and (old.get(pid) or {}).get("status") == x["was"]}
                res["license"] = {"since": lsince, "updated": len(updated), "changes": changes, "still": still}
                state["license"] = {"since": iso, "checked_at": iso, "alerted": alerted}
            except (FetchError, CallCapError) as e:
                res["license"] = {"error": f"{e} (다음 실행이 {lsince}부터 다시 본다)"}
    if apply:
        crowd = res.get("crowd") or crowd_status(data, today)
        alm = res.get("almanac") or almanac_status(data, today)
        res["applied"] = apply_safe(data, crowd, alm, (res.get("tide") or {}).get("ok"), today, net)
    text = report(iso, res, (budget.used, budget.max))
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"{iso}.md"
    out.write_text(net.mask(text), "utf-8")
    if keep_state:
        state["_about"] = ("tools/watch_updates.py의 지난 점검 상태 — press.last_no(마지막으로 본 군산시 보도자료 번호), "
                           "festival.items(TourAPI 행사 contentid별 제목·기간), license.since(인허가 바뀐 행을 볼 시작일)·"
                           "alerted(알렸고 아직 licenses.json에 반영 안 된 곳), tide(조석예보 서버 응답). 사람이 고치지 않는다.")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(dict(sorted(state.items())), ensure_ascii=False, indent=1) + "\n", "utf-8")
    res["report"] = str(out)
    res["calls"] = budget.used
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data/gunsan"))
    ap.add_argument("--state", type=Path, default=Path("data/watch/state.json"))
    ap.add_argument("--report-dir", type=Path, default=Path("reports/watch"))
    ap.add_argument("--only", help="쉼표로: " + ",".join(SECTIONS))
    ap.add_argument("--since", help="상태 파일이 없을 때 보도자료를 볼 시작일 YYYY-MM-DD(기본 14일 전)")
    ap.add_argument("--today", help="오늘 YYYY-MM-DD(기본: 한국 시각)")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--max-press-pages", type=int, default=10)
    ap.add_argument("--max-details", type=int, default=30)
    ap.add_argument("--apply-safe", action="store_true", help="crowd.json·almanac.json 같은 자동 자료만 다시 받는다")
    ap.add_argument("--no-state", action="store_true", help="상태 파일을 바꾸지 않는다")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else set(SECTIONS)
    if only - set(SECTIONS):
        ap.error(f"--only: {','.join(sorted(only - set(SECTIONS)))}")
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(KST).date()
    since = a.since or (today - dt.timedelta(days=DEFAULT_SINCE_DAYS)).isoformat()
    res = run(a.data, a.state, a.report_dir, today, only, since, a.max_calls, a.max_press_pages, a.max_details,
              a.apply_safe, not a.no_state)
    p, f, lic = res.get("press"), res.get("festival"), res.get("license")
    print(f"보고서: {res['report']} (호출 {res['calls']}회)")
    if p:
        print(f"  보도자료 새 글 {p['rows']}건, 여행 관련 {len(p['hits'])}건(사이트에 없음 "
              f"{sum(1 for h in p['hits'] if not h['in_events'])})" + (f" — {p['error']}" if p["error"] else ""))
    if f:
        print("  TourAPI 행사: " + (f["error"] if f.get("error") else
                                   f"{len(f['items'])}건, 새 {len(f['new'])}, 바뀜 {len(f['changed'])}, 사이트에 없음 "
                                   f"{len(f['missing'])}"))
    if lic:
        print("  인허가: " + (lic["error"] if lic.get("error") else
                            f"바뀐 행 {lic['updated']}건, 공개 장소 상태 바뀜 {len(lic['changes'])}곳"))
    if res.get("tide"):
        print(f"  조석예보: {'응답함' if res['tide']['ok'] else '응답 없음'}")
    if res.get("crowd", {}).get("exists"):
        print(f"  crowd.json 남은 {res['crowd']['days_left']}일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
