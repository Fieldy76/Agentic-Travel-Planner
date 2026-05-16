from freezegun import freeze_time

from travel_agent.tools.datetime_tool import get_current_datetime


@freeze_time("2026-05-16 12:34:56")
def test_get_current_datetime_returns_expected_shape():
    r = get_current_datetime()
    assert r["date"] == "2026-05-16"
    assert r["year"] == 2026
    assert r["month"] == 5
    assert r["day"] == 16
