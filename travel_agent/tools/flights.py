import asyncio
import logging
import random
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from ..config import Config

logger = logging.getLogger(__name__)

AMADEUS_TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_FLIGHTS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
AVIASALES_BASE = "https://www.aviasales.com/search"

AIRLINE_MAP = {
    "DL": "Delta Air Lines",
    "UA": "United Airlines",
    "BA": "British Airways",
    "LH": "Lufthansa",
    "AF": "Air France",
    "AA": "American Airlines",
    "EK": "Emirates",
    "RY": "Ryanair",
    "AZ": "ITA Airways",
    "TP": "TAP Air Portugal",
    "VS": "Virgin Atlantic",
}


class FlightSearchArgs(BaseModel):
    origin: str = Field(..., description="Three-letter airport code (e.g., JFK).")
    destination: str = Field(..., description="Three-letter airport code (e.g., LHR).")
    date: str = Field(..., description="Date of travel (YYYY-MM-DD).")


class BookFlightArgs(BaseModel):
    flight_id: str = Field(..., description="The ID of the flight to book.")
    passenger_name: str = Field(..., description="Full name of the passenger.")
    passport_number: str = Field(..., description="Passport number of the passenger.")


class AmadeusTokenCache:
    """Async-safe cache for the Amadeus OAuth bearer token."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, client_id: str, client_secret: str) -> str:
        async with self._lock:
            now = time.time()
            if self._token and now < self._expires_at:
                return self._token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    AMADEUS_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
            self._token = data["access_token"]
            # Refresh 60s before expiry to avoid thundering herd
            self._expires_at = time.time() + data.get("expires_in", 1800) - 60
            return self._token


_amadeus_token_cache = AmadeusTokenCache()


async def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """Search for flights between origin and destination on a specific date."""
    if Config.FLIGHT_API_KEY and Config.FLIGHT_API_SECRET:
        try:
            return await _search_real_flights(origin, destination, date)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning("Amadeus API failed (%s -> %s on %s): %s. Using mock.", origin, destination, date, e)
    return await _search_mock_flights(origin, destination, date)


async def _search_real_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    token = await _amadeus_token_cache.get(Config.FLIGHT_API_KEY, Config.FLIGHT_API_SECRET)
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin.upper(),
        "destinationLocationCode": destination.upper(),
        "departureDate": date,
        "adults": 1,
        "max": 5,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(AMADEUS_FLIGHTS_URL, headers=headers, params=params, timeout=15.0)
        response.raise_for_status()
        data = response.json()

    offers = data.get("data", [])
    results: List[Dict[str, Any]] = []
    for offer in offers:
        itinerary = offer.get("itineraries", [{}])[0]
        segment = itinerary.get("segments", [{}])[0]
        price = offer.get("price", {})

        carrier_code = segment.get("carrierCode", "Unknown")
        airline_name = AIRLINE_MAP.get(carrier_code, carrier_code)

        results.append({
            "flight_id": offer.get("id"),
            "airline": f"{airline_name} ({carrier_code})",
            "airline_code": carrier_code,
            "flight_number": f"{carrier_code}{segment.get('number', '000')}",
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_time": segment.get("departure", {}).get("at"),
            "arrival_time": segment.get("arrival", {}).get("at"),
            "price": float(price.get("total", 0)),
            "currency": price.get("currency", "USD"),
            "duration": itinerary.get("duration", "Unknown"),
        })

    return results


CURRENCY_BY_REGION = {
    "GBP": (("LHR", "LGW", "MAN"), 0.8),
    "EUR": (("CDG", "FRA", "FCO", "MXP", "AMS", "MAD"), 0.92),
    "JPY": (("TYO", "HND", "NRT"), 150.0),
}


def _localize_price(origin: str) -> tuple[str, float]:
    upper = origin.upper()
    for currency, (codes, multiplier) in CURRENCY_BY_REGION.items():
        if upper in codes:
            return currency, multiplier
    return "USD", 1.0


async def _search_mock_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    logger.info("Mock flight search %s -> %s on %s", origin, destination, date)
    currency, multiplier = _localize_price(origin)
    airline_codes = list(AIRLINE_MAP.keys())

    results: List[Dict[str, Any]] = []
    for _ in range(3):
        code = random.choice(airline_codes)
        airline_name = AIRLINE_MAP[code]
        flight_num = f"{code}{random.randint(100, 999)}"
        base_price = random.randint(300, 1200)
        price = int(base_price * multiplier)
        results.append({
            "flight_id": flight_num,
            "airline": f"{airline_name} ({code})",
            "airline_code": code,
            "origin": origin,
            "destination": destination,
            "departure_time": f"{date}T{random.randint(6, 22):02d}:00:00",
            "price": price,
            "currency": currency,
        })
    return results


def _aviasales_deeplink(origin: str, destination: str, date: str, passengers: int = 1) -> str:
    """Build an Aviasales search deeplink in the form ORIGIN+DDMM+DEST+PAX.

    Example: JFK to LHR on 2026-10-20 for 1 pax -> /search/JFK2010LHR1
    Wrapped in Travelpayouts affiliate redirect when TRAVELPAYOUTS_MARKER is set.
    """
    dt = datetime.strptime(date, "%Y-%m-%d")
    slug = f"{origin.upper()}{dt.day:02d}{dt.month:02d}{destination.upper()}{passengers}"
    target = f"{AVIASALES_BASE}/{slug}"

    marker = Config.TRAVELPAYOUTS_MARKER
    if not marker:
        return target
    return f"{Config.CARS_AFFILIATE_HOST}?{urlencode({'marker': marker, 'trs': 'flights', 'u': target})}"


async def book_flight(
    origin: str,
    destination: str,
    date: str,
    passenger_name: str,
    passengers: int = 1,
) -> Dict[str, Any]:
    """Generate a booking URL for the chosen flight route.

    The agent must present the booking_url to the user; the user completes
    payment + ticketing on the hosted Aviasales/airline page. Returns a
    reservation_intent reference for tracking.
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"date must be YYYY-MM-DD: {e}") from e
    if dt.date() < datetime.now(timezone.utc).date():
        raise ValueError("date cannot be in the past")
    if passengers < 1 or passengers > 9:
        raise ValueError("passengers must be between 1 and 9")

    intent_ref = secrets.token_urlsafe(8).upper().replace("_", "").replace("-", "")[:10]
    booking_url = _aviasales_deeplink(origin, destination, date, passengers)
    logger.info(
        "Booking intent %s: %s->%s on %s (%d pax) for %s", intent_ref, origin, destination, date, passengers, passenger_name
    )
    return {
        "status": "pending_user_action",
        "intent_reference": f"BK{intent_ref}",
        "origin": origin.upper(),
        "destination": destination.upper(),
        "date": date,
        "passengers": passengers,
        "passenger_name": passenger_name,
        "booking_url": booking_url,
        "note": (
            "No money has been charged. Click booking_url to complete payment "
            "and ticketing on the partner site."
        ),
    }
