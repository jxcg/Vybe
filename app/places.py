"""Google Places (New) → Vybe items, cached per ~1 km cell to stay inside the free tier."""

import os
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.categories import google_kind, tags_for

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
# One call per group so bars and restaurants don't crowd out everything else (20 results each)
SEARCHES = {
    "activity": [
        "comedy_club",
        "live_music_venue",
        "performing_arts_theater",
        "movie_theater",
        "bowling_alley",
        "video_arcade",
        "karaoke",
        "amusement_center",
    ],
    "culture": ["museum", "art_gallery", "concert_hall", "park"],
    "nightlife": ["bar", "pub", "cocktail_bar", "wine_bar", "night_club"],
    "food_deal": ["restaurant", "pizza_restaurant", "cafe", "dessert_shop"],
}
PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 1,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 3,
}
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
# Usual price level when Google gives none (museums, galleries, parks are often free)
USUAL_PRICE = {"theatre": 3, "culture": 1, "outdoors": 1}
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
    """Raw places around a point: one call per search group, per cell, every 6 hours."""
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
        vtype = "food_deal" if kind == "food_deal" else "activity"
        places += [{**p, "_kind": vtype} for p in _post("searchNearby", body, FIELDS)]
    places = list({p["id"]: p for p in places}.values())  # one place can match several searches
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
    types = place.get("types", [])
    kind = google_kind(types, primary)
    if kind is None:
        return None
    if kind.booking:
        # Theatres, gigs and cinemas list box-office hours, not show times, so ignore them.
        # shortcut: treat as bookable for this evening; real start times come from the Scout agent.
        hours: tuple[str, str] | None = ("00:00", "23:30")
    else:
        hours = _hours_today(place.get("regularOpeningHours", {}), now)
    if not hours:
        return None  # closed today or no hours: can't promise it's open
    start = place.get("priceRange", {}).get("startPrice", {}).get("units")
    return {
        "id": place["id"],
        "name": place["displayName"]["text"],
        "type": place["_kind"],
        "price": float(start) if start else None,
        # Google often has no price level; fall back to what that kind of place usually costs
        "price_level": PRICE_LEVELS.get(place.get("priceLevel", ""), USUAL_PRICE.get(kind.tag, 2)),
        # shortcut: Google has no student data, the Scout agent adds deals later
        "student_price": False,
        "adult_only": kind.adult,
        "rating": float(place["rating"]) if "rating" in place else None,
        "opens": hours[0],
        "closes": hours[1],
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
        "tags": tags_for(kind, outdoors="park" in types)
        + (["pizza"] if "pizza_restaurant" in types or primary == "pizza_restaurant" else []),
        "category": kind.category,
        "group": kind.group,
        "needs_booking": kind.booking,
        "url": place.get("websiteUri") or place.get("googleMapsUri"),
        "maps_url": place.get("googleMapsUri"),
        "source": "Google Places",
    }


def _place_photos(place_id: str, key: str) -> dict[str, Any]:
    details = httpx.get(
        f"{API}/{place_id}",
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "photos,googleMapsUri"},
        timeout=5,
    )
    details.raise_for_status()
    return dict(details.json())


def _resolve_photo(place_id: str, key: str, photo: dict[str, Any]) -> str | None:
    name = photo.get("name", "")
    if photo.get("widthPx", 0) < 1080 or not name.startswith(f"places/{place_id}/photos/"):
        return None
    media = httpx.get(
        f"https://places.googleapis.com/v1/{name}/media",
        headers={"X-Goog-Api-Key": key},
        params={"maxWidthPx": 1440, "skipHttpRedirect": "true"},
        timeout=5,
    )
    media.raise_for_status()
    url = media.json().get("photoUri")
    return url if isinstance(url, str) and url.startswith("https://") else None


def photo_candidates(place_id: str) -> list[dict[str, Any]]:
    """Resolve up to three fresh Google photos for the background theme activity."""
    key = api_key()
    if not key:
        return []
    place = _place_photos(place_id, key)
    candidates = []
    for index, photo in enumerate(place.get("photos", [])[:3]):
        if photo.get("heightPx", 0) > 0 and (url := _resolve_photo(place_id, key, photo)):
            candidates.append(
                {"url": url, "index": index, "width": photo["widthPx"], "height": photo["heightPx"]}
            )
    return candidates


def featured_photo(place_id: str, selection: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve the reviewed photo from current Places metadata."""
    key = api_key()
    if not key or not any(
        time.time() - fetched_at < CACHE_TTL and any(place["id"] == place_id for place in results)
        for fetched_at, results in _cache.values()
    ):
        return None
    place = _place_photos(place_id, key)
    for index, photo in enumerate(place.get("photos", [])[:3]):
        if selection is not None and selection != {
            "index": index,
            "width": photo.get("widthPx"),
            "height": photo.get("heightPx"),
        }:
            continue
        if url := _resolve_photo(place_id, key, photo):
            return {
                "url": url,
                "authors": photo.get("authorAttributions", []),
                "source_url": photo.get("googleMapsUri") or place.get("googleMapsUri"),
            }
    return None
