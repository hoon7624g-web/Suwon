"""tools/approve_publication.py: 운영자 공개 승인 반영. --data가 필수이고, 없는 데이터 파일은 빈 목록으로 본다."""
import json
from pathlib import Path

import pytest

from tools import approve_publication


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def dataset(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    write(data / "places.json", [
        {"id": "p1", "name": "선택된 장소", "status": "draft"},
        {"id": "p2", "name": "선택 안 된 장소", "status": "draft"},
        {"id": "p3", "name": "중복", "status": "draft", "duplicate_of": "p1"},
    ])
    write(data / "guides.json", [{"id": "g1", "title": "가이드", "status": "reviewed", "reviewed_at": "2026-10-19"}])
    selection = tmp_path / "reports" / "review_build_selection.json"
    write(selection, {"selected": [{"id": "p1"}, {"id": "p3"}]})
    return data, selection


def run(data: Path, selection: Path, *extra: str) -> int:
    return approve_publication.main(["--data", str(data), "--selection", str(selection), "--date", "2026-10-20", *extra])


def test_preview_writes_nothing_and_missing_files_count_as_empty(tmp_path, capsys):
    data, selection = dataset(tmp_path)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    assert run(data, selection) == 0
    counts = json.loads(capsys.readouterr().out)
    assert counts["apply"] is False
    # p1 only (p3 is a duplicate); the total is what the data would hold after --apply
    assert counts["places"] == {"published_now": 1, "held": 0, "published_total": 1}
    assert counts["guides"]["published_now"] == 1
    assert counts["courses"] == counts["events"] == {"published_now": 0, "held": 0, "published_total": 0}
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before


def test_apply_publishes_selected_records_keeps_review_dates_and_creates_no_files(tmp_path, capsys):
    data, selection = dataset(tmp_path)
    assert run(data, selection, "--hold", "g1", "--apply") == 0
    places = json.loads((data / "places.json").read_text("utf-8"))
    assert [(p["id"], p["status"], p.get("approved_at")) for p in places] == [
        ("p1", "published", "2026-10-20"), ("p2", "draft", None), ("p3", "draft", None)]
    guide = json.loads((data / "guides.json").read_text("utf-8"))[0]
    assert guide["status"] == "reviewed" and guide["reviewed_at"] == "2026-10-19" and "approved_at" not in guide
    assert sorted(p.name for p in data.iterdir()) == ["guides.json", "places.json"]     # no courses/events files made
    assert json.loads(capsys.readouterr().out)["guides"]["held"] == 1


def test_data_folder_is_required(tmp_path, capsys):
    _, selection = dataset(tmp_path)
    with pytest.raises(SystemExit) as exc:
        approve_publication.main(["--selection", str(selection), "--date", "2026-10-20"])
    assert exc.value.code == 2 and "--data" in capsys.readouterr().err
