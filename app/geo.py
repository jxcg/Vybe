"""Location helpers: walk time, geocoding and weather. All free, no keys."""

import math
import time
from typing import Any

import httpx

WALK_M_PER_MIN = 80  # ~4.8 km/h
DETOUR = 1.3  # streets aren't straight lines
_weather_cache: dict[tuple[float, float], tuple[float, bool]] = {}


def walk_mins(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Straight-line (haversine) distance turned into minutes on foot."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    metres = 2 * 6_371_000 * math.asin(math.sqrt(a))
    return max(1, round(metres * DETOUR / WALK_M_PER_MIN))


def geocode_postcode(q: str) -> tuple[float, float] | None:
    """UK full postcode ("SE1 7PB") or outcode ("SE1") via postcodes.io."""
    q = q.strip().replace(" ", "")
    for path in (f"postcodes/{q}", f"outcodes/{q}"):
        r = httpx.get(f"https://api.postcodes.io/{path}", timeout=5)
        if r.status_code == 200:
            res: dict[str, Any] = r.json()["result"]
            return float(res["latitude"]), float(res["longitude"])
    return None


def is_raining(lat: float, lng: float) -> bool:
    """Current precipitation from Open-Meteo, cached for 30 min per ~1 km cell."""
    cell = (round(lat, 2), round(lng, 2))
    hit = _weather_cache.get(cell)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lng, "current": "precipitation"},
            timeout=5,
        )
        raining = float(r.json()["current"]["precipitation"]) > 0
    except (httpx.HTTPError, KeyError, ValueError):
        raining = False  # weather is a nice-to-have; never block the feed on it
    _weather_cache[cell] = (time.time(), raining)
    return raining
