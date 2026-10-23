"""tools/kogl1_media.py and tools/image_sizes.py: derivatives only for published records (design Q14), the 15MB budget
for the whole set, and --data required by every TourAPI/photo tool (no default city). Photos and places are made up."""
import json
import shutil
from pathlib import Path

import pytest

from pipeline import media
from tools import image_sizes, kogl1_media, tourapi_bulk

ROOT = Path(__file__).resolve().parent.parent
METRO_DIR = ROOT / "tests" / "fixtures" / "metro"


def _city(tmp_path: Path) -> Path:
    """The metro fixture with lead photos: two published KOGL-1, one published KOGL-3, a draft and a reviewed KOGL-1."""
    data = tmp_path / "metro"
    shutil.copytree(METRO_DIR, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    img = lambda name, lic: {"url": f"https://img.test/{name}_image2_1.jpg", "alt": "사진", "credit": "한국관광공사",
                             "license": lic, "source": "TourAPI"}
    for p, (name, lic, status) in zip(places, [("pub", "KOGL-1", "published"), ("pubthree", "KOGL-3", "published"),
                                               ("draft", "KOGL-1", "draft"), ("rev", "KOGL-1", "reviewed"),
                                               ("big", "KOGL-1", "published")]):
        p["images"], p["status"] = [img(name, lic)], status
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    return data


def test_derivatives_only_for_published_kogl1_photos(tmp_path, capsys):
    rep = kogl1_media.run(_city(tmp_path), out=tmp_path / "media", dry_run=True)
    printed = capsys.readouterr().out
    assert rep["photos"] == 2 and "pub_image2_1" in printed and "big_image2_1" in printed
    assert "draft_" not in printed and "rev_" not in printed and "pubthree" not in printed


def test_the_whole_set_stays_within_the_budget(tmp_path, monkeypatch):
    out = tmp_path / "media"
    monkeypatch.setattr(kogl1_media, "fetch", lambda url, cache, budget: tmp_path / "raw.jpg")

    def encode(raw, url, slot, out_dir, force):  # 1,000 bytes of derivatives per photo
        entry = {"w": 940, "h": 627, "slot": slot, "avif": [], "webp": []}
        for fmt, size in (("avif", 600), ("webp", 400)):
            path = out_dir / f"{kogl1_media.stem_of(url)}-940.{fmt}"
            path.write_bytes(b"x" * size)
            entry[fmt].append([media.URL_PREFIX + path.name, 940, size])
        return entry

    monkeypatch.setattr(kogl1_media, "encode", encode)
    rep = kogl1_media.run(_city(tmp_path), out=out, cache=tmp_path / "cache", budget_bytes=1500)
    man = json.loads((out / "manifest.json").read_text("utf-8"))
    assert list(man) == ["https://img.test/big_image2_1.jpg"] and rep["photos"] == 1
    assert len(rep["skipped"]) == 1 and "pub_image2_1" in rep["skipped"][0] and "예산" in rep["skipped"][0]
    on_disk = {f.name for f in out.iterdir() if f.suffix in (".avif", ".webp")}
    assert on_disk == {Path(p).name for e in man.values() for fmt in ("avif", "webp") for p, *_ in e[fmt]}
    assert sum(b for e in man.values() for fmt in ("avif", "webp") for *_, b in e[fmt]) <= 1500
    assert kogl1_media.BUDGET_BYTES == 15 * 1024 * 1024


def test_image_sizes_without_places_records_nothing(tmp_path):
    rep = image_sizes.run(tmp_path, prober=lambda url: pytest.fail("no request"))
    assert rep["photos"] == 0 and json.loads((tmp_path / "image_sizes.json").read_text("utf-8")) == {}


@pytest.mark.parametrize("tool", [image_sizes, kogl1_media, tourapi_bulk])
def test_data_folder_is_required(tool, capsys):
    with pytest.raises(SystemExit) as exit_:
        tool.main([])
    assert exit_.value.code == 2 and "--data" in capsys.readouterr().err
