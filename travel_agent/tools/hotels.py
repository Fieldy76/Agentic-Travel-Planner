import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx

from ..config import Config
from .flights import _amadeus_token_cache  # reuse the same OAuth cache

logger = logging.getLogger(__name__)

AMADEUS_HOTELS_BY_CITY_URL = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
AMADEUS_HOTEL_OFFERS_URL = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
HOTELLOOK_BASE = "https://search.hotellook.com/hotels"


def _hotellook_deeplink(city: str, check_in: str, check_out: str, adults: int) -> str:
    """Build a Hotellook search deeplink, wrapped in Travelpayouts affiliate when set."""
    params = {
        "destination": city,
        "checkIn": check_in,
        "checkOut": check_out,
        "adults": adults,
    }
    target = f"{HOTELLOOK_BASE}?{urlencode(params)}"
    marker = Config.TRAVELPAYOUTS_MARKER
    if not marker:
        return target
    return f"{Config.CARS_AFFILIATE_HOST}?{urlencode({'marker': marker, 'trs': 'hotels', 'u': target})}"


async def search_hotels(city_code: str, check_in: str, check_out: str, adults: int = 1) -> List[Dict[str, Any]]:
    """Search hotels in a city for a given date range via Amadeus Hotel Search v3.

    Args:
        city_code: IATA city code (e.g. "PAR" for Paris, "ROM" for Rome).
        check_in: Arrival date (YYYY-MM-DD).
        check_out: Departure date (YYYY-MM-DD).
        adults: Number of adult guests (default 1).

    Returns a list of offers. Each offer includes a booking_url the user clicks
    to complete the reservation on Hotellook (real booking, real inventory).
    """
    try:
        ci = datetime.strptime(check_in, "%Y-%m-%d").date()
        co = datetime.strptime(check_out, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"Dates must be YYYY-MM-DD: {e}") from e
    if co <= ci:
        raise ValueError(f"check_out ({check_out}) must be after check_in ({check_in})")
    if adults < 1 or adults > 9:
        raise ValueError("adults must be between 1 and 9")

    if Config.FLIGHT_API_KEY and Config.FLIGHT_API_SECRET:
        try:
            return await _search_real_hotels(city_code, check_in, check_out, adults)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning("Amadeus hotels failed for %s: %s. Falling back to deeplink-only.", city_code, e)

    # Fallback: no live search, but still return a real booking deeplink + indicative pricing.
    nights = (co - ci).days
    estimate = 120 * nights * adults
    return [{
        "hotel_id": f"H{secrets.token_hex(3).upper()}",
        "name": f"Hotels in {city_code.upper()}",
        "city_code": city_code.upper(),
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "nights": nights,
        "estimated_total_price": estimate,
        "currency": "USD",
        "booking_url": _hotellook_deeplink(city_code, check_in, check_out, adults),
        "note": "Live search unavailable. Click booking_url for real-time prices on Hotellook.",
    }]


async def _search_real_hotels(city_code: str, check_in: str, check_out: str, adults: int) -> List[Dict[str, Any]]:
    token = await _amadeus_token_cache.get(Config.FLIGHT_API_KEY, Config.FLIGHT_API_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        list_response = await client.get(
            AMADEUS_HOTELS_BY_CITY_URL,
            headers=headers,
            params={"cityCode": city_code.upper()},
        )
        list_response.raise_for_status()
        hotels = (list_response.json().get("data") or [])[:20]
        hotel_ids = [h["hotelId"] for h in hotels if h.get("hotelId")]
        if not hotel_ids:
            raise ValueError(f"No hotels listed in {city_code}")

        offers_response = await client.get(
            AMADEUS_HOTEL_OFFERS_URL,
            headers=headers,
            params={
                "hotelIds": ",".join(hotel_ids[:10]),
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "adults": adults,
                "bestRateOnly": "true",
            },
        )
        offers_response.raise_for_status()
        offers_data = offers_response.json().get("data") or []

    results: List[Dict[str, Any]] = []
    for offer in offers_data[:10]:
        hotel_info = offer.get("hotel") or {}
        offers_list = offer.get("offers") or []
        if not offers_list:
            continue
        first_offer = offers_list[0]
        price = first_offer.get("price") or {}
        results.append({
            "hotel_id": hotel_info.get("hotelId"),
            "name": hotel_info.get("name"),
            "city_code": hotel_info.get("cityCode"),
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "price": float(price.get("total", 0)),
            "currency": price.get("currency", "USD"),
            "room_type": (first_offer.get("room") or {}).get("typeEstimated", {}).get("category"),
            "booking_url": _hotellook_deeplink(hotel_info.get("name") or city_code, check_in, check_out, adults),
        })

    if not results:
        raise ValueError("No offers returned by Amadeus")
    return results
