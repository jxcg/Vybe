import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app import geo, places
from app.ranking import rank

HERE = Path(__file__).parent
SOHO = (51.5136, -0.1365)  # default when the browser gives no location

app = FastAPI(title="Vybe")


def load_samples() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads((HERE / "items.json").read_text()))


def items_near(lat: float, lng: float, now: datetime) -> list[dict[str, Any]]:
    """Google Places when a key is set (sample data if not, or if Google fails), with walk times."""
    found = None
    if places.api_key():
        try:
            found = [i for p in places.nearby(lat, lng) if (i := places.to_item(p, now))]
        except httpx.HTTPError:
            found = None  # fall back to samples so the demo never shows an empty screen
    items = found or load_samples()
    return [{**i, "walk_mins": geo.walk_mins(lat, lng, i["lat"], i["lng"])} for i in items]


@app.get("/api/geocode")
def geocode(q: Annotated[str, Query(min_length=2, max_length=100)]) -> dict[str, float]:
    """Postcode or outcode ("SE1") first, which is free, then any place name via Google."""
    try:
        hit = geo.geocode_postcode(q)
        if hit is None and places.api_key():
            hit = places.geocode(q)
    except httpx.HTTPError as e:
        raise HTTPException(502, "Location lookup failed") from e
    if hit is None:
        raise HTTPException(404, "Couldn't find that place")
    return {"lat": hit[0], "lng": hit[1]}


@app.get("/api/feed")
def feed(
    lat: Annotated[float, Query(ge=-90, le=90)] = SOHO[0],
    lng: Annotated[float, Query(ge=-180, le=180)] = SOHO[1],
    budget: Annotated[int, Query(ge=1, le=3)] = 3,
    student: bool = False,
    adult: bool = True,
    liked: str = "",
    now: Annotated[str | None, Query(pattern=r"^\d{2}:\d{2}$")] = None,
) -> list[dict[str, Any]]:
    """`liked` is comma-separated item ids from the browser; `now` (HH:MM) is for time travel."""
    at = datetime.now()
    if now:
        h, m = map(int, now.split(":"))
        at = at.replace(hour=h, minute=m, second=0, microsecond=0)
    return rank(
        items_near(lat, lng, at),
        at,
        budget=budget,
        student=student,
        adult=adult,
        liked=frozenset(filter(None, liked.split(","))),
        raining=geo.is_raining(lat, lng),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
