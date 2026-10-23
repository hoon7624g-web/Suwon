"""Report fixed-question evidence coverage using stored originals only.

    python tools/question_coverage.py --data data/daegu --questions measurement/questions.csv \\
        --rules measurement/question_rules.json

This is a review aid, not generated travel advice or a publication approval.
It never fetches pages, changes questions/data, or treats a place-name match as
proof of hours, transport, indoor access, price or accommodation suitability.

What a question needs is data written with the city's question set, not code: the
rules JSON names the question groups to check and, per question ID, the places it
is about and its evidence steps, run in order.

    {"groups": {"N": 30, "P": 3},
     "questions": {"N01": {"names": ["<장소 이름>"], "steps": [
         {"do": "text", "pattern": "<정규식>", "facet": "<근거 설명>", "id": "desc"},
         {"do": "missing", "text": "<늘 남는 확인 항목>"},
         {"do": "missing", "text": "<근거가 없을 때 남는 항목>", "unless": "desc"}]}}}

`in` picks the records a step reads: "selected" (the named places and documents,
the default), "sources" (every place and saved document), "documents", or
{"from": one of those, "kind", "name_any", "name_all", "names", "text_all"}.
- text: original text matching `pattern` is evidence (an exact excerpt); `if_none` when nothing matched.
- fact: facts.<field> recorded by TourAPI or by the site's own source (site.json source.name).
- any: the first of `steps` that finds evidence; `if_none` when none did.
- courses: stored courses whose source page (last URL path segment) is in `pages`; a missing course gives
  `if_none`; `need_text` words must all appear in one of them, else `if_lacking`.
- course_stops: courses in `pages` whose stops name every word of `tokens`.
- conflict: a source table value labelled `label` with times the body text lacks: `missing`, the value as evidence.
- samples: saved period-limited notices (sample_review.json) matching `pattern`.
- missing: `text` always, or only `if` / `unless` the step with that `id` found evidence.
A question without rules keeps "이 질문의 직접 답변 근거" as missing. A collected course that is not imported gets
the report locator '<id_prefix>-course-<page>-<n>' (site.json id_prefix), never a stored slug.
Raw material (optional): data/raw/<id_prefix>/ (static_documents.json, details_crawl.json, sample_review.json) and
its collected courses (tools/rights_report.raw_courses_file).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.rights_report import raw_courses_file

TOURAPI_PROVIDER = "한국관광공사 TourAPI"
NO_RULE = "이 질문의 직접 답변 근거"
TIME = re.compile(r"\d{1,2}:\d{2}")
GROUP_TITLES = {"N": "핵심", "P": "플랫폼 제외"}
# step kind -> keys it needs
STEPS = {"text": ("pattern", "facet"), "fact": ("field", "facet"), "any": ("steps",), "courses": ("pages",),
         "course_stops": ("pages", "tokens", "facet"), "conflict": ("label", "facet", "missing"),
         "samples": ("pattern", "facet"), "missing": ("text",)}
SCOPES = ("selected", "sources", "documents")


def rules_problems(rules) -> list[str]:
    """What is wrong with a rules object (empty when it can be used)."""
    if not isinstance(rules, dict):
        return ["규칙은 JSON 객체여야 합니다"]
    out = []
    groups = rules.get("groups")
    if not (isinstance(groups, dict) and groups
            and all(isinstance(g, str) and g and isinstance(n, int) and n > 0 for g, n in groups.items())):
        out.append("groups: {\"군\": 문항 수} 객체여야 합니다")
    questions = rules.get("questions", {})
    if not isinstance(questions, dict):
        return out + ["questions: {질문 ID: 규칙} 객체여야 합니다"]

    def check(step, where: str) -> None:
        kind = step.get("do") if isinstance(step, dict) else None
        if kind not in STEPS:
            out.append(f"{where}: do 값 오류 {kind!r} (허용: {', '.join(STEPS)})")
            return
        out.extend(f"{where}: {kind}에 {key} 없음" for key in STEPS[kind] if not step.get(key))
        if step.get("pattern"):
            try:
                re.compile(step["pattern"])
            except re.error as exc:
                out.append(f"{where}: pattern 정규식 오류 {exc}")
        scope = step.get("in", "selected")
        origin = scope if isinstance(scope, str) else scope.get("from", "selected") if isinstance(scope, dict) else None
        if origin not in SCOPES:
            out.append(f"{where}: in 값 오류 {scope!r} (from: {', '.join(SCOPES)})")
        subs = (step.get("steps") or []) if kind == "any" else []
        for i, sub in enumerate(subs):
            check(sub, f"{where}.steps[{i}]")

    for ident, rule in questions.items():
        if (not isinstance(rule, dict) or not isinstance(rule.get("steps", []), list)
                or not all(isinstance(n, str) for n in rule.get("names", [])) or isinstance(rule.get("names"), str)):
            out.append(f"{ident}: {{names: [장소 이름], steps: [단계]}} 객체여야 합니다")
            continue
        for i, step in enumerate(rule.get("steps", [])):
            check(step, f"{ident}.steps[{i}]")
    return out


def load_rules(path: Path) -> dict:
    rules = json.loads(path.read_text("utf-8"))
    problems = rules_problems(rules)
    if problems:
        raise ValueError(f"{path}: 규칙 오류\n" + "\n".join(f"  - {p}" for p in problems))
    return rules


def _normalized(name):
    # Only identity lookup uses normalization; quoted source text remains unchanged.
    return re.sub(r"\s", "", name)


def _excerpt(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    if end < 0:
        end = len(text)
    # Keep a continuation line when the original is wrapped mid-sentence.
    while end < len(text) and end - start < 1200 and not text[start:end].rstrip().endswith((".", "다", "요")):
        following = text.find("\n", end + 1)
        if following < 0:
            following = len(text)
        if not text[end + 1:following].strip():
            break
        end = following
    return text[start:end]


def source_documents(records: list[dict], source_type: str) -> list[dict]:
    """Represent saved source material without inventing public page slugs."""
    return [{"name": r.get("name", ""), "slug": "", "source_type": source_type,
             "kind": r["candidate_kinds"][0] if len(r.get("candidate_kinds", [])) == 1 else "",
             "source_fields": r.get("source_fields", []),
             "original": {"text": r.get("original_text", ""), "source_url": r.get("source_url", ""),
                          "license": r.get("original_license", "UNKNOWN")}}
            for r in records if r.get("original_text", "").strip()]


def course_candidates(raw_courses: list[dict], imported: list[dict] | None = None, id_prefix: str = "") -> list[dict]:
    counters: dict[str, int] = {}
    results = []
    locator = f"{id_prefix}-course" if id_prefix else "course"
    for raw in raw_courses:
        source = raw.get("source_url") or raw.get("original", {}).get("source_url", "")
        page = urlsplit(source).path.rsplit("/", 1)[-1]
        counters[page] = counters.get(page, 0) + 1
        matched = [c for c in imported or [] if c.get("name") == raw.get("name")
                   and (c.get("original", {}).get("source_url") or c.get("source_url")) == source]
        # An unregistered course gets a report locator, never a stored slug.
        slug = matched[0]["slug"] if len(matched) == 1 else f"{locator}-{page}-{counters[page]}"
        results.append({**raw, "slug": slug, "slug_registered": len(matched) == 1, "source_page": page})
    return results


def _scope(spec, selected: list[dict], sources: list[dict], documents: list[dict]) -> list[dict]:
    """The records a step reads (see the module docstring, `in`)."""
    spec = {"from": spec} if isinstance(spec, str) else dict(spec or {})
    base = {"selected": selected, "sources": sources, "documents": documents}[spec.get("from", "selected")]
    names = {_normalized(n) for n in spec.get("names") or ()}
    out = []
    for item in base:
        name, text = item.get("name", ""), item.get("original", {}).get("text", "")
        if ((spec.get("kind") and item.get("kind") != spec["kind"])
                or (spec.get("name_any") and not any(w in name for w in spec["name_any"]))
                or any(w not in name for w in spec.get("name_all") or ())
                or (names and _normalized(name) not in names)
                or any(w not in text for w in spec.get("text_all") or ())):
            continue
        out.append(item)
    return out


def assess_question(question: dict, places: list[dict], courses: list[dict],
                    samples: list[dict] | None = None, documents: list[dict] | None = None, *,
                    rules: dict, source_name: str = "") -> dict:
    """Run the question's steps from `rules` (see the module docstring). source_name: the site's own source
    (site.json source.name), whose recorded facts count as evidence next to TourAPI's."""
    ident = question["id"]
    result = {"id": ident, "group": question["group"], "question": question["question"],
              "candidate_slugs": [], "evidence": [], "missing": [], "answer_status": "미확인"}
    documents = documents or []
    sources = places + documents
    rule = (rules.get("questions") or {}).get(ident)
    named = {_normalized(name) for name in (rule or {}).get("names") or ()}
    selected = [p for p in sources if _normalized(p.get("name", "")) in named]
    trusted = {TOURAPI_PROVIDER, source_name} - {""}

    def candidate(item):
        slug = item.get("slug", "")
        if slug and slug not in result["candidate_slugs"]:
            result["candidate_slugs"].append(slug)

    for item in selected:
        candidate(item)

    def add_text(items, pattern, facet):
        count = 0
        for item in items:
            original = item.get("original", {})
            quote = _excerpt(original.get("text", ""), pattern)
            if quote is None:
                continue
            candidate(item)
            evidence = {"slug": item.get("slug", ""), "name": item.get("name", ""),
                        "source_url": original.get("source_url", ""),
                        "quote": quote, "facet": facet, "license": original.get("license", "UNKNOWN"),
                        "source_type": item.get("source_type", "registered_original"),
                        "slug_registered": bool(item.get("slug"))}
            if not any(e["source_url"] == evidence["source_url"] and e["quote"] == quote
                       for e in result["evidence"]):
                result["evidence"].append(evidence)
            count += 1
        return count

    def add_fact(items, field, facet):
        count = 0
        for item in items:
            value = item.get("facts", {}).get(field)
            provider = item.get("facts_source", {}).get("provider", "")
            if not value or provider not in trusted:
                continue
            candidate(item)
            fact_source_url = item.get("facts_source", {}).get("source_url", "")
            if not fact_source_url and provider == source_name:   # the site's own source: its original page
                fact_source_url = item.get("original", {}).get("source_url", "")
            result["evidence"].append({"slug": item.get("slug", ""), "name": item.get("name", ""),
                                       "source_url": fact_source_url,
                                       "quote": str(value), "facet": facet, "license": "UNKNOWN",
                                       "source_type": "sourced_facts", "source_field": "facts." + field,
                                       "provider": provider, "slug_registered": bool(item.get("slug"))})
            count += 1
        return count

    def add_courses(pages, facet):
        found = []
        for course in courses:
            if course.get("source_page") not in pages or not course.get("stops"):
                continue
            text = course.get("original", {}).get("text", "")
            if not text.strip():
                continue
            candidate(course)
            result["evidence"].append({"slug": course["slug"], "name": course.get("name", ""),
                                       "source_url": course.get("source_url") or course.get("original", {}).get("source_url", ""),
                                       "quote": text[:600], "facet": facet,
                                       "license": course.get("original", {}).get("license", "UNKNOWN")})
            found.append(course)
        return found

    def add_course_stops(pages, tokens, facet):
        count = 0
        for c in courses:
            if c.get("source_page") not in pages or not all(any(token in s.get("name", "") for s in c.get("stops", []))
                                                           for token in tokens):
                continue
            candidate(c)
            original = c.get("original", {})
            result["evidence"].append({"slug": c["slug"], "name": c.get("name", ""),
                                       "source_url": c.get("source_url", ""), "quote": original.get("text", "")[:600],
                                       "facet": facet, "license": original.get("license", "UNKNOWN")})
            count += 1
        return count

    def add_conflicts(items, label, facet, missing):
        count = 0
        for item in items:
            body_times = set(TIME.findall(item.get("original", {}).get("text", "")))
            for field in item.get("source_fields", []):
                field_times = set(TIME.findall(field.get("value", "")))
                if field.get("label") == label and body_times and field_times - body_times:
                    result["missing"].append(missing)
                    result["evidence"].append({"slug": item.get("slug", ""), "name": item.get("name", ""),
                                               "source_url": item.get("original", {}).get("source_url", ""),
                                               "quote": field["value"], "facet": facet,
                                               "license": item.get("original", {}).get("license", "UNKNOWN"),
                                               "source_type": "raw_source_field", "source_field": "source_fields." + label})
                    count += 1
        return count

    def add_samples(pattern, facet):
        count = 0
        for sample in samples or []:
            quote = _excerpt(sample.get("original_text", ""), pattern)
            if quote is not None:
                result["evidence"].append({"slug": "", "name": sample.get("name", ""),
                                           "source_url": sample.get("source_url", ""),
                                           "quote": quote, "facet": facet,
                                           "license": sample.get("original_license", "UNKNOWN")})
                count += 1
        return count

    found: dict[str, int] = {}

    def run(step) -> int:
        kind = step["do"]
        items = lambda: _scope(step.get("in"), selected, sources, documents)
        count = 0
        if kind == "missing":
            if ("if" in step and not found.get(step["if"])) or ("unless" in step and found.get(step["unless"])):
                return 0
            result["missing"].append(step["text"])
            return 0
        if kind == "text":
            count = add_text(items(), step["pattern"], step["facet"])
        elif kind == "fact":
            count = add_fact(items(), step["field"], step["facet"])
        elif kind == "any":
            for sub in step["steps"]:
                count = run(sub)
                if count:
                    break
        elif kind == "courses":
            available = add_courses(set(step["pages"]), step.get("facet") or "코스 순서")
            count = len(available)
            need = step.get("need_text") or ()
            if available and need and not any(all(w in c["original"]["text"] for w in need) for c in available):
                result["missing"].append(step.get("if_lacking") or "필요한 일차·구간의 직접 근거")
        elif kind == "course_stops":
            count = add_course_stops(set(step["pages"]), step["tokens"], step["facet"])
        elif kind == "conflict":
            count = add_conflicts(items(), step["label"], step["facet"], step["missing"])
        elif kind == "samples":
            count = add_samples(step["pattern"], step["facet"])
        if not count and step.get("if_none"):
            result["missing"].append(step["if_none"])
        if step.get("id"):
            found[step["id"]] = count
        return count

    if rule is None:
        result["missing"].append(NO_RULE)
    for step in (rule or {}).get("steps") or []:
        run(step)
    if result["evidence"]:
        result["answer_status"] = "일부" if result["missing"] else "답충분"
    # Suggestions without direct answer evidence must never become '답충분'.
    return result


def guide_candidates(places: list[dict], courses: list[dict], documents: list[dict] | None = None) -> list[dict]:
    sources = places + (documents or [])

    def candidates(pattern, *, kind=None, reject=None):
        found, seen = [], set()
        for place in sources:
            original = place.get("original", {})
            text = original.get("text", "")
            if kind and place.get("kind") != kind:
                continue
            quote = _excerpt(text, pattern)
            if quote is None or (reject and re.search(reject, quote)):
                continue
            key = original.get("source_url", ""), quote
            if key in seen:
                continue
            seen.add(key)
            found.append({"slug": place.get("slug", ""), "name": place.get("name", ""),
                          "source_url": key[0], "quote": quote})
        return found

    children = candidates("어린이.{0,20}체험|아동.{0,20}체험|어린이박물관")
    indoor = candidates("실내.{0,15}(?:전시|체험|관광)", reject="(?:않|불가|금지|중단)")
    stays = candidates("독채", kind="stay")
    transit = candidates("(?:시내버스|대중교통|도보).{0,50}(?:이용|접근|진입|탑승)")
    return [
        {"name": "차 없는 당일여행", "candidates": transit, "missing": "현재 대중교통·도보 접근 및 출발지·환승 확인 필요. 당일 코스만으로 무차량 여행을 단정하지 않음."},
        {"name": "아이와 함께", "candidates": children, "missing": "체험연령·유모차·보호자 동반 조건. 후보 등록과 가이드 본문 작성은 별도 검수."},
        {"name": "비 오는 날", "candidates": indoor, "missing": "현재 개방·우천 접근 조건 확인 필요. 실내 이용 언급은 우천 적합성 확정이 아님."},
        {"name": "독채 숙소 고르기", "candidates": stays, "missing": "독채 적용 객실·현재 영업·업주 확인 필요. 코스의 '숙소'·관광호텔 언급으로 대체하지 않음."},
    ]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", "").replace("\n", " ")


def coverage_markdown(results: list[dict], place_count: int, course_count: int,
                      groups: dict[str, int] | None = None) -> str:
    if groups is None:   # the groups in the order the results have them
        groups = {}
        for r in results:
            groups[r["group"]] = groups.get(r["group"], 0) + 1
    lines = ["# 고정 질문군 원문 근거 점검", "",
             f"입력: 저장된 장소 원문 {place_count}건, 코스 원문 {course_count}건. 질문 CSV와 데이터는 변경하지 않았습니다.", "",
             "`답충분`은 질문에 필요한 최소 원문 근거가 있다는 뜻입니다. 검수·이용조건·공개·색인·실제 AI 인용을 통과했다는 뜻이 아닙니다. `일부`는 관련 원문은 있지만 질문 전체를 답할 근거가 부족한 상태, `미확인`은 직접 답변 근거를 찾지 못한 상태입니다.", "",
             "장소·코스 이름의 단순 일치, 코스에서 언급한 시설명, 요약·FAQ 문장은 답변 근거로 사용하지 않습니다. "
             f"{'/'.join(groups)}군을 따로 세고, 그 밖의 군은 이 점검에서 제외했습니다.", ""]
    lines.extend(["별도 정적 안내·수집 문서는 보조 근거입니다. slug가 없는 문서는 공개 페이지가 등록되지 않은 상태이며, 시티투어 안내나 기간 한정 공지의 존재를 현재 운행 확인으로 취급하지 않습니다.", ""])
    for group, count in groups.items():
        title = " ".join(x for x in (group, GROUP_TITLES.get(group, ""), f"{count}문항") if x)
        rows = [r for r in results if r["group"] == group]
        counts = {status: sum(r["answer_status"] == status for r in rows) for status in ("답충분", "일부", "미확인")}
        lines.extend([f"## {title}", "", " / ".join(f"{status} {number}건" for status, number in counts.items()), "",
                      "| ID | 질문 | 후보 slug | 원문 근거 | 부족한 데이터 |", "| --- | --- | --- | --- | --- |"])
        for r in rows:
            lines.append("| " + " | ".join(_cell(str(v)) for v in (r["id"], r["question"], ", ".join(r["candidate_slugs"]) or "없음", r["answer_status"], "; ".join(r["missing"]) or "질문 수준의 최소 원문 근거 있음")) + " |")
        lines.append("")
    lines.extend(["## 원문 근거 발췌(검수용)", "", "아래 문구는 저장된 `original.text`·보조 자료의 `original_text`에서 가져온 연속 부분 문자열입니다. 출처가 기록된 주소 등은 `sourced_facts`와 필드 경로로 별도 표시합니다. 원문은 수정하지 않았으며 긴 코스는 앞부분만 발췌했습니다. 원문 전체의 공개 가능 여부는 권리 리포트로 별도 판단해야 합니다.", ""])
    for r in results:
        for e in r["evidence"]:
            lines.extend([f"### {r['id']} / {e['slug'] or '공개 페이지 slug 미등록 원문'} / {e['facet']}", "", f"자료명: {e['name']}", "", f"출처: {e['source_url']} · 원문 이용조건: {e['license']}",
                          f"근거 유형: {e.get('source_type', 'original')} {e.get('source_field', '')}", "", "```text", e["quote"], "```", ""])
    return "\n".join(lines)


def guide_markdown(guides: list[dict]) -> str:
    lines = ["# 가이드 4종 후보 검토", "", "가이드 본문은 작성하지 않았습니다. 저장된 장소·코스 원문에서 직접 확인할 수 있는 후보와 정확한 원문 발췌만 기록합니다. 후보는 게재 승인이나 완성된 여행 추천이 아닙니다.", ""]
    for guide in guides:
        lines.extend([f"## {guide['name']}", "", f"후보: {', '.join(c['slug'] or c['name'] + ' (공개 페이지 slug 없음)' for c in guide['candidates']) or '없음(근거 미확인)'}", "", f"부족한 데이터: {guide['missing']}", ""])
        for c in guide["candidates"]:
            lines.extend([f"{c['name']} · {c['source_url']}", "", "```text", c["quote"], "```", ""])
    return "\n".join(lines)


def run(questions_path: Path, data: Path, raw_courses_path: Path | None, reports: Path, *, rules: dict,
        out: Path | None = None, guides_out: Path | None = None,
        sample_review_path: Path | None = None, raw_dir: Path | None = None) -> list[dict]:
    """rules: a rules object (load_rules). Optional site.json in `data` gives id_prefix (raw folder, course
    locators) and source.name (the site's own source for recorded facts)."""
    problems = rules_problems(rules)
    if problems:
        raise ValueError("규칙 오류: " + "; ".join(problems))
    groups = rules["groups"]
    with questions_path.open(encoding="utf-8-sig", newline="") as f:
        questions = [q for q in csv.DictReader(f) if q.get("group") in groups]
    expected = {f"{g}{i:02d}" for g, n in groups.items() for i in range(1, n + 1)}
    if len(questions) != len(expected) or {q["id"] for q in questions} != expected:
        label = "/".join(f"{g}{n}" for g, n in groups.items())
        raise ValueError(f"Expected the fixed {label} question IDs without duplicates")
    site_path = data / "site.json"
    site = json.loads(site_path.read_text("utf-8")) if site_path.exists() else {}
    id_prefix = str(site.get("id_prefix") or "").strip()
    source_name = str((site.get("source") or {}).get("name") or "").strip()
    places = json.loads((data / "places.json").read_text("utf-8"))
    raw = json.loads(raw_courses_path.read_text("utf-8")) if raw_courses_path and raw_courses_path.exists() else []
    imported_path = data / "courses.json"
    imported = json.loads(imported_path.read_text("utf-8")) if imported_path.exists() else []
    raw_keys = {(c.get("name"), c.get("original", {}).get("source_url") or c.get("source_url")) for c in raw}
    raw = raw + [c for c in imported if (c.get("name"), c.get("original", {}).get("source_url")) not in raw_keys]
    courses = course_candidates(raw, imported, id_prefix)
    source_dir = raw_dir or (raw_courses_path.parent / id_prefix if raw_courses_path and id_prefix else None)
    sample_path = sample_review_path or (source_dir / "sample_review.json" if source_dir else None)
    samples = json.loads(sample_path.read_text("utf-8")).get("samples", []) if sample_path and sample_path.exists() else []
    documents = []
    for filename, key, label in (("static_documents.json", "documents", "static_source"),
                                 ("details_crawl.json", "records", "raw_detail_source")):
        path = source_dir / filename if source_dir else None
        if path and path.exists():
            documents.extend(source_documents(json.loads(path.read_text("utf-8")).get(key, []), label))
    results = [assess_question(q, places, courses, samples, documents, rules=rules, source_name=source_name)
               for q in questions]
    coverage_path = out or reports / "question_coverage.md"
    guides_path = guides_out or reports / "guide_candidates.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    guides_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(coverage_markdown(results, len(places), len(courses), groups), "utf-8")
    guides_path.write_text(guide_markdown(guide_candidates(places, courses, documents)), "utf-8")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="도시 데이터 폴더(예: data/daegu)")
    parser.add_argument("--questions", type=Path, default=Path("measurement/questions.csv"))
    parser.add_argument("--rules", type=Path, help="질문별 점검 규칙 JSON(기본: 질문표 옆 question_rules.json)")
    parser.add_argument("--raw", type=Path, help="수집 원자료 폴더(기본: data/raw/<site.json id_prefix>)")
    parser.add_argument("--raw-courses", type=Path,
                        help="미수입 수집 코스 JSON(기본: --raw 폴더의 courses.json, 없으면 그 옆 <폴더 이름>_courses.json)")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--guides-out", type=Path)
    parser.add_argument("--sample-review", type=Path, help="Optional saved detail samples (the samples step reads them)")
    args = parser.parse_args(argv)
    rules_path = args.rules or args.questions.parent / "question_rules.json"
    if not rules_path.exists():
        parser.error(f"규칙 파일이 없습니다: {rules_path} — 질문표와 함께 --rules로 주세요")
    site_path = args.data / "site.json"
    id_prefix = str((json.loads(site_path.read_text("utf-8")) if site_path.exists() else {}).get("id_prefix") or "")
    raw_dir = args.raw or (Path("data/raw") / id_prefix if id_prefix else None)
    raw_courses_path = args.raw_courses or (raw_courses_file(raw_dir) if raw_dir else None)
    try:
        rules = load_rules(rules_path)
        results = run(args.questions, args.data, raw_courses_path, args.reports, rules=rules,
                      out=args.out, guides_out=args.guides_out,
                      sample_review_path=args.sample_review or (raw_dir / "sample_review.json" if raw_dir else None),
                      raw_dir=raw_dir)
    except (ValueError, OSError) as exc:
        print(f"질문 점검 거부: {exc}", file=sys.stderr)
        return 1
    groups = rules["groups"]
    print(json.dumps({group: {status: sum(r["group"] == group and r["answer_status"] == status for r in results)
                             for status in ("답충분", "일부", "미확인")} for group in groups}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
