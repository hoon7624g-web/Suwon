"""tools/tourapi_doctor.py — key normalisation, redaction, response classification, --data and --check-region
(network mocked; region codes are synthetic)."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("tourapi_doctor", ROOT / "tools" / "tourapi_doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

DECODED = "AbC+dEf/GhI=jKl123456789=="
ENCODED = "AbC%2BdEf%2FGhI%3DjKl123456789%3D%3D"


def test_key_forms_normalise_both_inputs():
    a, b = doctor.key_forms(DECODED), doctor.key_forms(ENCODED)
    assert a["decoded"] == b["decoded"] == DECODED
    assert a["encoded_once"] == b["encoded_once"] == ENCODED
    assert b["given_form"].startswith("Encoding") and a["given_form"].startswith("Decoding")


def test_redact_hides_every_form():
    text = f"url?serviceKey={ENCODED}&x=1 raw={DECODED}"
    out = doctor.redact(text, ENCODED, DECODED)
    assert ENCODED not in out and DECODED not in out and out.count("«KEY»") == 2


def test_classify_json_success_and_gateway_error():
    ok = json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                  "body": {"items": {"item": [{"title": "경암동 철길마을", "addr1": "샘플시", "contentid": "1"}]}}}})
    info = doctor.classify(ok)
    assert info["format"] == "json" and info["items"] == 1 and "경암동" in info["first"]
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
           "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode>"
           "</cmmMsgHeader></OpenAPI_ServiceResponse>")
    info = doctor.classify(xml)
    assert info["format"] == "xml" and info["code"] == "30"
    assert "등록되지 않은 키" in doctor.advice(info["message"])


class FakeResp(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_run_reports_success_without_leaking_key(monkeypatch):
    seen = []
    body = json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": {"title": "경암동 철길마을", "contentid": "9"}}}}}).encode()

    def fake_urlopen(req, timeout=15):
        seen.append(req.full_url)
        return FakeResp(body)

    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(doctor.urllib.request, "urlopen", fake_urlopen)
    rep = doctor.run("경암동 철길마을", ENCODED)
    assert rep["verdict"].startswith("정상")
    assert f"serviceKey={ENCODED}&" in seen[0]          # decoded key encoded exactly once
    dumped = json.dumps(rep, ensure_ascii=False)
    assert ENCODED not in dumped and DECODED not in dumped


def test_run_explains_unregistered_key(monkeypatch):
    xml = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
           b"</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda req, timeout=15: FakeResp(xml))
    rep = doctor.run("x", DECODED)
    assert rep["verdict"].startswith("실패") and "등록되지 않은 키" in rep["verdict"]


def test_missing_key_and_blocked_network(monkeypatch):
    assert "TOURAPI_KEY가 없습니다" in doctor.run("x", "")["verdict"]
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (False, "blocked"))
    assert "접속할 수 없습니다" in doctor.run("x", DECODED)["verdict"]


# ------------------------------------------------------------------ --data and --check-region (synthetic codes)
METRO = ROOT / "tests" / "fixtures" / "metro"
REGIONS = [{"code": "980", "name": "다른광역시"}, {"code": "990", "name": "대구광역시"}]
DISTRICTS = json.loads((METRO / "site.json").read_text("utf-8"))["districts"]


def _ok(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items}}}}).encode()


def _server(seen, under):
    def urlopen(req, timeout=15):
        url = doctor.urllib.parse.urlsplit(req.full_url)
        q = {k: v[0] for k, v in doctor.urllib.parse.parse_qs(url.query).items()}
        seen.append((url.path.rsplit("/", 1)[1], q, req.get_header("User-agent")))
        if url.path.endswith("/ldongCode2"):
            return FakeResp(_ok(REGIONS if "lDongRegnCd" not in q else under if q["lDongRegnCd"] == "990" else []))
        return FakeResp(_ok([{"title": "샘플", "contentid": "1"}]))
    return urlopen


def _main(monkeypatch, capsys, argv, under):
    seen = []
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(doctor, "load_key", lambda *a, **k: DECODED)
    monkeypatch.setattr(doctor.urllib.request, "urlopen", _server(seen, under))
    code = doctor.main(argv)
    return code, capsys.readouterr().out, seen


def test_data_sets_the_default_keyword_and_requests_name_no_city(monkeypatch, capsys):
    code, out, seen = _main(monkeypatch, capsys, ["--data", str(METRO)], [])
    assert code == 0 and seen[0][0] == "searchKeyword2" and seen[0][1]["keyword"] == "대구"   # site.json region
    assert seen[0][1]["MobileApp"] == doctor.DEFAULT_MOBILE_APP and seen[0][2] == doctor.USER_AGENT
    code, out, seen = _main(monkeypatch, capsys, [], [])
    assert code == 0 and seen[0][1]["keyword"] == doctor.DEFAULT_KEYWORD
    assert not any(op == "ldongCode2" for op, *_ in seen)          # no region check unless asked


def test_check_region_lists_the_districts_and_names_a_missing_one(monkeypatch, capsys):
    under = [{"code": str(99101 + i), "name": d} for i, d in enumerate(DISTRICTS)]
    code, out, seen = _main(monkeypatch, capsys, ["--data", str(METRO), "--check-region"], under)
    assert code == 0 and "대구광역시(990)" in out and "군위군(99109)" in out and "모두" in out
    assert [q.get("lDongRegnCd") for op, q, _ in seen if op == "ldongCode2"] == [None, "990"]   # codes from the answer
    code, out, _ = _main(monkeypatch, capsys, ["--data", str(METRO), "--check-region", "--json"],
                         [x for x in under if x["name"] != "군위군"])
    rep = json.loads(out)
    assert code == 1 and rep["region"]["missing"] == ["군위군"] and not rep["region"]["ok"]
    assert "군위군" in rep["region"]["message"] and "docs/rights.md 4절" in rep["region"]["message"]
    assert len(rep["region"]["signgu"]) == 8 and rep["verdict"].startswith("정상")


def test_check_region_needs_data_and_an_exact_region_name(monkeypatch, capsys, tmp_path):
    with pytest.raises(SystemExit):
        doctor.main(["--check-region"])
    site = json.loads((METRO / "site.json").read_text("utf-8"))
    site["tourapi"]["ldong_regn_name"] = "대구"          # not the provider's exact name
    (tmp_path / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    code, out, _ = _main(monkeypatch, capsys, ["--data", str(tmp_path), "--check-region", "--json"], [])
    rep = json.loads(out)
    assert code == 1 and rep["region"]["regn"] is None and "0개" in rep["region"]["message"]
