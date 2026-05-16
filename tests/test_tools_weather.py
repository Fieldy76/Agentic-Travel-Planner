import httpx
import respx

from travel_agent.agent.cache import global_tool_cache
from travel_agent.tools.weather import get_forecast


def setup_function():
    # Ensure tests don't reuse cached results from each other.
    global_tool_cache.invalidate()


@respx.mock
def test_forecast_within_horizon_uses_live_api():
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json={
            "results": [{"latitude": 48.85, "longitude": 2.35, "name": "Paris"}]
        })
    )
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(200, json={
            "daily": {"temperature_2m_max": [22], "temperature_2m_min": [12], "weathercode": [1]}
        })
    )
    from datetime import date, timedelta
    near = (date.today() + timedelta(days=3)).isoformat()
    r = get_forecast("Paris", near)
    assert r["source"] == "forecast"
    assert r["condition"] == "Mainly clear"
    assert r["temperature_celsius"] == 17.0


@respx.mock
def test_forecast_beyond_horizon_uses_archive():
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json={
            "results": [{"latitude": 41.9, "longitude": 12.49, "name": "Rome"}]
        })
    )
    respx.get("https://archive-api.open-meteo.com/v1/archive").mock(
        return_value=httpx.Response(200, json={
            "daily": {"temperature_2m_max": [30], "temperature_2m_min": [20], "weathercode": [0]}
        })
    )
    from datetime import date, timedelta
    far = (date.today() + timedelta(days=100)).isoformat()
    r = get_forecast("Rome", far)
    assert r["source"] == "historical_proxy"
    assert r["condition"] == "Clear sky"
    assert "Forecast horizon" in r["note"]


@respx.mock
def test_geocoding_failure_returns_error():
    respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    r = get_forecast("Atlantis", "2030-01-01")
    assert "error" in r and "Could not resolve" in r["error"]


def test_invalid_date_returns_error():
    r = get_forecast("Paris", "not-a-date")
    assert "Invalid date" in r["error"]
