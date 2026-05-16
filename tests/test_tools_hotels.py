import httpx
import pytest
import respx

from travel_agent.tools.hotels import search_hotels


async def test_search_hotels_validates_dates():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await search_hotels("PAR", "not-a-date", "2026-06-05")


async def test_search_hotels_validates_order():
    with pytest.raises(ValueError, match="after"):
        await search_hotels("PAR", "2026-06-05", "2026-06-01")


async def test_search_hotels_validates_adults():
    with pytest.raises(ValueError, match="adults"):
        await search_hotels("PAR", "2026-06-01", "2026-06-05", adults=0)


async def test_search_hotels_falls_back_to_deeplink_without_keys():
    # No FLIGHT_API_KEY in conftest -> Amadeus skipped, deeplink fallback used.
    results = await search_hotels("PAR", "2026-06-01", "2026-06-05", adults=2)
    assert len(results) == 1
    assert "hotellook.com" in results[0]["booking_url"] or "tp.media" in results[0]["booking_url"]
    assert results[0]["nights"] == 4
    assert results[0]["estimated_total_price"] == 120 * 4 * 2


async def test_search_hotels_real_amadeus_path(monkeypatch):
    monkeypatch.setenv("FLIGHT_API_KEY", "k")
    monkeypatch.setenv("FLIGHT_API_SECRET", "s")
    import importlib
    import travel_agent.config as cfg_mod
    importlib.reload(cfg_mod)
    # reload tools that read Config at import
    import travel_agent.tools.flights as flights_mod
    importlib.reload(flights_mod)
    import travel_agent.tools.hotels as hotels_mod
    importlib.reload(hotels_mod)
    # Reset the (now-reloaded) token cache
    flights_mod._amadeus_token_cache = flights_mod.AmadeusTokenCache()
    hotels_mod._amadeus_token_cache = flights_mod._amadeus_token_cache

    with respx.mock:
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 1800})
        )
        respx.get("https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city").mock(
            return_value=httpx.Response(200, json={"data": [
                {"hotelId": "HOTELA"}, {"hotelId": "HOTELB"}
            ]})
        )
        respx.get("https://test.api.amadeus.com/v3/shopping/hotel-offers").mock(
            return_value=httpx.Response(200, json={"data": [
                {
                    "hotel": {"hotelId": "HOTELA", "name": "Hotel A", "cityCode": "PAR"},
                    "offers": [{"price": {"total": "250.00", "currency": "EUR"},
                                "room": {"typeEstimated": {"category": "STANDARD"}}}],
                }
            ]})
        )
        results = await hotels_mod.search_hotels("PAR", "2026-06-01", "2026-06-05", adults=2)

    assert len(results) == 1
    assert results[0]["name"] == "Hotel A"
    assert results[0]["price"] == 250.0
    assert results[0]["currency"] == "EUR"
    # Restore env for downstream tests
    monkeypatch.delenv("FLIGHT_API_KEY", raising=False)
    monkeypatch.delenv("FLIGHT_API_SECRET", raising=False)
