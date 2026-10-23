"""TourAPI 연결 진단 — 키·네트워크·서비스 버전 문제를 한 번에 가린다.

    python tools/tourapi_doctor.py                                    # .env 또는 환경 변수 TOURAPI_KEY 사용
    python tools/tourapi_doctor.py --data data/daegu                  # 검색어 기본값 = site.json의 region
    python tools/tourapi_doctor.py --data data/daegu --check-region   # ldongCode2의 구·군 목록과 빠진 구·군
    python tools/tourapi_doctor.py --keyword 박물관
    python tools/tourapi_doctor.py --json                             # 결과를 JSON으로(에이전트용)

선택 인자
  --data DIR       도시 데이터 폴더. site.json을 읽어 검색어 기본값(region)과 MobileApp(tourapi.mobile_app)을 정한다.
                   없으면 검색어 기본값은 중립 낱말 '관광'이다.
  --keyword WORD   searchKeyword2 검색어(주면 기본값 대신 쓴다).
  --check-region   (--data 필요) ldongCode2로 시·도 목록을 받아 이름이 tourapi.ldong_regn_name(없으면 region_admin)과
                   정확히 같은 하나를 고르고, 그 아래 구·군 목록을 코드와 함께 출력한 뒤 site.json districts(없으면
                   locality) 가운데 응답에 없는 이름을 알린다(예: 군위군 — docs/rights.md 4절). 코드는 응답에서만
                   읽는다. 시·도가 하나로 정해지지 않거나 빠진 구·군이 있으면 종료 코드 1.
  --json           결과를 JSON으로.

- 표준 라이브러리만 쓴다. 저장소의 pipeline 코드와 무관하게 단독으로 돈다(--data도 site.json을 json으로만 읽는다).
- 키는 어떤 출력에도 나오지 않는다(원문·인코딩·디코딩 형태 모두 가림). 대신 공급자 오류 메시지는
  키만 가린 채 그대로 보여 준다 — 메시지를 통째로 숨기면 원인을 알 수 없다.
- 공공데이터포털은 같은 키를 'Encoding'과 'Decoding' 두 형태로 준다. 어느 쪽을 넣어도 되도록
  '%'가 들어 있으면 한 번 풀어(Decoding 형태로 정규화) 쓴다. 두 형태를 모두 시험해 어느 쪽이 통하는지도 알려 준다.
- 요청의 MobileApp·User-Agent에는 도시나 브랜드 이름을 넣지 않는다(site.json tourapi.mobile_app이 있으면 그 값).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "apis.data.go.kr"
SERVICES = [("KorService2", "searchKeyword2"), ("KorService1", "searchKeyword1")]
DEFAULT_KEYWORD = "관광"           # --data도 --keyword도 없을 때: 어느 도시에도 묶이지 않은 낱말
DEFAULT_MOBILE_APP = "TravelSite"  # pipeline.tourapi.DEFAULT_MOBILE_APP과 같은 중립 이름(이 도구는 pipeline을 쓰지 않는다)
USER_AGENT = "tourapi-doctor"
OK_CODES = ("0000", "00", "0")
# 공공데이터포털 공통 오류 → 원인·조치 (메시지 문자열 기준으로 판별)
KNOWN = {
    "SERVICE_KEY_IS_NOT_REGISTERED": "등록되지 않은 키 — 오타, Encoding 키를 한 번 더 인코딩, 다른 API용 키, 승인 직후 동기화 대기(보통 1시간 안팎) 중 하나",
    "SERVICE_ACCESS_DENIED": "이 키로 '한국관광공사_국문 관광정보 서비스' 활용신청이 안 됨 — 마이페이지에서 활용신청·승인 상태 확인",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS": "일일 호출 한도 초과 — 다음 날 재시도, 캐시 활용",
    "DEADLINE_HAS_EXPIRED": "활용 기간 만료 — 마이페이지에서 연장 신청",
    "UNREGISTERED_IP": "허용되지 않은 IP — 활용신청의 IP 제한 설정 확인",
    "NO_OPENAPI_SERVICE": "서비스 주소·오퍼레이션 이름 오류 — 버전(KorService1/2)과 오퍼레이션명 확인",
    "INVALID_REQUEST_PARAMETER": "요청 파라미터 오류 — 명세의 필수 파라미터 확인",
    "NO_MANDATORY_REQUEST_PARAMETERS": "필수 파라미터 누락 — MobileOS·MobileApp 등 확인",
}


def load_key(env_path: Path = Path(".env")) -> str:
    key = os.environ.get("TOURAPI_KEY", "")
    if not key and env_path.exists():
        for line in env_path.read_text("utf-8").splitlines():
            line = line.strip()
            if line.startswith("TOURAPI_KEY="):
                key = line.split("=", 1)[1]
                break
    return key.strip().strip('"').strip("'")


def key_forms(raw: str) -> dict:
    """Return the decoded (canonical) key and what the user seems to have pasted."""
    raw = raw.strip()
    decoded = urllib.parse.unquote(raw) if "%" in raw else raw
    return {
        "given_form": "Encoding(인코딩된 키)" if "%" in raw else "Decoding(일반 키)",
        "decoded": decoded,
        "encoded_once": urllib.parse.quote(decoded, safe=""),
        "length": len(decoded),
        "has_whitespace": bool(re.search(r"\s", raw)),
    }


def redact(text: str, *secrets: str) -> str:
    out = text or ""
    for s in sorted({x for x in secrets if x and len(x) >= 6}, key=len, reverse=True):
        out = out.replace(s, "«KEY»")
    return out


def classify(body: str) -> dict:
    """Pull result codes/messages out of a JSON or XML response body."""
    info = {"format": "unknown", "code": "", "message": "", "items": 0, "first": ""}
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("response"), dict):
        info["format"] = "json"
        header = data["response"].get("header") or {}
        info["code"] = str(header.get("resultCode", ""))
        info["message"] = str(header.get("resultMsg", ""))
        items = ((data["response"].get("body") or {}).get("items") or {})
        item = items.get("item") if isinstance(items, dict) else None
        lst = item if isinstance(item, list) else ([item] if isinstance(item, dict) else [])
        info["items"] = len(lst)
        if lst:
            info["first"] = f"{lst[0].get('title', '')} | {lst[0].get('addr1', '')} | contentid={lst[0].get('contentid', '')}"
        return info
    if isinstance(data, dict) and "OpenAPI_ServiceResponse" in data:
        hdr = (data["OpenAPI_ServiceResponse"] or {}).get("cmmMsgHeader") or {}
        info.update(format="json-gateway", code=str(hdr.get("returnReasonCode", "")),
                    message=str(hdr.get("returnAuthMsg") or hdr.get("errMsg") or ""))
        return info
    def tag(*names: str) -> str:
        for name in names:  # priority order: the specific auth message beats the generic errMsg
            m = re.search(rf"<{name}>\s*([^<]*)<", body or "")
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""
    code, msg = tag("returnReasonCode", "resultCode"), tag("returnAuthMsg", "resultMsg", "errMsg")
    if code or msg:
        info.update(format="xml", code=code, message=msg)
    return info


def advice(message: str) -> str:
    for marker, text in KNOWN.items():
        if marker in (message or "").upper():
            return text
    return ""


def tcp_check(host: str = HOST, timeout: float = 6.0) -> tuple[bool, str]:
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        return True, "프록시 경유 환경 — 직접 연결 확인은 생략하고 실제 요청 결과로 판단"
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True, "연결됨"
    except OSError as e:
        return False, f"{type(e).__name__}: {e}"


def request(service: str, op: str, key_param: str, params: dict, timeout: float = 15.0,
            mobile_app: str = DEFAULT_MOBILE_APP) -> dict:
    """One GET. key_param is inserted verbatim (already URL-safe); every other value is encoded here.
    {"status", "content_type", "body"}, or {"network_error", "advice"} when no HTTP answer came back."""
    others = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": mobile_app or DEFAULT_MOBILE_APP,
                                     "_type": "json", **params})
    url = f"https://{HOST}/B551011/{service}/{op}?serviceKey={key_param}&{others}"
    status, ctype, body = None, "", ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, ctype = r.status, r.headers.get("Content-Type", "")
            body = r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, ctype = e.code, e.headers.get("Content-Type", "") if e.headers else ""
        try:
            body = e.read(200_000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - diagnostics only
            body = ""
    except (urllib.error.URLError, OSError) as e:
        msg = f"{type(e).__name__}: {e}"
        hint = ("실행 환경의 네트워크 정책(프록시)이 apis.data.go.kr을 막고 있음 — 허용 도메인에 추가하거나 PC에서 실행"
                if "Tunnel connection failed" in msg or "403" in msg else
                "네트워크 연결 실패 — 인터넷·방화벽·DNS 확인")
        return {"network_error": msg, "advice": hint}
    return {"status": status, "content_type": ctype, "body": body}


def call(service: str, op: str, key_param: str, keyword: str, timeout: float = 15.0,
         mobile_app: str = DEFAULT_MOBILE_APP) -> dict:
    """searchKeyword with one key form."""
    r = request(service, op, key_param, {"numOfRows": 3, "pageNo": 1, "arrange": "A", "keyword": keyword},
                timeout, mobile_app)
    if "network_error" in r:
        return {"service": service, "op": op, **r}
    info = classify(r["body"])
    return {"service": service, "op": op, "http_status": r["status"], "content_type": r["content_type"],
            "result": info, "body_head": r["body"][:300], "advice": advice(info["message"])}


def items_of(body: str) -> list[dict]:
    """The item list of a JSON success body ([] for anything else)."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []
    items = (((data.get("response") or {}).get("body") or {}).get("items") or {}) if isinstance(data, dict) else {}
    item = items.get("item") if isinstance(items, dict) else None
    return [x for x in (item if isinstance(item, list) else [item]) if isinstance(x, dict)]


def _squash(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def load_site(data_dir: Path) -> dict:
    """site.json of a city data folder (json only: this tool does not use the pipeline package)."""
    return json.loads((Path(data_dir) / "site.json").read_text("utf-8"))


def region_target(site: dict) -> dict:
    """What --check-region looks for: the 시·도 name (tourapi.ldong_regn_name, else region_admin) and the names under
    it (districts, else the locality)."""
    t = site.get("tourapi") if isinstance(site.get("tourapi"), dict) else {}
    districts = [_squash(d) for d in site.get("districts") or [] if _squash(d)]
    return {"regn_name": _squash(t.get("ldong_regn_name")) or _squash(site.get("region_admin")),
            "locality": _squash(site.get("locality")),
            "expected": districts or [_squash(site.get("locality"))], "unit": "구·군" if districts else "시"}


def _ldong(key_param: str, params: dict, mobile_app: str, service: str = "KorService2") -> tuple[list[dict], str]:
    """(items, '') or ([], error text) for one ldongCode2 request."""
    r = request(service, "ldongCode2", key_param, {"numOfRows": 100, "pageNo": 1, **params}, mobile_app=mobile_app)
    if "network_error" in r:
        return [], r["network_error"]
    info = classify(r["body"])
    if info["format"] != "json" or info["code"] not in OK_CODES:
        return [], f"HTTP {r['status']} · code={info['code']} · {info['message'] or r['body'][:200]}"
    return items_of(r["body"]), ""


def check_region(key_param: str, target: dict, mobile_app: str = DEFAULT_MOBILE_APP) -> dict:
    """ldongCode2: the one 시·도 named exactly target['regn_name'], the names (with codes) under it, and which of
    target['expected'] are missing (none, or more than one with that name). Codes are only ever read here."""
    out = {"want": target["regn_name"], "regn": None, "signgu": [], "expected": target["expected"], "missing": [],
           "ok": False}
    regions, err = _ldong(key_param, {}, mobile_app)
    if err:
        out["message"] = f"ldongCode2(시·도) 오류: {err}"
        return out
    hits = [r for r in regions if _squash(r.get("name")) == target["regn_name"]]
    if len(hits) != 1:
        out["message"] = (f"시·도 이름이 '{target['regn_name']}'인 항목이 {len(hits)}개 — site.json tourapi.ldong_regn_name"
                          f"(없으면 region_admin)을 응답의 이름과 정확히 맞추세요 (응답: "
                          f"{', '.join(_squash(r.get('name')) for r in regions) or '없음'})")
        return out
    out["regn"] = {"code": str(hits[0].get("code") or ""), "name": target["regn_name"]}
    under, err = _ldong(key_param, {"lDongRegnCd": out["regn"]["code"]}, mobile_app)
    if err:
        out["message"] = f"ldongCode2({target['regn_name']} 아래) 오류: {err}"
        return out
    out["signgu"] = [{"code": str(r.get("code") or ""), "name": _squash(r.get("name"))} for r in under]
    names = [s["name"] for s in out["signgu"]]
    loc = target.get("locality") or ""
    out["missing"] = [n for n in target["expected"]
                      if names.count(n) != 1 and (not loc or names.count(f"{loc} {n}") != 1)]
    out["ok"] = not out["missing"]
    out["message"] = (f"site.json {target['unit']} {len(target['expected'])}개가 모두 {target['regn_name']} 코드 아래에 있음"
                      if out["ok"] else
                      f"{', '.join(out['missing'])}: {target['regn_name']} 코드 아래에 없음(또는 이름이 둘 이상) — "
                      "docs/rights.md 4절")
    return out


def run(keyword: str, raw_key: str, region: dict | None = None, mobile_app: str = DEFAULT_MOBILE_APP) -> dict:
    """The connection check; with `region` (region_target(site)) also the ldongCode2 check (report['region'])."""
    report: dict = {"keyword": keyword}
    ok, why = tcp_check()
    report["network"] = {"host": HOST, "ok": ok, "detail": why}
    if not raw_key:
        report["verdict"] = "TOURAPI_KEY가 없습니다. 저장소 루트 .env에 TOURAPI_KEY=키 한 줄을 넣거나 환경 변수로 설정하세요."
        return report
    forms = key_forms(raw_key)
    report["key"] = {"given_form": forms["given_form"], "length": forms["length"],
                     "has_whitespace": forms["has_whitespace"]}
    if not ok:
        report["verdict"] = ("apis.data.go.kr에 접속할 수 없습니다(네트워크 차단). 이 컴퓨터/환경에서 해당 도메인 접근을 허용하거나, "
                             "접속 가능한 PC에서 실행하세요.")
        return report
    attempts = []
    # 1) canonical: decoded key encoded exactly once  2) the pasted form verbatim (if it was an Encoding key)
    variants = [("decoded→1회 인코딩", forms["encoded_once"])]
    if "%" in raw_key.strip():
        variants.append(("붙여 넣은 그대로", raw_key.strip()))
    working = {}  # service -> the key form that answered OK
    for service, op in SERVICES:
        for label, param in variants:
            res = call(service, op, param, keyword, mobile_app=mobile_app)
            res["key_variant"] = label
            attempts.append(res)
            if res.get("result", {}).get("code") in OK_CODES and res["result"]["items"] >= 0 \
                    and res["result"]["format"] == "json":
                working.setdefault(service, param)
                break
    secrets = (raw_key, forms["decoded"], forms["encoded_once"])
    for a in attempts:
        for k in ("body_head", "network_error"):
            if k in a:
                a[k] = redact(a[k], *secrets)
        if "result" in a:
            a["result"]["message"] = redact(a["result"]["message"], *secrets)
            a["result"]["first"] = redact(a["result"]["first"], *secrets)
    report["attempts"] = attempts
    good = [a for a in attempts if a.get("result", {}).get("format") == "json"
            and a["result"]["code"] in OK_CODES]
    if good:
        g = good[0]
        report["verdict"] = (f"정상 — {g['service']}/{g['op']} 응답 OK(항목 {g['result']['items']}개, 첫 항목: {g['result']['first'] or '-'}). "
                             f"키 형태: {forms['given_form']}. 파이프라인은 키를 'decoded→1회 인코딩'으로 정규화해 쓰면 된다.")
    else:
        msgs = [a.get("advice") or a.get("result", {}).get("message") or a.get("network_error") or f"HTTP {a.get('http_status')}"
                for a in attempts]
        report["verdict"] = "실패 — " + " / ".join(dict.fromkeys(m for m in msgs if m))
    if region is not None:
        if "KorService2" in working:
            reg = check_region(working["KorService2"], region, mobile_app)
            reg["message"] = redact(reg.get("message", ""), *secrets)
        else:
            reg = {"want": region["regn_name"], "regn": None, "signgu": [], "expected": region["expected"],
                   "missing": [], "ok": False, "message": "KorService2 연결이 안 돼 지역 코드(ldongCode2)를 확인하지 못함"}
        report["region"] = reg
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, help="도시 데이터 폴더(선택): site.json의 region을 검색어 기본값으로")
    ap.add_argument("--keyword", help=f"검색어(기본: --data의 region, 없으면 '{DEFAULT_KEYWORD}')")
    ap.add_argument("--check-region", action="store_true",
                    help="(--data 필요) ldongCode2의 시·도와 그 아래 구·군 목록을 출력하고 빠진 구·군을 알린다")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    site: dict = {}
    if a.data is not None:
        try:
            site = load_site(a.data)
        except (OSError, ValueError) as err:
            ap.error(f"--data {a.data}: site.json을 읽지 못함 ({err})")
    if a.check_region and not site:
        ap.error("--check-region에는 --data(도시 데이터 폴더)가 필요합니다")
    keyword = a.keyword or _squash(site.get("region")) or DEFAULT_KEYWORD
    mobile_app = _squash((site.get("tourapi") or {}).get("mobile_app")) or DEFAULT_MOBILE_APP
    rep = run(keyword, load_key(), region_target(site) if a.check_region else None, mobile_app)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(f"[네트워크] {rep['network']['host']}: {'OK' if rep['network']['ok'] else '실패'} ({rep['network']['detail']})")
        if "key" in rep:
            k = rep["key"]
            print(f"[키] 형태 {k['given_form']}, 길이 {k['length']}, 공백 포함 {k['has_whitespace']} (값은 표시하지 않음)")
        for at in rep.get("attempts", []):
            r = at.get("result", {})
            line = at.get("network_error") or f"HTTP {at.get('http_status')} · {r.get('format')} · code={r.get('code')} · {r.get('message')}"
            print(f"[시도] {at['service']}/{at['op']} · 키 {at['key_variant']} → {line}")
            if at.get("advice"):
                print(f"       → {at['advice']}")
        print(f"[결론] {rep['verdict']}")
        reg = rep.get("region")
        if reg:
            if reg.get("regn"):
                print(f"[지역] 시·도 {reg['regn']['name']}({reg['regn']['code']}) — ldongCode2 응답에서 읽음")
                print(f"[지역] 그 아래 {len(reg['signgu'])}개: "
                      + (", ".join(f"{s['name']}({s['code']})" for s in reg["signgu"]) or "없음"))
            print(f"[지역 결론] {'정상' if reg['ok'] else '확인 필요'} — {reg.get('message', '')}")
    ok = str(rep.get("verdict", "")).startswith("정상") and (rep.get("region") or {"ok": True})["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
