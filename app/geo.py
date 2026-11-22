"""Location helpers: walk time, geocoding and weather. All free, no keys."""

import math
import time
from dataclasses import dataclass
from typing import Any

import httpx

WALK_M_PER_MIN = 80  # ~4.8 km/h
DETOUR = 1.3  # streets aren't straight lines
_weather_cache: dict[tuple[float, float], tuple[float, "Weather | None"]] = {}


def cache_set(cache: dict[Any, tuple[float, Any]], key: Any, value: Any, ttl: float) -> None:
    """Store in a TTL cache, first purging expired entries.

    The caches are keyed by user-supplied ~1 km cells (location message, /api/feed), so
    without eviction any client could grow them without bound.
    """
    now = time.time()
    for stale in [k for k, (fetched, _) in cache.items() if now - fetched >= ttl]:
        del cache[stale]
    cache[key] = (now, value)


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
    if not q.isalnum():  # it goes into a URL path
        return None
    for path in (f"postcodes/{q}", f"outcodes/{q}"):
        r = httpx.get(f"https://api.postcodes.io/{path}", timeout=5)
        if r.status_code == 200:
            res: dict[str, Any] = r.json()["result"]
            return float(res["latitude"]), float(res["longitude"])
    return None


@dataclass(frozen=True)
class Weather:
    raining: bool = False
    temp_c: float | None = None

    @property
    def bad(self) -> bool:
        """Weather that makes indoors the better choice."""
        return self.raining or (self.temp_c is not None and self.temp_c < 8)


def weather(lat: float, lng: float) -> Weather | None:
    """Current rain and temperature from Open-Meteo, cached for 30 min per ~1 km cell."""
    cell = (round(lat, 2), round(lng, 2))
    hit = _weather_cache.get(cell)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lng, "current": "precipitation,temperature_2m"},
            timeout=5,
        )
        cur = r.json()["current"]
        w: Weather | None = Weather(float(cur["precipitation"]) > 0, float(cur["temperature_2m"]))
    except (httpx.HTTPError, KeyError, ValueError):
        w = None  # weather is a nice-to-have; never block the feed on it
    cache_set(_weather_cache, cell, w, 1800)
    return w
