"""tools/place_text.py — the fee reader the summaries depend on (2026-10-27)."""
from tools.place_text import fee_text


def test_a_price_range_row_keeps_its_first_amount_whole():
    raw = "- 숲속의 집 60,000원~100,000원\n- 세미나실 50,000원~80,000원\n※ 자세한 사항은 홈페이지 참조"
    assert fee_text(raw)["text"] == "숲속의 집 60,000원~100,000원, 세미나실 50,000원~80,000원"
