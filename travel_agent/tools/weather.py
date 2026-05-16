import logging
from datetime import date as _date, datetime, timedelta
from typing import Any, Dict

import httpx

from ..agent.cache import global_tool_cache

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

FORECAST_HORIZON_DAYS = 14

WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Heavy rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


@global_tool_cache.cached
def _geocode(location: str) -> tuple[float, float, str] | None:
    """Resolve a free-form city name to (lat, lon, resolved_name) via Open-Meteo."""
    try:
        response = httpx.get(
            OPEN_METEO_GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        logger.warning("Geocoding failed for %r: %s", location, e)
        return None

    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    return float(top["latitude"]), float(top["longitude"]), top.get("name", location)


def _query_open_meteo(url: str, lat: float, lon: float, start: str, end: str) -> Dict[str, Any] | None:
    """Single Open-Meteo query, returns parsed JSON or None on failure."""
    try:
        response = httpx.get(
            url,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                "start_date": start,
                "end_date": end,
                "timezone": "auto",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning("Open-Meteo %s failed (%s..%s): %s", url, start, end, e)
        return None


def _format(resolved_name: str, date_str: str, data: Dict[str, Any], source: str) -> Dict[str, Any]:
    daily = data.get("daily") or {}
    temp_max_list = daily.get("temperature_2m_max") or []
    temp_min_list = daily.get("temperature_2m_min") or []
    weather_code_list = daily.get("weathercode") or []
    if not temp_max_list or not temp_min_list or not weather_code_list:
        return {"location": resolved_name, "date": date_str, "error": "No weather data returned."}

    temp_max = temp_max_list[0]
    temp_min = temp_min_list[0]
    weather_code = weather_code_list[0]
    condition = WEATHER_CODE_MAP.get(weather_code, "Unknown")
    avg_temp = None if (temp_max is None or temp_min is None) else (temp_max + temp_min) / 2

    return {
        "location": resolved_name,
        "date": date_str,
        "condition": condition,
        "temperature_celsius": round(avg_temp, 1) if avg_temp is not None else None,
        "temperature_fahrenheit": round(avg_temp * 9 / 5 + 32, 1) if avg_temp is not None else None,
        "temp_max_c": temp_max,
        "temp_min_c": temp_min,
        "source": source,
    }


@global_tool_cache.cached
def get_forecast(location: str, date: str) -> Dict[str, Any]:
    """Get weather for a location on a specific date (YYYY-MM-DD).

    Strategy:
      - Within ~14 days: live forecast (Open-Meteo forecast API).
      - Further out: same date last year from the historical archive, returned
        as a climatological estimate (source="historical_proxy").
      - Past dates: historical archive directly.

    No API key required.
    """
    geocoded = _geocode(location)
    if geocoded is None:
        return {
            "location": location,
            "date": date,
            "error": f"Could not resolve location {location!r}. Try a more specific city name.",
        }
    lat, lon, resolved_name = geocoded

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as e:
        return {"location": resolved_name, "date": date, "error": f"Invalid date {date!r}: {e}"}

    today = _date.today()
    delta = (target_date - today).days

    if -1 <= delta <= FORECAST_HORIZON_DAYS:
        data = _query_open_meteo(OPEN_METEO_FORECAST_URL, lat, lon, date, date)
        if data:
            return _format(resolved_name, date, data, source="forecast")

    proxy_date = target_date if target_date < today else target_date.replace(year=today.year - 1)
    proxy_str = proxy_date.isoformat()
    data = _query_open_meteo(OPEN_METEO_ARCHIVE_URL, lat, lon, proxy_str, proxy_str)
    if not data:
        return {"location": resolved_name, "date": date, "error": "Weather service unavailable."}

    formatted = _format(resolved_name, date, data, source="historical_proxy")
    if "error" not in formatted and proxy_date != target_date:
        formatted["note"] = (
            f"Forecast horizon is ~{FORECAST_HORIZON_DAYS} days. Showing {proxy_str} "
            f"(same date one year ago) as a climatological estimate."
        )
    return formatted
