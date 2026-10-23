"""tools/tourapi_harvest.py — its requests land on the cache files the merging tools read (no quota spent twice), and a
pack restores the same files with their fetch dates."""
import json
import os
import tarfile

from pipeline.tourapi import TourAPI
from tools import tourapi_harvest as H


class Recorder(H.Harvest):
    """Records each (service, op, params) instead of calling; answers like an empty page."""

    def __init__(self, site, cache):
        super().__init__(site, "k", cache, max_calls=5, workers=2)
        self.seen = []

    def call(self, svc, op, **params):
        self.seen.append((svc, op, params))
        return []


def test_detail_requests_share_the_bulk_tools_cache_keys(tmp_path):
    h = Recorder({"tourapi": {}}, tmp_path)
    H.details(h, "kor", [("123", "12")])
    h.pool.shutdown()
    api = TourAPI("k", cache_dir=tmp_path)
    asked = []
    api.call = lambda op, **params: asked.append((op, params)) or []
    api.detail_common("123"), api.detail_intro("123", "12"), api.detail_info("123", "12"), api.detail_image("123")
    path = TourAPI("k", cache_dir=tmp_path)._cache_path
    assert {path(op, p) for _, op, p in h.seen} == {path(op, p) for op, p in asked}


def test_pack_and_unpack_keep_files_and_dates(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    cache = root / "data" / "cache" / "tourapi"
    (cache / "engservice2").mkdir(parents=True)
    a = cache / "detailCommon-aaaa.json"
    b = cache / "engservice2" / "areaBasedList-bbbb.json"
    for f in (a, b):
        f.write_text(json.dumps({"response": {}}), "utf-8")
        os.utime(f, (1760000000, 1760000000))
    data = root / "data" / "metro"
    data.mkdir(parents=True)
    monkeypatch.setattr(H, "ROOT", root)
    m = H.pack(data, cache)
    assert set(m["archives"]) == {"korservice2.tar.gz", "engservice2.tar.gz"}
    with tarfile.open(root / "data" / "raw" / "metro" / "tourapi" / "engservice2.tar.gz") as tar:
        assert tar.getnames() == ["engservice2/areaBasedList-bbbb.json"]
    fresh = tmp_path / "fresh"
    assert H.unpack(data, fresh) == 2
    assert (fresh / "engservice2" / "areaBasedList-bbbb.json").stat().st_mtime == 1760000000
    assert H.unpack(data, fresh) == 0  # files already there are kept
