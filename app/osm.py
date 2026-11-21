"""OpenStreetMap → Vybe items. Free, no key: Overpass for venues, Nominatim for place names."""

import re
import time
from datetime import datetime
from typing import Any

import httpx

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "vybe-hackathon-app/0.1"}  # both services ask for an identifying UA
CACHE_TTL = 6 * 3600
_cache: dict[tuple[float, float], tuple[float, list[dict[str, Any]]]] = {}

# (osm key, value) → (Vybe type, tag, adult only, price level)
KINDS: dict[tuple[str, str], tuple[str, str, bool, int]] = {
    ("amenity", "restaurant"): ("food_deal", "food", False, 2),
    ("amenity", "cafe"): ("food_deal", "food", False, 1),
    ("amenity", "fast_food"): ("food_deal", "food", False, 1),
    ("amenity", "bar"): ("activity", "nightlife", True, 2),
    ("amenity", "pub"): ("activity", "nightlife", True, 2),
    ("amenity", "nightclub"): ("activity", "nightlife", True, 2),
    ("amenity", "cinema"): ("activity", "culture", False, 2),
    ("amenity", "theatre"): ("activity", "culture", False, 3),
    ("amenity", "arts_centre"): ("activity", "culture", False, 1),
    ("tourism", "museum"): ("activity", "culture", False, 1),
    ("tourism", "gallery"): ("activity", "culture", False, 1),
    ("leisure", "bowling_alley"): ("activity", "active", False, 2),
    ("leisure", "amusement_arcade"): ("activity", "active", False, 1),
    ("leisure", "escape_game"): ("activity", "active", False, 3),
    ("leisure", "sports_centre"): ("activity", "active", False, 2),
    ("leisure", "park"): ("activity", "active", False, 1),
}
DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def _query(lat: float, lng: float) -> str:
    by_key: dict[str, list[str]] = {}
    for k, v in KINDS:
        by_key.setdefault(k, []).append(v)
    parts = "".join(
        f'nwr(around:1500,{lat},{lng})["{k}"~"^({"|".join(vs)})$"]["name"]["opening_hours"];'
        for k, vs in by_key.items()
    )
    return f"[out:json][timeout:20];({parts});out center 300;"


def nearby(lat: float, lng: float) -> list[dict[str, Any]]:
    """Raw OSM elements around a point, cached per ~1 km cell for 6 hours."""
    cell = (round(lat, 2), round(lng, 2))
    hit = _cache.get(cell)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    r = httpx.post(OVERPASS, data={"data": _query(lat, lng)}, headers=HEADERS, timeout=8)
    r.raise_for_status()
    elements: list[dict[str, Any]] = r.json().get("elements", [])
    _cache[cell] = (time.time(), elements)
    return elements


def geocode(q: str) -> tuple[float, float] | None:
    r = httpx.get(
        NOMINATIM,
        params={"q": q, "format": "json", "limit": 1, "countrycodes": "gb"},
        headers=HEADERS,
        timeout=5,
    )
    r.raise_for_status()
    hits: list[dict[str, Any]] = r.json()
    return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None


def _days(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        if a not in DAYS or (b and b not in DAYS):
            raise ValueError(part)
        i, j = DAYS.index(a), DAYS.index(b or a)
        out |= {d % 7 for d in range(i, j + 1 if j >= i else j + 8)}
    return out


def hours_on(spec: str, weekday: int) -> list[tuple[str, str]] | None:
    """Opening windows for a weekday (0 = Monday) from an OSM opening_hours string.

    shortcut: handles the common "Mo-Fr 09:00-17:00; Sa 10:00-16:00" forms only; holidays,
    months and sunrise rules return None (the venue is skipped). Swap for a full parser if
    too many real venues get dropped.
    """
    spec = spec.strip()
    if spec == "24/7":
        return [("00:00", "00:00")]  # equal times mean open 24 hours
    result: list[tuple[str, str]] | None = None
    try:
        for rule in filter(None, (r.strip() for r in spec.split(";"))):
            m = re.fullmatch(r"(?:([A-Za-z,\-]+)\s+)?(.+)", rule)
            assert m
            days, times = m.groups()
            if days and days not in ("off", "closed") and weekday not in _days(days):
                continue
            if times in ("off", "closed"):
                result = []
                continue
            windows = re.findall(r"(\d{2}:\d{2})-(\d{2}:\d{2})", times)
            if not windows or re.sub(r"[\d:,\-\s]", "", times):
                return None
            # later rules override earlier ones for the same day (OSM semantics)
            result = [(o, "23:59" if c == "24:00" else c) for o, c in windows]
    except (ValueError, AssertionError):
        return None
    return result


def to_item(el: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    tags: dict[str, str] = el.get("tags", {})
    keys = [(k, tags.get(k, "")) for k in ("amenity", "tourism", "leisure")]
    kind = next((KINDS[k] for k in keys if k in KINDS), None)
    windows = hours_on(tags.get("opening_hours", ""), now.weekday())
    if not kind or not windows:
        return None
    yesterday = hours_on(tags["opening_hours"], (now.weekday() - 1) % 7) or []
    # still inside last night's late window (e.g. 18:00-02:00 at 00:30)
    late = [(o, c) for o, c in yesterday if c < o and now.strftime("%H:%M") < c]
    open_now_or_later = [w for w in windows if w[1] < w[0] or w[1] > now.strftime("%H:%M")]
    if not (late or open_now_or_later):
        return None
    window = (late or open_now_or_later)[0]
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lng = el.get("lon") or el.get("center", {}).get("lon")
    if lat is None or lng is None:
        return None
    vtype, tag, adult, level = kind
    return {
        "id": f"osm-{el['type']}-{el['id']}",
        "name": tags["name"],
        "type": vtype,
        "price": None,
        "price_level": level,
        "student_price": False,
        "adult_only": adult,
        "rating": None,
        "opens": window[0],
        "closes": window[1],
        "lat": float(lat),
        "lng": float(lng),
        "tags": [tag, "outdoors" if tags.get("leisure") == "park" else "indoors"],
        "url": tags.get("website") or tags.get("contact:website"),
        "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}",
        "source": "OpenStreetMap",
    }
