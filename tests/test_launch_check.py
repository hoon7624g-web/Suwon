"""tools/launch_check.py: production 검증 오류 → 사람이 할 일, 색인 준비도, 질문 대상, 결정 대기. 임시 폴더에서만 빌드한다."""
import json
import shutil
import subprocess
from pathlib import Path

from pipeline import city as citymod
from tools import launch_check as lc

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CITY = citymod.from_site(json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8")))
SITE_ERRORS = [
    "[site.json] site_url이 최종 공개 주소가 아님: ",
    "[site.json] ga4_id 없음 — 신규 사이트 GA4 설치는 확정 사항",
    "[site.json] operator.contact(정정 요청 연락처) 없음",
    "[URL] 절대 주소 28건이 site_url(빈 값)로 시작하지 않음 — canonical·og 기준이어야 함 (예: /about/index.html canonical: /about/)",
]


def _sample(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    questions = tmp_path / "questions.csv"
    questions.write_text("id,question,related_pages\nN01,q1,경암동\nN16,q16,여행 안내(교통)\n", "utf-8-sig")
    return data, questions


def _snapshot(folder: Path) -> dict:
    return {p.name: p.read_bytes() for p in sorted(folder.glob("*.json"))}


def test_every_owner_setting_error_maps_to_a_concrete_action():
    actions = [lc.action_for(m.split("] ", 1)[1]) for m in SITE_ERRORS]
    assert "`site_url`" in actions[0] and "서브도메인" in actions[0]
    assert "`ga4_id`" in actions[1]
    assert "`operator.contact`" in actions[2]
    assert "다시 빌드" in actions[3]
    assert lc.action_for("실용 정보 없음 — 주소 외 방문 정보") .startswith("이 장소는 published로 바꾸지 않는다")
    assert lc.action_for("처음 보는 오류") == lc.FALLBACK_ACTION


def test_parse_and_group_validate_report(tmp_path):
    report = tmp_path / "qa.md"
    report.write_text("# QA 리포트\n\n## 오류\n" + "\n".join(f"- {x}" for x in SITE_ERRORS)
                      + "\n- [p-1 [백년가게]쌍용반점] 실용 정보 없음 — 02 표준\n- [p-2 동국사] 실용 정보 없음 — 02 표준\n"
                      "\n## 경고\n- 없음\n", "utf-8")
    errors, warnings = lc.parse_qa_report(report)
    assert errors[4] == ("p-1 [백년가게]쌍용반점", "실용 정보 없음 — 02 표준") and warnings == []
    groups = lc.group_errors(errors)
    assert [g["count"] for g in groups] == [1, 1, 1, 1, 2]
    assert groups[3]["message"].endswith("기준이어야 함")          # examples after '(예:' are dropped
    assert groups[4]["examples"] == ["p-1 [백년가게]쌍용반점", "p-2 동국사"]


def test_content_status_ignores_only_the_review_date():
    base = {"name": "동국사", "kind": "attraction", "facts": {"usetime": "09:00~18:00", "parking": "가능"},
            "summary": "동국사는 국내에 남은 유일한 일본식 사찰입니다. 입장료는 없습니다."}
    assert lc.content_status(base, city=SAMPLE_CITY) == (True, [])
    taut = {**base, "summary": "동국사는 군산시 금광동에 있는 사찰입니다."}     # the sample city's stock sentence
    ok, reasons = lc.content_status(taut, city=SAMPLE_CITY)
    assert not ok and reasons == [lc.INDEX_REASONS["taut"]]
    thin = {**base, "facts": {"usetime": "09:00~18:00"}}
    assert lc.content_status(thin, city=SAMPLE_CITY) == (False, [lc.INDEX_REASONS["groups"]])
    metro = citymod.from_site(json.loads((ROOT / "tests" / "fixtures" / "metro" / "site.json").read_text("utf-8")))
    district = {**base, "summary": "동국사는 중구 샘플로에 있는 사찰입니다."}    # a 구·군-level stock sentence (design 3.6)
    assert lc.content_status(district, city=metro) == (False, [lc.INDEX_REASONS["taut"]])


def test_checklist_with_fake_build_is_deterministic_and_writes_only_the_md(tmp_path, monkeypatch):
    data, questions = _sample(tmp_path)
    before = _snapshot(data)
    target = next(p for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("question_ids"))
    calls = []

    def fake(args):
        calls.append(args)
        assert args[args.index("--mode") + 1] == "production"
        if args[1] == "pipeline.build":
            Path(args[args.index("--out") + 1]).mkdir(parents=True)
            return subprocess.CompletedProcess(args, 0, "{}\n", "")
        src = Path(args[args.index("--data") + 1])
        report = Path(args[args.index("--report") + 1])
        if src.name == "rehearsal-data":   # temporary copy: everything published and reviewed
            for name in ("places", "guides", "courses", "events"):
                assert {r["status"] for r in json.loads((src / f"{name}.json").read_text("utf-8"))} == {"published"}
            assert json.loads((src / "site.json").read_text("utf-8"))["site_url"].startswith("https://")
            lines = [f"[{target['id']} {target['name']}] 실용 정보 없음 — 주소 외 방문 정보"]
        else:
            assert src == data.resolve()
            lines = [x for x in SITE_ERRORS]
        report.write_text("# QA\n\n## 오류\n" + "\n".join(f"- {x}" for x in lines) + "\n\n## 경고\n- 없음\n", "utf-8")
        return subprocess.CompletedProcess(args, 1, json.dumps({"sitemap_urls": 9}) + "\n", "")

    monkeypatch.setattr(lc, "_python", fake)
    md = tmp_path / "out" / "launch_checklist.md"
    assert lc.main(["--data", str(data), "--md", str(md), "--questions", str(questions)]) == 0
    text = md.read_text("utf-8")
    assert len(calls) == 4 and _snapshot(data) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "out", "questions.csv"]
    assert "production 검증 오류 4건 → 사람이 할 일 4가지" in text
    for needle in ("`site_url`에 최종 https 주소", "`ga4_id`", "`operator.contact`", "search_verification.google",
                   "search_verification.naver", "`indexnow_key`", "## 2. 색인 준비도", "## 3. 공개할 때 사람이 할 일",
                   "## 4. 사람이 정할 것", "글꼴 라이선스", "위키백과·위키데이터 sameAs", "지도 제공자", "overview",
                   "3유형(KOGL-3)", "`docs/rights.md`"):
        assert needle in text, needle
    # every command names the data folder it was given; no document outside this repository is cited
    assert f"python tools/make_review_sheet.py --data {data.resolve()}" in text
    assert f"python tools/refresh.py --data {data.resolve()}" in text and "tools/indexnow.py --data" in text
    assert "aeo_geo_spec" not in text and "03_prelaunch" not in text and "rights_request_draft" not in text
    assert "고객사 장소" not in text                               # operator.client_places is not configured
    assert f"`/places/{target['slug']}/` | 장소 | 미달 |" in text and "공개 시 검증 오류: 실용 정보 없음" in text
    assert "- N16: 여행 안내(교통)" in text                       # a question with no question_ids page
    assert "2026-" not in text.split("## 1.")[0]                  # no build date in the summary
    lc.main(["--data", str(data), "--md", str(md), "--questions", str(questions)])
    assert md.read_text("utf-8") == text                          # same data -> same file


def test_noindex_advice_follows_the_site_url_host():
    vercel = lc.noindex_advice("travel-city.vercel.app")
    assert "`travel-city.vercel.app`(vercel.app)이므로 이 호스트에서만 헤더를 빼고" in vercel
    assert "다른 `*.vercel.app` 배포 주소(미리보기·브랜치)는 noindex를 유지" in vercel
    own = lc.noindex_advice("travel.example.com")
    assert "공개 도메인 `travel.example.com`에서만" in own and "공개 도메인으로 301" in own
    assert "`site_url`을 정한 뒤" in lc.noindex_advice("")


def test_owner_rows_come_from_the_site_config(tmp_path):
    data, _ = _sample(tmp_path)
    site = json.loads((data / "site.json").read_text("utf-8"))
    places = json.loads((data / "places.json").read_text("utf-8"))
    site["operator"] = {**site.get("operator", {}), "client_places": [places[1]["name"][:3]]}
    site["site_url"] = "https://travel-city.vercel.app"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    R = lc.readiness(data)
    O = lc.owner_state(data, R)
    assert O["host"] == "travel-city.vercel.app" and O["city_node"].startswith("#")
    assert O["clients"] == [places[1]["name"]]
    rows = {a: (b, c) for a, b, c in lc.owner_rows(O)}
    assert rows["고객사 장소 노출과 관계 표시"][0] == f"장소 데이터에 있음: {places[1]['name']}"
    assert f"{site['locality']} 위키백과·위키데이터 sameAs" in rows
    assert f"{site['source']['name']} 원문·사진 이용 범위" in rows
    items = "\n".join(lc.launch_items({**O, "data": "data/x"}, R, {"stats": {}}))
    assert "`travel-city.vercel.app`(vercel.app)이므로" in items and "python tools/refresh.py --data data/x" in items


def test_real_production_build_on_sample(tmp_path):
    """The real build/validate (no network) — guards the report format the checklist parses."""
    data, questions = _sample(tmp_path)
    text = lc.run(data, None, questions)
    assert "| 1 | [site.json] site_url이 최종 공개 주소가 아님" in text
    assert "`ga4_id`에 넣는다" in text
    assert "## 2. 색인 준비도" in text and "| 장소 |" in text
