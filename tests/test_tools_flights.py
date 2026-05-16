import pytest

from travel_agent.tools.flights import (
    AIRLINE_MAP,
    AmadeusTokenCache,
    _aviasales_deeplink,
    book_flight,
    search_flights,
)


async def test_search_flights_falls_back_to_mock_without_keys():
    # conftest.py removes FLIGHT_API_KEY/SECRET — search hits mock path.
    results = await search_flights("JFK", "LHR", "2026-06-15")
    assert len(results) == 3
    for r in results:
        assert r["origin"] == "JFK"
        assert r["destination"] == "LHR"
        assert r["airline_code"] in AIRLINE_MAP


async def test_search_flights_localized_currency():
    results = await search_flights("LHR", "JFK", "2026-06-15")
    assert results[0]["currency"] == "GBP"


async def test_book_flight_returns_real_deeplink_and_intent_ref():
    r = await book_flight("JFK", "LHR", "2026-10-20", "Alice", passengers=2)
    assert r["status"] == "pending_user_action"
    assert r["intent_reference"].startswith("BK")
    assert "JFK2010LHR2" in r["booking_url"]


async def test_book_flight_rejects_invalid_date():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await book_flight("JFK", "LHR", "tomorrow", "Alice")


async def test_book_flight_rejects_past_date():
    with pytest.raises(ValueError, match="past"):
        await book_flight("JFK", "LHR", "2000-01-01", "Alice")


async def test_book_flight_rejects_zero_passengers():
    with pytest.raises(ValueError, match="passengers"):
        await book_flight("JFK", "LHR", "2030-01-01", "Alice", passengers=0)


def test_aviasales_deeplink_format():
    url = _aviasales_deeplink("JFK", "LHR", "2026-10-20", 1)
    assert url.endswith("/JFK2010LHR1") or "JFK2010LHR1" in url


async def test_amadeus_token_cache_reuses_token():
    import httpx
    import respx

    cache = AmadeusTokenCache()
    with respx.mock:
        route = respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 1800})
        )
        t1 = await cache.get("k", "s")
        t2 = await cache.get("k", "s")
    assert t1 == t2 == "tok-1"
    assert route.call_count == 1
