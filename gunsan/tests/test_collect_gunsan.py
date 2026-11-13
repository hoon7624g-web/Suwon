"""Collector safety and preservation checks; HTTP and time are fully simulated."""
import csv
import hashlib
import io
from urllib.error import HTTPError, URLError

import pytest

from tools import collect_gunsan as collector


ROBOTS = b"User-agent: *\nAllow: /tour\n"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ScriptedOpener:
    def __init__(self, clock, events):
        self.clock = clock
        self.events = list(events)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, dict(request.header_items()), self.clock(), timeout))
        assert self.events, "Unexpected network request (all HTTP is mocked)"
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return Response(event)


def http_error(status, *, location=None):
    headers = {} if location is None else {"Location": location}
    return HTTPError(collector.ORIGIN + "/tour", status, "mock HTTP error", headers, None)


def make_fetcher(tmp_path, events, **kwargs):
    clock = FakeClock()
    opener = ScriptedOpener(clock, events)
    fetcher = collector.Fetcher(tmp_path / "raw", opener=opener, clock=clock, sleep=clock.sleep, **kwargs)
    return fetcher, opener, clock


def manifest_rows(fetcher):
    with fetcher.manifest.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_fixed_agent_and_spacing_apply_to_robots_and_redirect_hops(tmp_path):
    fetcher, opener, clock = make_fetcher(tmp_path, [
        ROBOTS, http_error(302, location="/tour/m2080"), b"detail body", b"second body",
    ])
    fetcher.load_robots()
    fetcher.get(collector.ORIGIN + "/tour")
    fetcher.get(collector.ORIGIN + "/tour/m2079")
    assert [call[2] for call in opener.calls] == [0, 1.5, 3.0, 4.5]
    assert clock.sleeps == [1.5, 1.5, 1.5]
    assert all(dict((k.lower(), v) for k, v in call[1].items())["user-agent"] ==
               "WebforAI-collector/0.1 (research; o2o.kr)" for call in opener.calls)
    assert all(call[3] == 20 for call in opener.calls)
    assert fetcher.requests == 4


@pytest.mark.parametrize("interval,limit", [(1.49, 1000), (1.5, 0), (1.5, 1001)])
def test_rate_and_budget_cannot_be_weakened(tmp_path, interval, limit):
    with pytest.raises(ValueError):
        collector.Fetcher(tmp_path, interval=interval, limit=limit)


def test_robots_crawl_delay_increases_spacing(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [b"User-agent: *\nCrawl-delay: 4\nAllow: /\n", b"body"])
    fetcher.load_robots()
    fetcher.get(collector.ORIGIN + "/tour")
    assert fetcher.interval == 4
    assert [call[2] for call in opener.calls] == [0, 4]


def test_without_robots_no_tourism_request_occurs(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [])
    with pytest.raises(collector.CollectionError, match="robots"):
        fetcher.get(collector.ORIGIN + "/tour")
    assert opener.calls == []


@pytest.mark.parametrize("body", [b"", b"<html>error page</html>", b"# User-agent: *\n", b"User-agent:\nAllow: /\n"])
def test_malformed_robots_fails_closed(tmp_path, body):
    fetcher, opener, _ = make_fetcher(tmp_path, [body])
    with pytest.raises(collector.CollectionError):
        fetcher.load_robots()
    with pytest.raises(collector.CollectionError):
        fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 1


@pytest.mark.parametrize("error", [http_error(404), URLError("mock unavailable")])
def test_robots_failure_stops_fetcher(tmp_path, error):
    fetcher, opener, _ = make_fetcher(tmp_path, [error])
    with pytest.raises(collector.CollectionError):
        fetcher.load_robots()
    assert fetcher.stopped
    with pytest.raises(collector.CollectionError):
        fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 1


def test_disallow_is_checked_for_each_requested_path(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [b"User-agent: *\nDisallow: /tour/m2080\n", b"menu"])
    fetcher.load_robots()
    with pytest.raises(collector.CollectionError, match="disallows"):
        fetcher.get(collector.ORIGIN + "/tour/m2080")
    assert len(opener.calls) == 1
    fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 2


def test_off_origin_redirect_is_rejected_before_request(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, http_error(302, location="https://example.org/tour")])
    fetcher.load_robots()
    with pytest.raises(collector.CollectionError, match="origin"):
        fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 2
    assert all(call[0].startswith(collector.ORIGIN + "/") for call in opener.calls)


def test_redirect_target_disallowed_by_robots_is_not_fetched(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [
        b"User-agent: *\nDisallow: /tour/m2080\n", http_error(302, location="/tour/m2080"),
    ])
    fetcher.load_robots()
    with pytest.raises(collector.CollectionError, match="disallowed"):
        fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 2


@pytest.mark.parametrize("url", ["http://www.gunsan.go.kr/tour", "https://gunsan.go.kr/tour",
                                      "https://www.gunsan.go.kr:443/tour", "https://www.gunsan.go.kr/main"])
def test_direct_url_cannot_escape_inspected_origin_and_scope(tmp_path, url):
    fetcher, opener, _ = make_fetcher(tmp_path, [])
    with pytest.raises(collector.CollectionError):
        fetcher.get(url)
    assert opener.calls == []


@pytest.mark.parametrize("status", [403, 429])
def test_access_denial_and_rate_limit_stop_immediately(tmp_path, status):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, http_error(status)])
    fetcher.load_robots()
    with pytest.raises(collector.CollectionError, match=str(status)):
        fetcher.get(collector.ORIGIN + "/tour")
    assert fetcher.stopped
    with pytest.raises(collector.CollectionError, match="stopped"):
        fetcher.get(collector.ORIGIN + "/tour/m2080")
    assert len(opener.calls) == 2
    assert manifest_rows(fetcher)[-1]["http_status"] == str(status)


@pytest.mark.parametrize("error_factory", [lambda: http_error(500), lambda: URLError("mock unavailable")])
def test_five_consecutive_failures_stop_further_requests(tmp_path, error_factory):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS] + [error_factory() for _ in range(5)])
    fetcher.load_robots()
    for index in range(5):
        with pytest.raises(collector.CollectionError):
            fetcher.get(collector.ORIGIN + "/tour")
        assert fetcher.stopped is (index == 4)
    with pytest.raises(collector.CollectionError, match="stopped"):
        fetcher.get(collector.ORIGIN + "/tour")
    assert len(opener.calls) == 6
    assert fetcher.errors == 5


def test_success_resets_consecutive_error_count(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS] + [http_error(500) for _ in range(4)] + [b"recovered", http_error(500)])
    fetcher.load_robots()
    for _ in range(4):
        with pytest.raises(collector.CollectionError):
            fetcher.get(collector.ORIGIN + "/tour")
    fetcher.get(collector.ORIGIN + "/tour")
    assert fetcher.errors == 0
    with pytest.raises(collector.CollectionError):
        fetcher.get(collector.ORIGIN + "/tour/m2080")
    assert fetcher.errors == 1
    assert not fetcher.stopped
    assert len(opener.calls) == 7


def test_request_cap_includes_robots_and_redirects(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, http_error(302, location="/tour/m2080")], limit=2)
    fetcher.load_robots()
    with pytest.raises(collector.CollectionError, match="budget"):
        fetcher.get(collector.ORIGIN + "/tour")
    assert fetcher.stopped
    assert fetcher.requests == 2
    assert len(opener.calls) == 2


def test_original_bytes_manifest_hash_and_repeated_url_cache(tmp_path):
    body = "<p>첫 줄\r\n둘째 줄  </p>".encode("utf-8")
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, body])
    fetcher.load_robots()
    url = collector.ORIGIN + "/tour/m2080/view/1"
    first = fetcher.get(url)
    assert fetcher.get(url + "#fragment") == first
    assert len(opener.calls) == 2
    assert (fetcher.root / first[1]).read_bytes() == body
    rows = manifest_rows(fetcher)
    assert len(rows) == 2
    assert rows[-1]["url"] == url
    assert rows[-1]["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert rows[-1]["http_status"] == "200"
    assert rows[-1]["collected_at"]
    assert rows[-1]["raw_path"] == first[1]


def test_new_run_appends_manifest_and_preserves_previous_raw_bytes(tmp_path):
    url = collector.ORIGIN + "/tour/m2080/view/1"
    first, _, _ = make_fetcher(tmp_path, [ROBOTS, b"original source"])
    first.load_robots()
    _, old_path = first.get(url)
    old_manifest = first.manifest.read_bytes()
    second, _, _ = make_fetcher(tmp_path, [ROBOTS, b"updated source"])
    second.load_robots()
    _, new_path = second.get(url)
    assert second.manifest.read_bytes().startswith(old_manifest)
    assert (second.root / old_path).read_bytes() == b"original source"
    assert (second.root / new_path).read_bytes() == b"updated source"
    assert old_path != new_path
    assert len(manifest_rows(second)) == 4


def test_request_budget_is_preserved_across_cli_stages(tmp_path):
    first, _, _ = make_fetcher(tmp_path, [ROBOTS, b"first stage"], limit=2)
    first.load_robots()
    first.get(collector.ORIGIN + "/tour")
    second, opener, _ = make_fetcher(tmp_path, [], limit=2)
    assert second.initial_requests == 2
    assert second.requests == 2
    with pytest.raises(collector.CollectionError, match="budget"):
        second.load_robots()
    assert opener.calls == []


def test_raw_collision_fails_without_overwriting_existing_file(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, b"response source"])
    fetcher.load_robots()
    url = collector.ORIGIN + "/tour/m2080/view/1"
    filename = hashlib.sha256(url.encode()).hexdigest()[:20] + "-" + hashlib.sha256(b"response source").hexdigest()[:12] + ".html"
    target = fetcher.html / filename
    target.write_bytes(b"preexisting local source")
    with pytest.raises(collector.CollectionError, match="collision"):
        fetcher.get(url)
    assert target.read_bytes() == b"preexisting local source"
    assert len(manifest_rows(fetcher)) == 1
    assert len(opener.calls) == 2


def test_failed_three_sample_gate_makes_no_collection_requests_or_outputs(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [])
    with pytest.raises(collector.CollectionError, match="gate"):
        collector.collect(fetcher, {"place_candidates": [{"url": collector.ORIGIN + "/tour/m2080/view/1"}],
                                    "sources": []}, {"passed": False})
    assert opener.calls == []
    assert not (fetcher.root.parent / "gunsan_places.csv").exists()
    assert not (fetcher.root.parent / "gunsan_courses.json").exists()


@pytest.mark.parametrize("samples", [[], [{"checks": {"body": True}}] * 2,
                                    [{"checks": {"body": True}}] * 4,
                                    [{"checks": {"body": True}}] * 2 + [{"checks": {"body": False}}],
                                    [{"checks": {}}] * 3])
def test_passed_flag_cannot_override_actual_three_sample_gate(tmp_path, samples):
    fetcher, opener, _ = make_fetcher(tmp_path, [])
    with pytest.raises(collector.CollectionError, match="gate"):
        collector.collect(fetcher, {"place_candidates": [], "sources": []}, {"passed": True, "samples": samples})
    assert opener.calls == []


def test_full_collection_preserves_text_and_deduplicates_source_identity(tmp_path, monkeypatch):
    original = "첫째 줄\n둘째 줄  "
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, b"detail"])
    fetcher.load_robots()
    url = collector.ORIGIN + "/tour/m2080/view/1"
    item = {"source_id": "1", "name": "장소 이름", "url": url, "category": "역사"}
    alias = dict(item, url=collector.ORIGIN + "/tour/m2339/view/1")
    monkeypatch.setattr(collector, "parse_detail", lambda raw, url: {
        "checks": {"body": True, "identity": True}, "name": "장소 이름",
        "original_text": original, "original_license": "NONE", "license_evidence": "표기 없음",
        "images": [{"url": collector.ORIGIN + "/images/photo.jpg", "license": "UNKNOWN"}],
        "structure": {"body": "inspected selector"},
    })
    gate = {"passed": True, "samples": [{"checks": {"body": True}}] * 3}
    summary = collector.collect(fetcher, {"place_candidates": [item, alias], "sources": []}, gate)
    assert summary["places"] == 1
    assert summary["complete"]
    assert len(opener.calls) == 2  # Image URL is recorded without an image download.
    with (fetcher.root.parent / "gunsan_places.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["original_text"] == original
    assert rows[0]["original_license"] == "NONE"
    assert rows[0]["image_license"] == "UNKNOWN"
    assert rows[0]["status"] == "draft"
    assert rows[0]["tier"] == "basic"


def test_samples_require_inventory_observed_urls_and_three_checks(tmp_path, monkeypatch):
    fetcher, opener, _ = make_fetcher(tmp_path, [ROBOTS, b"one", b"two", b"three"])
    fetcher.load_robots()
    monkeypatch.setattr(collector, "parse_detail", lambda raw, url: {"checks": {"body": True, "license": url != collector.SAMPLE_URLS[1]},
                                                                 "original_text": raw})
    catalog = {"sources": [{"items": [{"url": url} for url in collector.SAMPLE_URLS]}]}
    gate = collector.samples(fetcher, catalog)
    assert len(gate["samples"]) == 3
    assert not gate["passed"]
    assert len(opener.calls) == 4
    assert (fetcher.root / "sample_review.json").exists()


def test_sample_url_not_observed_in_inventory_is_not_fetched(tmp_path):
    fetcher, opener, _ = make_fetcher(tmp_path, [])
    with pytest.raises(collector.CollectionError, match="inventory"):
        collector.samples(fetcher, {"sources": []})
    assert opener.calls == []


def test_default_cli_stage_is_inventory_only(tmp_path, monkeypatch, capsys):
    calls = []

    class FakeFetcher:
        def __init__(self, root, **kwargs):
            self.root = root
            self.requests = 0
            calls.append(("init", root, kwargs))

        def load_robots(self):
            calls.append(("robots",))

    def fake_inventory(fetcher):
        calls.append(("inventory",))
        return {"sources": [], "place_candidates": [], "course_candidates": [], "guide_candidates": []}

    def forbidden(*args, **kwargs):
        pytest.fail("Default CLI must not fetch details or perform full collection")

    monkeypatch.setattr(collector, "Fetcher", FakeFetcher)
    monkeypatch.setattr(collector, "inventory", fake_inventory)
    monkeypatch.setattr(collector, "samples", forbidden)
    monkeypatch.setattr(collector, "collect", forbidden)
    assert collector.main(["--raw", str(tmp_path / "raw")]) == 0
    assert [call[0] for call in calls] == ["init", "robots", "inventory"]
    assert '"place_candidates": 0' in capsys.readouterr().out
