"""장소 요약·FAQ 작성 도구 — 작성자용 사실표(prepare), 기계 검사(check), 반영(merge). 네트워크를 쓰지 않는다.

    python tools/place_content.py prepare --data data/<도시> --out work/content [--batch 12] [--only ids.txt]
    python tools/place_content.py check --data data/<도시> work/content/places-01.output.json [...] [--inputs DIR] [--json]
    python tools/place_content.py merge --data data/<도시> work/content/places-*.output.json [--inputs DIR] [--dry-run]

앞 사이트의 3차 내용 도구(사실표·복사·문구·숫자·FAQ 검사)에서 도시와 상관없는 부분만 옮겼다. 도시 값(시·도,
구·군, 상투구)은 모두 site.json → pipeline.city.of(site)에서 오고, 이 파일에는 도시 이름이 없다.

prepare — 요약이 필요한 장소(요약 없음, summary_auto, 첫 문장이 schema.summary_problems에 걸림; 중복·제외 레코드는
  빼고)를 --batch개씩 DIR/places-NN.input.json({"rules", "output_example", "items"})으로 쓴다. --only는 장소 id(또는
  slug) 목록 파일(줄·쉼표 구분 텍스트, 또는 JSON 목록·{"ids": [...]})이고, 그 장소만 골라 쓴다. 같은 폴더의 이전
  places-*.input.json은 지운다(출력 파일은 그대로). 사실표: id·slug·name·kind·category, district·area·road
  (City.parse_address), alternate_names, tourapi_title, facts 행 {key, label, value, provider, checked_at,
  [url, confirmed_by, differs_from]}, source_text(TourAPI overview — 사실 확인용, 옮겨 쓰기 금지), nearby(이름),
  events(같은 장소의 행사: 이름 포함 또는 같은 주소), current_summary, current_faq, faq_sources.
check — 작성자 출력({"items": [{id, summary, faq: [{q, a, source}], thin?}]} 또는 그 목록)을 사실표와 맞춰 본다.
  사실표는 --inputs 폴더(기본: 출력 파일이 있는 폴더)의 *.input.json에서 id로 찾는다(같은 이름의 입력 파일 우선).
  하나라도 걸리면 종료 코드 1. 검사(모두 막는다):
  - 복사: source_text(지금 데이터의 overview도)와 15자 이상 연속 일치(이름·사실 값은 빼고 센다; 그런 구간을 지운
    뒤 남은 구간도 다시 찾는다)
  - 문구: 출처 해설체·전언체·'자료에 없음'·'확인 필요'·근거 없는 수식어(BANNED), 장소 이름을 먼저 지우고 본다
  - 요약: 비어 있지 않음, 1~3문장, 문장마다 '다.'로 끝남, schema.summary_problems(새 요약을 넣은 장소 사본,
    city=…)가 내는 문제 전부(상투구 City.taut_rx·출처 해설체), 별칭·괄호 뺀 이름으로 쓴 상투구도
  - 숫자: 요약·FAQ 질문·답의 숫자 묶음이 모두 사실표(사실 값·다른 출처 값·source_text·이름·별칭·구·군·동·도로)에 있음
  - FAQ: 존댓말 의문형(JONDAE), 질문에 장소 이름, source는 faq_sources 중 하나, 음식점·숙소 2개·그 밖 3개 이하,
    같은 질문을 검사하는 다른 항목·places.json의 다른 장소 FAQ와 겹치지 않음
  - 기타: 사실표·places.json에 있는 id, 사실표 뒤 이름이 바뀌지 않음, 같은 id 두 번 금지, thin은 주소·홈페이지
    말고 쓸 사실이 없을 때만, locks에 summary(FAQ를 쓰면 faq)가 없음
merge — check를 다시 돌려 문제가 있는 항목은 거부하고(사유를 보고), 깨끗한 항목만 places.json에 반영한다: summary,
  faq(비어 있지 않을 때만 교체 — 비우거나 빼면 기존 FAQ 유지), summary_auto 삭제, thin=true면 summary_thin=true(아니면
  삭제). status·reviewed_at·approved_at·slug와 다른 필드는 건드리지 않는다. 임시 파일 + os.replace로 쓰고, 읽은 뒤
  places.json이 바뀌었으면(다른 수집이 쓰는 중) 아무것도 쓰지 않는다. --dry-run은 쓰지 않고 결과만 보인다.
  결과 JSON {dry_run, merged, refused, faq, thin, merged_ids, refused_items, problems, after_review, written}.
  거부·문제가 하나라도 있으면 종료 코드 1(깨끗한 항목은 반영됨).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import city as citymod
from pipeline.schema import FACT_LABELS, INDEX_REASONS, KIND_LABELS, summary_problems, summary_sentences
from pipeline.textutil import display_address, normalize_name, squash_ws

COPY_LIMIT = 15            # CLAUDE.md 3.3: 원문과 15자 이상 연속 일치 금지
SOURCE_TEXT_MAX = 6000
SUMMARY_MAX_SENTENCES = 3
FAQ_MAX = {"food": 2, "stay": 2}
FAQ_MAX_DEFAULT = 3
THIN_IGNORED = ("address", "homepage")   # thin may be claimed only when nothing but these is known
TOURAPI_SOURCE = "한국관광공사 TourAPI"
INPUT_GLOB = "places-*.input.json"
BANNED = [
    (r"원문[은는이에서의]", "출처 해설체('원문은…')"),
    (r"(소개|설명|안내)(합니다|한다|하고 있|되어 있)", "출처 해설체('~를 소개합니다')"),
    (r"라고\s*(합니다|한다|전합니다|알려져)", "전언체('~라고 합니다')"),
    (r"(자료|정보)(에|가)\s*(없|나와 있지|기재되어 있지)", "'자료에 없음' 답변"),
    (r"확인(이)?\s*필요", "'확인 필요' 문구(화면이 블록마다 한 번 자동 표시)"),
    (r"최고|최상|꼭\s|필수|인기|아름다운|아름답|멋진|환상|완벽|강추|유명한|손꼽|명소 중|대표적인 명소|낭만|감성 가득|힐링",
     "근거 없는 수식어"),
]
JONDAE = re.compile(r"(나요|까요|습니까|가요|인가요|세요|되나요|있나요|하나요|ㄴ가요|던가요|을까요|일까요)\?$")
EXTRA_LABELS = {  # TourAPI intro keys; pipeline.schema.FACT_LABELS holds them today, this is the fallback
    "seat": "좌석", "treatmenu": "취급 메뉴", "packing": "포장", "kidsfacility": "어린이 놀이방",
    "reservation": "예약 안내", "reservationurl": "예약 페이지", "roomcount": "객실 수", "roomtype": "객실 유형",
    "subfacility": "부대시설", "cooking": "객실 내 취사", "creditcard": "신용카드 결제", "expguide": "체험 안내",
    "discount": "할인", "openperiod": "운영 기간", "filming": "촬영지 정보",
    "fairday": "장날", "saleitem": "판매 품목", "shopguide": "매장 안내",
}
OUTPUT_EXAMPLE = {"items": [{"id": "<사실표의 id>", "summary": "답부터 쓰는 평서문 1~3문장.",
                             "faq": [{"q": "<장소 이름>은 … 있나요?", "a": "사실표 값으로 답합니다.",
                                      "source": "<faq_sources 중 하나>"}],
                             "thin": False}]}


# ------------------------------------------------------------------ io
def load_json(path: Path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Write next to the target, then os.replace (a reader never sees half a file)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


def load_city(data: Path):
    site = load_json(data / "site.json")
    if not isinstance(site, dict):
        raise SystemExit(f"{data / 'site.json'}이 없거나 객체가 아닙니다")
    return citymod.of(site)


# ------------------------------------------------------------------ fact sheets
def label(key: str) -> str:
    return FACT_LABELS.get(key) or EXTRA_LABELS.get(key) or key


def _text(value) -> str:
    return squash_ws("" if value is None else str(value))


def name_variants(name: str, alternates=(), title: str = "") -> list[str]:
    """Names a sentence may use for the place: the name, the name without a bracket ('A(B)' -> 'A', '[x] A' -> 'A'),
    the bracket's content, alternate names, the TourAPI title. Two characters or more, without repeats."""
    base = squash_ws(re.sub(r"\(.*?\)|\[.*?\]|（.*?）", " ", name))
    inner = [squash_ws(g) for groups in re.findall(r"\((.*?)\)|（(.*?)）", name) for g in groups if g]
    out = [name, base, *inner, *(squash_ws(a) for a in alternates or ()), squash_ws(title)]
    return [n for n in dict.fromkeys(out) if len(n) >= 2]


def needs_summary(p: dict, *, city) -> bool:
    """A shown record whose summary is missing, auto-written, or breaks CLAUDE.md 3.5 (schema.summary_problems)."""
    if p.get("duplicate_of") or p.get("exclude"):
        return False
    if p.get("summary_auto") or not squash_ws(p.get("summary")):
        return True
    return bool(summary_problems(p, city=city))


def fact_rows(p: dict) -> list[dict]:
    """facts as rows with the provider of each value (fact_sources, else facts_source) and the other sources' values."""
    base = p.get("facts_source") or {}
    rows = []
    for key, value in (p.get("facts") or {}).items():
        v = _text(value)
        if not v:
            continue
        src = (p.get("fact_sources") or {}).get(key) or base
        row = {"key": key, "label": label(key), "value": v, "provider": _text(src.get("provider")),
               "checked_at": _text(src.get("checked_at"))}
        for extra in ("url", "confirmed_by"):
            if _text(src.get(extra)):
                row[extra] = _text(src[extra])
        alts = [{"value": _text(a.get("value")), "provider": _text(a.get("provider")),
                 **({"relation": a["relation"]} if a.get("relation") else {})}
                for a in (p.get("fact_alternatives") or {}).get(key) or [] if _text(a.get("value"))]
        if alts:
            row["differs_from"] = alts
        rows.append(row)
    return rows


def faq_sources(p: dict) -> list[str]:
    """What a FAQ answer may cite: TourAPI (when the record comes from it), the original page, and every URL a value
    was checked on (a facility's own homepage)."""
    out = []
    providers = [_text((p.get("facts_source") or {}).get("provider"))]
    providers += [_text(s.get("provider")) for s in (p.get("fact_sources") or {}).values() if isinstance(s, dict)]
    if (p.get("tourapi") or {}).get("contentid") or any(w in x for x in providers for w in citymod.NATIONAL_PROVIDER):
        out.append(TOURAPI_SOURCE)
    urls = [(p.get("original") or {}).get("source_url")]
    urls += [s.get("url") for s in (p.get("fact_sources") or {}).values() if isinstance(s, dict)]
    out += [_text(u) for u in urls if _text(u).startswith(("http://", "https://"))]
    return list(dict.fromkeys(out))


def events_at(p: dict, events: list[dict]) -> list[dict]:
    """Events held at this place: the event's place names it (3+ characters, normalised) or has the same address."""
    key = normalize_name(p.get("name"))
    addr = display_address((p.get("facts") or {}).get("address"))
    out = []
    for e in events or []:
        named = len(key) >= 3 and key in normalize_name(e.get("place_name"))
        if named or (addr and display_address(e.get("address")) == addr):
            out.append({k: _text(e.get(k)) for k in ("name", "start_date", "end_date", "place_name")})
    return out


def fact_sheet(p: dict, *, city, events: list[dict] | None = None) -> dict:
    a = city.parse_address((p.get("facts") or {}).get("address"))
    tour = p.get("tourapi") or {}
    return {
        "id": p["id"], "slug": p.get("slug", ""), "name": p["name"], "kind": p.get("kind", ""),
        "category": p.get("category", ""), "district": a.district, "area": a.area, "road": a.road,
        "alternate_names": list(p.get("alternate_names") or []), "tourapi_title": _text(tour.get("title")),
        "facts": fact_rows(p),
        "source_text": squash_ws(tour.get("overview"))[:SOURCE_TEXT_MAX],
        "nearby": [_text(n.get("name")) for n in p.get("nearby") or [] if isinstance(n, dict) and _text(n.get("name"))],
        "events": events_at(p, events or []),
        "current_summary": p.get("summary", ""),
        "current_faq": p.get("faq") or [],
        "faq_sources": faq_sources(p),
    }


def rules(city) -> list[str]:
    """What every writer reads first (CLAUDE.md 3절 1·2·5·6·10, 4절), with this city's stock sentence."""
    stock = f"'○○은 {city.admin_line} ○○에 있는 ○○입니다'"
    if city.districts:
        stock += f"(시 이름 대신 {city.region_label} 이름으로 시작해도 같다)"
    return [
        "source_text는 한국관광공사 TourAPI 개요(overview)로, 사실 확인용이다. 게재하지 않고 문장을 옮기지 않는다 — "
        f"요약·FAQ가 source_text와 {COPY_LIMIT}자 이상 연속 일치하면(이름·사실 값 제외) 검사에서 막힌다. 우리 문장으로 쓴다.",
        "사실은 이 사실표(facts·source_text·이름·주소)에서만 가져온다. 추정이나 일반 지식으로 채우지 않는다. "
        "요약·FAQ의 숫자는 모두 사실표에 있어야 한다. 제3자 리뷰·평점·블로그 내용과 근거 없는 업체 추천은 쓰지 않는다.",
        f"요약(summary)은 답부터 쓰는 평서문 1~{SUMMARY_MAX_SENTENCES}문장이고, 문장마다 '다.'로 끝낸다.",
        f"첫 문장을 {stock} 꼴로만 끝내지 않는다. 그 장소만의 사실(대표 메뉴·좌석·객실 수·운영 특징·볼거리)을 "
        "하나 이상 넣는다. 쓸 사실이 없으면 짧게 두고 thin: true로 표시한다(색인에서 빠진다). 주소·홈페이지 말고 사실이 "
        "있으면 thin을 쓸 수 없다.",
        "출처 해설체('원문은…', '~를 소개합니다'), 전언체('~라고 합니다'), '자료에 없음'·'확인 필요' 문구, 근거 없는 "
        "수식어(최고·인기·아름다운·유명한·낭만 등)를 쓰지 않는다. 빈 정보의 '확인 필요'는 화면이 블록마다 한 번 붙인다.",
        "facts의 differs_from은 다른 출처의 값이다. 한쪽을 고르지 않는다 — 쓰려면 두 값을 다 적고 '방문 전 전화 확인'을 "
        "붙이거나 쓰지 않는다(relation 'also'는 함께 맞는 값).",
        "FAQ 질문은 존댓말 '~나요?/~인가요?'로 끝내고 장소 이름을 넣는다. 같은 질문을 여러 장소에 반복하지 않고, "
        "데이터로 답할 수 없는 질문은 만들지 않는다. 음식점·숙소는 2개 이하, 그 밖은 3개 이하. "
        "답의 source는 그 장소의 faq_sources 중 하나다.",
        "faq를 비우거나 빼면 기존 FAQ(current_faq)를 그대로 둔다. events·nearby는 참고용이다(행사 날짜는 요약에 쓰지 않는다).",
        "출력 형식은 output_example과 같다: {\"items\": [{id, summary, faq: [{q, a, source}], thin}]}.",
    ]


def read_only_list(path: Path) -> list[str]:
    """Ids (or slugs) from a text file (lines, commas or spaces; '#' starts a comment) or JSON (a list of strings or
    of {id}, or {"ids": [...]})."""
    text = path.read_text("utf-8")
    try:
        value = json.loads(text)
    except ValueError:
        words = re.split(r"[\s,]+", re.sub(r"#[^\n]*", "", text))
        return [w for w in words if w]
    if isinstance(value, dict):
        value = value.get("ids") or value.get("items") or []
    return [_text(v.get("id") if isinstance(v, dict) else v) for v in value or [] if v]


def prepare(data: Path, out: Path, batch: int = 12, only: list[str] | None = None) -> dict:
    city = load_city(data)
    places = load_json(data / "places.json", [])
    events = load_json(data / "events.json", [])
    if only is None:
        todo = [p for p in places if needs_summary(p, city=city)]
        unknown, skipped = [], []
    else:
        want = set(only)
        hit = [p for p in places if p.get("id") in want or p.get("slug") in want]
        found = {p.get("id") for p in hit} | {p.get("slug") for p in hit}
        unknown = sorted(want - found)
        skipped = sorted(p["id"] for p in hit if p.get("duplicate_of") or p.get("exclude"))
        todo = [p for p in hit if p["id"] not in skipped]
    def order(p: dict) -> tuple:   # one kind and one 구·군·동 together, so a writer sees neighbours side by side
        a = city.parse_address((p.get("facts") or {}).get("address"))
        return p.get("kind", ""), a.district, a.area, a.road, p["name"]
    todo.sort(key=order)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(INPUT_GLOB):
        old.unlink()
    size = max(1, batch)
    n = 0
    for i in range(0, len(todo), size):
        n += 1
        doc = {"rules": rules(city), "output_example": OUTPUT_EXAMPLE,
               "items": [fact_sheet(p, city=city, events=events) for p in todo[i:i + size]]}
        (out / f"places-{n:02d}.input.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"places": len(todo), "batches": n, "out": str(out), "unknown": unknown, "skipped": skipped}


# ------------------------------------------------------------------ checks
def _longest_copy(text: str, source: str, allowed: list[str]) -> str:
    """The first span of 15+ characters `text` shares with `source` that is not just names and fact values; '' when
    none. A span that is mostly an allowed word is cut out and the rest of the text searched again."""
    a, b = squash_ws(text), squash_ws(source)
    if not a or not b:
        return ""
    words = sorted({squash_ws(w) for w in allowed if squash_ws(w)}, key=len, reverse=True)
    sm = SequenceMatcher(None, "", b, autojunk=False)
    while True:
        sm.set_seq1(a)
        m = sm.find_longest_match(0, len(a), 0, len(b))
        if m.size < COPY_LIMIT:
            return ""
        span = rest = a[m.a:m.a + m.size]
        for word in words:
            rest = rest.replace(word, "")
        if len(re.sub(r"[\s.,·()]", "", rest)) >= COPY_LIMIT - 3:
            return span
        a = a[:m.a] + "\x00" + a[m.a + m.size:]


def _wording(text: str, names: tuple[str, ...] = ()) -> list[str]:
    for name in sorted((n for n in names if n), key=len, reverse=True):
        text = (text or "").replace(name, " ")
    return [f"{lbl}: …{m.group(0)}…" for pat, lbl in BANNED for m in [re.search(pat, text or "")] if m]


def _numbers(text: str) -> set[str]:
    return {x.lstrip("0") or "0" for x in re.findall(r"\d+", text or "")}


def _qkey(q: str) -> str:
    return re.sub(r"[\s?？.!]", "", squash_ws(q))


def check_item(item: dict, sheet: dict, *, city, place: dict | None = None) -> list[str]:
    """Problems of one written item against its fact sheet (and the current record, when given). [] when clean."""
    issues: list[str] = []
    name = sheet["name"]
    names = name_variants(name, sheet.get("alternate_names"), sheet.get("tourapi_title", ""))
    facts = sheet.get("facts") or []
    values = [f["value"] for f in facts] + [d["value"] for f in facts for d in f.get("differs_from") or []]
    allowed = names + name.split() + values
    known = _numbers(" ".join([*allowed, sheet.get("source_text", ""), sheet.get("category", ""),
                               sheet.get("district", ""), sheet.get("area", ""), sheet.get("road", "")]))
    sources = [sheet.get("source_text", "")]
    overview = squash_ws(((place or {}).get("tourapi") or {}).get("overview"))
    if overview and overview != sources[0]:
        sources.append(overview)

    summary = squash_ws(item.get("summary"))
    probe = {**(place or {"name": name}), "summary": summary}
    issues += [f"summary 색인 규칙 위반: {INDEX_REASONS[k]}" for k in summary_problems(probe, city=city)]
    sentences = summary_sentences(summary)
    if summary:
        if len(sentences) > SUMMARY_MAX_SENTENCES:
            issues.append(f"summary는 1~{SUMMARY_MAX_SENTENCES}문장(지금 {len(sentences)}문장)")
        issues += [f"summary 문장이 '다.'로 끝나지 않음: '{s}'" for s in sentences if not s.endswith("다.")]
        for alias in names:
            if alias != probe.get("name") and city.taut_rx(alias).match(sentences[0]):
                issues.append(f"summary 첫 문장이 상투구('{alias}' 이름으로): '{sentences[0]}'")
                break
    if item.get("thin") and [f for f in facts if f["key"] not in THIN_IGNORED]:
        issues.append(f"thin 표시는 {'·'.join(label(k) for k in THIN_IGNORED)} 말고 쓸 사실이 없을 때만")
    locks = set((place or {}).get("locks") or [])
    if "summary" in locks:
        issues.append("locks에 summary가 있어 바꾸지 않음")

    texts = [("summary", summary)]
    faqs = item.get("faq") or []
    if not isinstance(faqs, list):
        issues.append("faq는 [{q, a, source}] 목록이어야 함")
        faqs = []
    if faqs and "faq" in locks:
        issues.append("locks에 faq가 있어 바꾸지 않음")
    limit = FAQ_MAX.get(sheet.get("kind"), FAQ_MAX_DEFAULT)
    if len(faqs) > limit:
        kind = KIND_LABELS.get(sheet.get("kind"), sheet.get("kind") or "장소")
        issues.append(f"{kind} FAQ는 {limit}개 이하(지금 {len(faqs)}개)")
    squeezed = [n.replace(" ", "") for n in names]
    for i, f in enumerate(faqs):
        f = f if isinstance(f, dict) else {}
        q, a = squash_ws(f.get("q")), squash_ws(f.get("a"))
        texts += [(f"faq[{i}].q", q), (f"faq[{i}].a", a)]
        if not q or not a:
            issues.append(f"faq[{i}] q·a가 비어 있음")
        if q and not JONDAE.search(q):
            issues.append(f"faq[{i}].q 존댓말 의문형('~나요?/~인가요?')이 아님: {q}")
        if q and not any(n in q.replace(" ", "") for n in squeezed):
            issues.append(f"faq[{i}].q에 장소 이름이 없음(페이지 간 같은 질문 금지): {q}")
        if f.get("source") not in sheet.get("faq_sources", []):
            issues.append(f"faq[{i}].source는 {sheet.get('faq_sources')} 중 하나: {f.get('source')}")
    for where, text in texts:
        if not text:
            continue
        issues += [f"{where} {w}" for w in _wording(text, tuple(names))]
        for src in sources:
            span = _longest_copy(text, src, allowed)
            if span:
                issues.append(f"{where} source_text 복사 {len(span)}자: '{span}'")
                break
        unknown = sorted(_numbers(text) - known, key=int)
        if unknown:
            issues.append(f"{where} 사실표에 없는 숫자 {unknown}")
    return issues


def _items(doc) -> list | None:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("items"), list):
        return doc["items"]
    return None


def load_sheets(paths: list[Path], inputs: Path | None) -> tuple[dict, dict]:
    """(sheets by id, ids by input file) from the *.input.json files of `inputs` (default: each output's folder)."""
    folders = [inputs] if inputs else list(dict.fromkeys(p.resolve().parent for p in paths))
    sheets: dict[str, dict] = {}
    by_file: dict[Path, list[str]] = {}
    for folder in folders:
        for f in sorted(Path(folder).glob("*.input.json")):
            items = _items(load_json(f)) or []
            by_file[f.resolve()] = [i.get("id") for i in items if isinstance(i, dict)]
            for i in items:
                if isinstance(i, dict) and i.get("id"):
                    sheets.setdefault(i["id"], i)
    return sheets, by_file


def review(paths: list[Path], *, data: Path, inputs: Path | None = None, places: list[dict] | None = None) -> dict:
    """Check written outputs. {"rows": [{file, id, item, issues}], "problems": [file-level], "notes": [missing
    outputs, not blocking]}. Repeats: a question already used by another place in places.json or by an earlier item
    of these files is reported on the later item."""
    city = load_city(data)
    places = load_json(data / "places.json", []) if places is None else places
    by_id = {p.get("id"): p for p in places}
    sheets, by_file = load_sheets(paths, inputs)
    existing = {}
    for p in places:
        for f in p.get("faq") or []:
            existing.setdefault(_qkey(f.get("q")), p.get("id"))
    rows, problems, notes = [], [], []
    seen_q: dict[str, str] = {}
    seen_id: dict[str, str] = {}
    for path in paths:
        try:
            items = _items(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: 읽을 수 없음 — {exc}")
            continue
        if items is None:
            problems.append(f"{path.name}: {{\"items\": [...]}} 형식이 아님")
            continue
        paired = path.resolve().with_name(path.name.replace(".output.json", ".input.json"))
        own = {i.get("id"): i for i in _items(load_json(paired)) or [] if isinstance(i, dict)} if paired.exists() else {}
        for item in items:
            item = item if isinstance(item, dict) else {}
            pid = item.get("id")
            sheet = own.get(pid) or sheets.get(pid)
            row = {"file": path.name, "id": pid, "item": item, "issues": []}
            rows.append(row)
            if not sheet:
                row["issues"].append("입력 사실표에 없는 id")
                continue
            place = by_id.get(pid)
            if place is None:
                row["issues"].append("places.json에 없는 id")
            elif squash_ws(place.get("name")) != squash_ws(sheet["name"]):
                row["issues"].append(f"사실표 뒤 이름이 바뀜('{sheet['name']}' → '{place.get('name')}') — prepare를 다시")
            if pid in seen_id:
                row["issues"].append(f"같은 id가 {seen_id[pid]}에도 있음")
            seen_id.setdefault(pid, path.name)
            row["issues"] += check_item(item, sheet, city=city, place=place)
            mine = set()
            for f in item["faq"] if isinstance(item.get("faq"), list) else []:
                k = _qkey(f.get("q")) if isinstance(f, dict) else ""
                if not k:
                    continue
                if k in mine:
                    row["issues"].append(f"같은 질문이 두 번: {f.get('q')}")
                elif existing.get(k) not in (None, pid):
                    row["issues"].append(f"같은 질문이 places.json의 {existing[k]}에 있음: {f.get('q')}")
                elif seen_q.get(k) not in (None, pid):
                    row["issues"].append(f"같은 질문이 {seen_q[k]}에도 있음: {f.get('q')}")
                mine.add(k)
                seen_q.setdefault(k, pid)
        if paired.resolve() in by_file:
            got = {i.get("id") for i in items if isinstance(i, dict)}
            missing = [x for x in by_file[paired.resolve()] if x not in got]
            if missing:
                notes.append(f"{path.name}: 입력에 있으나 출력에 없는 id {len(missing)}개 — {', '.join(missing)}")
    return {"rows": rows, "problems": problems, "notes": notes}


def finding_lines(rep: dict) -> list[str]:
    return rep["problems"] + [f"{r['file']} {r['id']} {x}" for r in rep["rows"] for x in r["issues"]]


def check(paths: list[Path], *, data: Path, inputs: Path | None = None) -> list[str]:
    """Every finding as one line ('file id issue'); [] when all items are clean."""
    return finding_lines(review(paths, data=data, inputs=inputs))


# ------------------------------------------------------------------ merge
def apply_item(p: dict, item: dict) -> int:
    """Write one checked item into its record: summary, faq (a non-empty list replaces it), summary_auto off,
    summary_thin as marked. Nothing else is touched. Returns the number of FAQs written."""
    p["summary"] = squash_ws(item["summary"])
    p.pop("summary_auto", None)
    if item.get("thin"):
        p["summary_thin"] = True
    else:
        p.pop("summary_thin", None)
    faqs = item.get("faq") or []
    if faqs:
        p["faq"] = [{"q": squash_ws(f["q"]), "a": squash_ws(f["a"]), "source": squash_ws(f["source"])} for f in faqs]
    return len(faqs)


def merge(paths: list[Path], *, data: Path, inputs: Path | None = None, dry_run: bool = False) -> dict:
    pp = data / "places.json"
    raw = pp.read_bytes()
    places = json.loads(raw.decode("utf-8"))
    rep = review(paths, data=data, inputs=inputs, places=places)
    by_id = {p.get("id"): p for p in places}
    out = {"dry_run": dry_run, "merged": 0, "refused": 0, "faq": 0, "thin": 0, "merged_ids": [], "refused_items": [],
           "problems": rep["problems"], "notes": rep["notes"], "after_review": [], "written": None}
    for row in rep["rows"]:
        if row["issues"]:
            out["refused"] += 1
            out["refused_items"].append({"file": row["file"], "id": row["id"], "issues": row["issues"]})
            continue
        p = by_id[row["id"]]
        out["faq"] += apply_item(p, row["item"])
        out["thin"] += bool(row["item"].get("thin"))
        out["merged"] += 1
        out["merged_ids"].append(row["id"])
        if p.get("reviewed_at") or p.get("approved_at"):
            out["after_review"].append(row["id"])   # the reviewed text changed: a person looks again
    if out["merged"] and not dry_run:
        if pp.read_bytes() != raw:
            raise SystemExit(f"{pp}이 검사 중에 바뀌었습니다(다른 작업이 쓰는 중) — 아무것도 쓰지 않았습니다. 다시 실행하세요.")
        write_atomic(pp, dump(places))
        out["written"] = str(pp)
    return out


# ------------------------------------------------------------------ cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("prepare", help="작성자용 사실표 묶음을 만든다")
    a1.add_argument("--data", type=Path, required=True)
    a1.add_argument("--out", type=Path, required=True)
    a1.add_argument("--batch", type=int, default=12)
    a1.add_argument("--only", type=Path, help="장소 id(또는 slug) 목록 파일 — 텍스트 또는 JSON")
    for name, help_ in (("check", "작성 결과를 검사한다(문제가 있으면 종료 코드 1)"),
                        ("merge", "검사를 통과한 항목만 places.json에 반영한다")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--data", type=Path, required=True)
        s.add_argument("paths", nargs="+", type=Path)
        s.add_argument("--inputs", type=Path, help="사실표(*.input.json) 폴더 — 기본: 출력 파일이 있는 폴더")
        if name == "check":
            s.add_argument("--json", action="store_true", help="결과를 JSON으로")
        else:
            s.add_argument("--dry-run", action="store_true", help="쓰지 않고 결과만 보인다")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        only = read_only_list(a.only) if a.only else None
        print(json.dumps(prepare(a.data, a.out, a.batch, only), ensure_ascii=False))
        return 0
    if a.cmd == "check":
        rep = review(a.paths, data=a.data, inputs=a.inputs)
        lines = finding_lines(rep)
        if a.json:
            print(json.dumps({"ok": not lines, "items": len(rep["rows"]), "problems": rep["problems"],
                              "issues": [{"file": r["file"], "id": r["id"], "issues": r["issues"]}
                                         for r in rep["rows"] if r["issues"]], "notes": rep["notes"]},
                             ensure_ascii=False, indent=1))
        else:
            for line in lines + [f"참고: {n}" for n in rep["notes"]]:
                print(line)
            if not lines:
                print(f"OK — {len(rep['rows'])}개 항목 통과")
        return 1 if lines else 0
    res = merge(a.paths, data=a.data, inputs=a.inputs, dry_run=a.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if res["refused"] or res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
