import pytest

from travel_agent.tools.cars import rent_car


def test_rent_car_computes_days():
    r = rent_car("LHR", "2026-06-01", "2026-06-05", "sedan")
    assert r["days"] == 4
    assert r["estimated_total_price"] == 60 * 4
    assert r["car_type"] == "sedan"
    assert "rentalcars.com" in r["booking_url"] or "tp.media" in r["booking_url"]


def test_rent_car_unknown_type_default_price():
    r = rent_car("JFK", "2026-06-01", "2026-06-02", "alien")
    assert r["estimated_total_price"] == 50  # default


def test_rent_car_rejects_invalid_dates():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        rent_car("JFK", "not-a-date", "2026-06-02")


def test_rent_car_rejects_reverse_dates():
    with pytest.raises(ValueError, match="after"):
        rent_car("JFK", "2026-06-05", "2026-06-01")


def test_rent_car_high_entropy_reference():
    refs = {rent_car("JFK", "2026-06-01", "2026-06-02")["search_reference"] for _ in range(20)}
    assert len(refs) == 20
