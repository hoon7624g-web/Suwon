"""검수 시트 생성(make_review_sheet)과 반영(apply_review): OK 행만 reviewed, 나머지는 한 글자도 안 바뀐다."""
import csv
import difflib
import json
from pathlib import Path

import pytest

from pipeline.slugs import is_slug
from tools import apply_review, make_review_sheet
from tools.make_review_sheet import HEADERS, make_rows

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-20"
BASE = "https://review.example"      # the fixture site.json site_url: the sheet's default preview address


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def site_json(root: Path, source: Path = ROOT / "data" / "sample" / "site.json", **changes) -> None:
    site = json.loads(source.read_text("utf-8"))
    site.update({"site_url": BASE, **changes})
    write(root / "site.json", site)


def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    site_json(root)                   # sample config: slug_policy.collision = number
    src = {"provider": "샘플시 문화관광", "checked_at": "2026-10-08"}
    write(root / "places.json", [
        {"id": "p0", "name": "같은 이름", "kind": "attraction", "tier": "basic", "status": "draft"},
        {"id": "p1", "name": "같은 이름", "kind": "attraction", "tier": "full", "status": "draft",
         "summary": "같은 이름은 전시 12개를 둔 박물관입니다. 둘째 문장.",
         "facts": {"address": "샘플시 어딘가  1", "usetime": "09:00~18:00", "parking": "가능", "accessible_toilet": "있음"},
         "facts_source": src,
         "fact_sources": {"usetime": {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-08", "contentid": "111",
                                      "confirmed_by": "샘플시 문화관광 2026-10-08"}},
         "fact_alternatives": {"parking": [{"value": "불가", "provider": "한국관광공사 TourAPI"}]},
         "original": {"source_url": "https://www.city.example/tour/p1"},
         "official": {"source_url": "https://www.city.example/tour/p1", "homepage": "https://museum.example"},
         "tourapi": {"contentid": "111"}},
        {"id": "p2", "slug": "ga-jangso", "name": "가 장소", "kind": "attraction", "tier": "full", "status": "published",
         "reviewed_at": "2026-10-01", "facts": {}, "facts_source": src},
        {"id": "p3", "slug": "dup", "name": "가 장소", "kind": "attraction", "tier": "full", "status": "draft",
         "duplicate_of": "p2"},
        {"id": "p4", "name": "basic", "kind": "food", "tier": "basic", "status": "draft"},
    ])
    write(root / "guides.json", [
        {"id": "g1", "title": "비 오는 날", "status": "reviewed", "reviewed_at": "2026-10-02", "summary": "실내 세 곳입니다.",
         "items": [{"place_slug": "gateun-ireum-2", "reason": "실내"}, {"name": "없는 곳", "reason": "x"}],
         "sources": [{"name": "s", "url": "https://www.city.example/tour/g"}], "body": [], "faq": []},
        {"id": "g2", "slug": "plan", "title": "계획만", "status": "draft", "items": [], "body": []},
    ])
    write(root / "courses.json", [
        {"id": "c1", "name": "1코스 | 근대", "status": "draft", "summary": "",
         "stops": [{"name": "가 장소", "place_slug": "ga-jangso"}, {"name": "숙소\n(자유)", "place_slug": ""}],
         "original": {"source_url": "https://www.city.example/tour/c"}},
    ])
    write(root / "events.json", [
        {"id": "e2", "name": "매년 행사", "status": "draft", "period_text": "매년  음력 7월", "start_date": "", "end_date": "",
         "place_name": "샘플시  성산면", "source_url": "https://www.city.example/tour/e2", "contentid": ""},
        {"id": "e1", "name": "축제", "status": "draft", "period_text": "", "start_date": "2026-10-09", "end_date": "2026-10-11",
         "place_name": "백년광장", "source_url": "https://www.city.example/tour/e1", "contentid": "999"},
    ])
    return root


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def save_csv(path: Path, rows: list[dict], encoding: str = "utf-8-sig") -> None:
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def snapshot(data: Path) -> dict:
    return {p.name: p.read_text("utf-8") for p in sorted(data.glob("*.json"))}


# --- make_review_sheet ---------------------------------------------------------------------------

def test_sheet_targets_columns_and_facts(tmp_path):
    data = dataset(tmp_path)
    before = snapshot(data)
    out = tmp_path / "sheet.csv"
    assert make_review_sheet.main(["--data", str(data), "--out", str(out)]) == 0
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
    rows = read_csv(out)
    assert tuple(rows[0]) == HEADERS
    assert [(r["구분"], r["ID"]) for r in rows] == [
        ("장소", "p2"), ("장소", "p1"),                       # full only, no duplicate_of, sorted by name
        ("가이드", "g1"), ("가이드", "g2"), ("코스", "c1"),
        ("행사", "e1"), ("행사", "e2")]                       # dated events first, like the events page
    p1 = rows[1]
    # slug derived like pipeline.build (pipeline.slugs.assign_slugs): records without a slug in id order, so p0
    # took "gateun-ireum" and p1 got the number (sample slug_policy "number"); the base is the site.json site_url
    assert p1["미리보기 URL"] == f"{BASE}/places/gateun-ireum-2/"
    facts = p1["핵심 사실"].splitlines()
    assert facts[0] == "같은 이름은 전시 12개를 둔 박물관입니다."
    assert "주소: 샘플시 어딘가 1 (샘플시 문화관광)" in facts                      # provider falls back to facts_source
    assert "이용시간: 09:00~18:00 (한국관광공사 TourAPI; 일치 확인 샘플시 문화관광 2026-10-08)" in facts
    assert "  └ 다른 출처 값: 불가 (한국관광공사 TourAPI)" in facts
    assert "데이터 없음: 쉬는 날·이용요금·문의" in facts
    assert not any("장애인" in line for line in facts)
    assert p1["출처 링크"].splitlines() == ["https://www.city.example/tour/p1", "https://museum.example", "TourAPI contentid 111"]
    assert p1["현재 상태"] == "draft (reviewed_at 없음)" and rows[0]["현재 상태"] == "published (reviewed_at 2026-10-01)"
    assert all(r["판정"] == "" and r["메모"] == "" for r in rows)
    g1, g2, c1, e1, e2 = rows[2:]
    assert "추천 장소 2곳: 같은 이름, 없는 곳(연결 없음)" in g1["핵심 사실"]
    assert g1["미리보기 URL"] == f"{BASE}/guides/bi-oneun-nal/"
    assert "본문이 없어 미리보기에 없음" in g2["미리보기 URL"]
    assert c1["미리보기 URL"] == f"{BASE}/courses/1-koseu-geundae/"
    assert "경유지 2곳 · 장소 연결 1곳" in c1["핵심 사실"] and "연결 안 된 경유지: 숙소 (자유)" in c1["핵심 사실"]
    assert e1["핵심 사실"] == "기간: 2026-10-09 ~ 2026-10-11\n장소: 백년광장"
    assert e1["출처 링크"] == "https://www.city.example/tour/e1\nTourAPI contentid 999"
    assert e2["핵심 사실"].startswith("기간: 매년 음력 7월 (시작·종료일 없음)")
    assert e1["미리보기 URL"] == f"{BASE}/events/"
    assert all(is_slug(r["미리보기 URL"].split("\n")[0].rstrip("/").rsplit("/", 1)[-1]) for r in rows if r["구분"] != "행사")
    assert snapshot(data) == before


def test_sheet_is_deterministic_and_base_is_configurable(tmp_path):
    data = dataset(tmp_path)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    make_review_sheet.main(["--data", str(data), "--out", str(a), "--base", "https://preview.example/"])
    make_review_sheet.main(["--data", str(data), "--out", str(b), "--base", "https://preview.example/"])
    assert a.read_bytes() == b.read_bytes()
    assert read_csv(a)[0]["미리보기 URL"] == "https://preview.example/places/ga-jangso/"


@pytest.mark.parametrize("base", ["ftp://x", "https://u:p@x", "https://x?q=1", "x"])
def test_sheet_rejects_bad_base(tmp_path, base):
    with pytest.raises(SystemExit) as exc:
        make_review_sheet.main(["--data", str(dataset(tmp_path)), "--out", str(tmp_path / "s.csv"), "--base", base])
    assert exc.value.code == 2


def test_sheet_needs_data_and_a_preview_address(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        make_review_sheet.main(["--out", str(tmp_path / "s.csv")])
    assert exc.value.code == 2 and "--data" in capsys.readouterr().err
    data = dataset(tmp_path)
    site_json(data, site_url="")                          # no site_url and no --base: nothing to link to
    with pytest.raises(SystemExit) as exc:
        make_review_sheet.main(["--data", str(data), "--out", str(tmp_path / "s.csv")])
    assert exc.value.code == 2 and "site_url" in capsys.readouterr().err
    assert not (tmp_path / "s.csv").exists()
    assert make_review_sheet.main(["--data", str(data), "--out", str(tmp_path / "s.csv"),
                                   "--base", "https://preview.example"]) == 0
    with pytest.raises(ValueError, match="site_url"):
        make_rows(data)


def test_sheet_slugs_follow_the_site_collision_policy_and_report_bad_stored_slugs(tmp_path, capsys):
    """A metropolitan config (slug_policy district): a same-name place in another 구·군 takes the 구·군 suffix, then a
    number; a malformed stored slug is reported and kept as it is (a published URL never changes)."""
    root = tmp_path / "data"
    site_json(root, ROOT / "tests" / "fixtures" / "metro" / "site.json")
    place = lambda pid, address, **extra: {"id": pid, "name": "[샘플] 같은 식당", "kind": "food", "tier": "full",
                                           "status": "draft", "facts": {"address": address}, **extra}
    write(root / "places.json", [place("m1", "대구광역시 북구 샘플로 3"), place("m2", "대구광역시 남구 샘플로 7"),
                                 place("m3", "대구광역시 남구 샘플로 9"),
                                 place("m4", "대구광역시 중구 샘플로 1", slug="Bad Slug")])
    out = tmp_path / "sheet.csv"
    assert make_review_sheet.main(["--data", str(root), "--out", str(out)]) == 0
    urls = {r["ID"]: r["미리보기 URL"] for r in read_csv(out)}
    assert urls["m1"] == f"{BASE}/places/gateun-sikdang/"
    assert urls["m2"] == f"{BASE}/places/gateun-sikdang-nam-gu/"
    assert urls["m3"] == f"{BASE}/places/gateun-sikdang-nam-gu-2/"
    assert urls["m4"] == f"{BASE}/places/Bad%20Slug/"
    assert "경고(slug):" in capsys.readouterr().err


def test_sheet_slugs_equal_the_build_slugs(tmp_path):
    """The sheet links to the pages the build makes: it assigns missing slugs with the build's own function
    (pipeline.build.assign_record_slugs), so every preview URL is the path of a page the build state names."""
    from pipeline import build as build_mod

    assert make_review_sheet.assign_record_slugs is build_mod.assign_record_slugs
    data = dataset(tmp_path)
    state = build_mod.State(data, "preview")
    built = {"장소": {x["id"]: x["slug"] for x in state.entities_all},
             "가이드": {x["id"]: x["slug"] for x in state.guides_all},
             "코스": {x["id"]: x["slug"] for x in state.courses_all}}
    assert all(is_slug(s) for kind in built.values() for s in kind.values())
    folder = {"장소": "places", "가이드": "guides", "코스": "courses"}
    rows = [r for r in make_rows(data) if r["구분"] in folder]
    assert rows
    for r in rows:
        url = r["미리보기 URL"].split("\n")[0]
        assert url == f"{BASE}/{folder[r['구분']]}/{built[r['구분']][r['ID']]}/", r


# --- apply_review --------------------------------------------------------------------------------

def marked_sheet(tmp_path: Path, data: Path, marks: dict, encoding: str = "utf-8-sig") -> Path:
    sheet = tmp_path / "sheet.csv"
    make_review_sheet.write_sheet(make_rows(data), sheet)
    rows = read_csv(sheet)
    for row in rows:
        verdict, memo = marks.get(row["ID"], ("", ""))
        row["판정"], row["메모"] = verdict, memo
    save_csv(sheet, rows, encoding)
    return sheet


MARKS = {"p1": (" ok ", ""), "p2": ("OK", ""), "g1": ("Ok", ""), "c1": ("수정", "경유지 순서 확인"), "e1": ("보류", "")}


def test_dry_run_writes_nothing_and_lists_todo(tmp_path, capsys):
    data = dataset(tmp_path)
    before = snapshot(data)
    sheet = marked_sheet(tmp_path, data, MARKS)
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", DATE]) == 0
    out = capsys.readouterr().out
    assert snapshot(data) == before
    assert "반영 예정(미리 보기) 2건" in out
    assert "장소 p1 같은 이름: draft → reviewed" in out
    assert "가이드 g1 비 오는 날: reviewed (reviewed_at 2026-10-02) → reviewed" in out
    assert "코스 c1 1코스 | 근대: 경유지 순서 확인" in out          # 수정 → to-do with memo
    assert "장소 p2 가 장소: status published" in out              # OK on published: untouched
    assert "'보류'" in out and "판정 없음 2건" in out and "--apply" in out


def test_apply_changes_only_status_and_reviewed_at(tmp_path, capsys):
    data = dataset(tmp_path)
    before = snapshot(data)
    sheet = marked_sheet(tmp_path, data, MARKS)
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", DATE, "--apply"]) == 0
    after = snapshot(data)
    changed = {}
    for name in before:
        diff = [line for line in difflib.unified_diff(before[name].splitlines(), after[name].splitlines(), lineterm="", n=0)
                if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        if diff:
            changed[name] = diff
    assert changed == {
        "places.json": ['-    "status": "draft",', '+    "status": "reviewed",', f'+    "reviewed_at": "{DATE}",'],
        "guides.json": ['-    "reviewed_at": "2026-10-02",', f'+    "reviewed_at": "{DATE}",'],
    }
    assert all(text.endswith("]\n") for name, text in after.items() if name != "site.json")
    places = json.loads(after["places.json"])
    assert [p["status"] for p in places] == ["draft", "reviewed", "published", "draft", "draft"]
    assert "".join(after.values()).count('"published"') == "".join(before.values()).count('"published"')
    assert [p.get("slug") for p in places] == [None, None, "ga-jangso", "dup", None]  # slugs never written back
    # applying the same sheet again changes nothing
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", DATE, "--apply"]) == 0
    assert snapshot(data) == after
    assert "이미 reviewed" in capsys.readouterr().out


def test_reads_sheet_saved_by_excel_as_cp949(tmp_path):
    data = dataset(tmp_path)
    sheet = marked_sheet(tmp_path, data, {"p1": ("OK", "")}, encoding="cp949")
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", DATE, "--apply"]) == 0
    assert json.loads((data / "places.json").read_text("utf-8"))[1]["status"] == "reviewed"


@pytest.mark.parametrize("edit, message", [
    (lambda rows: rows[1].update(ID="p-missing"), "없는 ID"),
    (lambda rows: rows.append(dict(rows[1])), "같은 ID가"),
    (lambda rows: rows[1].update(이름="다른 이름"), "이름이 데이터와 다릅니다"),
    (lambda rows: rows[1].update(구분="숙소"), "알 수 없는 구분"),
])
def test_refuses_mismatched_sheet_before_writing(tmp_path, capsys, edit, message):
    data = dataset(tmp_path)
    before = snapshot(data)
    sheet = marked_sheet(tmp_path, data, {"p1": ("OK", ""), "g1": ("OK", "")})
    rows = read_csv(sheet)
    edit(rows)
    save_csv(sheet, rows)
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", DATE, "--apply"]) == 1
    assert message in capsys.readouterr().err
    assert snapshot(data) == before


def test_refuses_duplicate_id_in_data_and_bad_date(tmp_path, capsys):
    data = dataset(tmp_path)
    sheet = marked_sheet(tmp_path, data, {"g1": ("OK", "")})
    guides = json.loads((data / "guides.json").read_text("utf-8"))
    write(data / "guides.json", guides + [dict(guides[0])])
    assert apply_review.main(["--sheet", str(sheet), "--data", str(data), "--apply"]) == 1
    assert "같은 ID가 2개" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        apply_review.main(["--sheet", str(sheet), "--data", str(data), "--date", "20261020"])
    assert exc.value.code == 2
