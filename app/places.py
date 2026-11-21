"""Google Places (New) → Vybe items, cached per ~1 km cell to stay inside the free tier."""

import os
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

API = "https://places.googleapis.com/v1/places"
FIELDS = ",".join(
    f"places.{f}"
    for f in [
        "id",
        "displayName",
        "location",
        "rating",
        "priceLevel",
        "priceRange",
        "regularOpeningHours",
        "types",
        "primaryType",
        "websiteUri",
        "googleMapsUri",
    ]
)
SEARCHES = {
    "activity": [
        "bowling_alley",
        "movie_theater",
        "museum",
        "art_gallery",
        "amusement_center",
        "park",
    ],
    "nightlife": ["night_club", "bar"],
    "food_deal": ["restaurant", "cafe"],
}
PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 1,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 3,
}
TAGS = {
    "bowling_alley": "active",
    "amusement_center": "active",
    "park": "active",
    "museum": "culture",
    "art_gallery": "culture",
    "movie_theater": "culture",
    "night_club": "nightlife",
    "bar": "nightlife",
    "restaurant": "food",
    "cafe": "food",
}
ADULT = {"night_club", "bar"}
# shops, chains and stations match our searches but aren't a plan for tonight
SKIP_PRIMARY = {
    "department_store",
    "supermarket",
    "grocery_store",
    "convenience_store",
    "fast_food_restaurant",
    "book_store",
    "clothing_store",
    "shopping_mall",
    "store",
    "transit_station",
    "subway_station",
    "train_station",
    "lodging",
    "hotel",
}
CACHE_TTL = 6 * 3600
_cache: dict[tuple[float, float], tuple[float, list[dict[str, Any]]]] = {}


def api_key() -> str | None:
    return os.environ.get("GOOGLE_PLACES_API_KEY")


def _post(endpoint: str, body: dict[str, Any], fields: str) -> list[dict[str, Any]]:
    key = api_key()
    assert key
    r = httpx.post(
        f"{API}:{endpoint}",
        json=body,
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": fields},
        timeout=10,
    )
    r.raise_for_status()
    places: list[dict[str, Any]] = r.json().get("places", [])
    return places


def nearby(lat: float, lng: float) -> list[dict[str, Any]]:
    """Raw places around a point: 3 calls (activities, nightlife, food) per cell every 6 hours."""
    cell = (round(lat, 2), round(lng, 2))
    hit = _cache.get(cell)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    places = []
    for kind, types in SEARCHES.items():
        body = {
            "includedTypes": types,
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 1500.0}
            },
        }
        # nightlife is its own search so bars don't crowd out other activities
        vtype = "activity" if kind == "nightlife" else kind
        places += [{**p, "_kind": vtype} for p in _post("searchNearby", body, FIELDS)]
    _cache[cell] = (time.time(), places)
    return places


def _hours_today(hours: dict[str, Any], now: datetime) -> tuple[str, str] | None:
    """Today's (opens, closes) as HH:MM, including a window that started yesterday."""
    today = (now.weekday() + 1) % 7  # Google: 0 = Sunday
    yesterday = (today - 1) % 7
    best: tuple[datetime, str, str] | None = None
    for p in hours.get("periods", []):
        o, c = p["open"], p.get("close")
        if c is None:  # open 24 hours
            return "00:00", "00:00"  # equal times mean open 24 hours
        opens, closes = f"{o['hour']:02}:{o['minute']:02}", f"{c['hour']:02}:{c['minute']:02}"
        if o["day"] == yesterday and c["day"] == today:
            end = now.replace(hour=c["hour"], minute=c["minute"])
            if now < end:
                return opens, closes
        if o["day"] == today:
            end = now.replace(hour=c["hour"], minute=c["minute"])
            if c["day"] != today:
                end += timedelta(days=1)
            # several periods a day (lunch, dinner): take the first that hasn't closed
            if end > now and (best is None or end < best[0]):
                best = (end, opens, closes)
    return (best[1], best[2]) if best else None


def to_item(place: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    primary = place.get("primaryType", "")
    if primary in SKIP_PRIMARY or primary.endswith("_store") or "lodging" in place.get("types", []):
        return None
    hours = _hours_today(place.get("regularOpeningHours", {}), now)
    if not hours:
        return None  # closed today or no hours: can't promise it's open
    types = place.get("types", [])
    tags = [TAGS[t] for t in types if t in TAGS][:1] or [
        "food" if place["_kind"] != "activity" else "active"
    ]
    tags.append("outdoors" if "park" in types else "indoors")
    start = place.get("priceRange", {}).get("startPrice", {}).get("units")
    return {
        "id": place["id"],
        "name": place["displayName"]["text"],
        "type": place["_kind"],
        "price": float(start) if start else None,
        # no price level usually means free entry (museums, galleries, parks)
        "price_level": PRICE_LEVELS.get(place.get("priceLevel", ""), 1),
        # shortcut: Google has no student data, the Scout agent adds deals later
        "student_price": False,
        "adult_only": bool(ADULT & set(types)),
        "rating": float(place["rating"]) if "rating" in place else None,
        "opens": hours[0],
        "closes": hours[1],
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
        "tags": tags,
        "url": place.get("websiteUri") or place.get("googleMapsUri"),
        "maps_url": place.get("googleMapsUri"),
        "source": "Google Places",
    }
