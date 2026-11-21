import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import geo, osm, places, ws
from app.ranking import rank

HERE = Path(__file__).parent
SOHO = (51.5136, -0.1365)  # default when the browser gives no location

app = FastAPI(title="Vybe")


def load_samples() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads((HERE / "items.json").read_text()))


def items_near(lat: float, lng: float, now: datetime) -> list[dict[str, Any]]:
    """Google Places if a key is set, else OpenStreetMap (free); samples if both fail."""
    found = None
    try:
        if places.api_key():
            found = [i for p in places.nearby(lat, lng) if (i := places.to_item(p, now))]
        else:
            found = [i for e in osm.nearby(lat, lng) if (i := osm.to_item(e, now))]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        found = None  # fall back to samples so the demo never shows an empty screen
    items = found or load_samples()
    unique = {i["id"]: i for i in items}  # a place can match more than one search
    return [
        {**i, "walk_mins": geo.walk_mins(lat, lng, i["lat"], i["lng"])} for i in unique.values()
    ]


@app.get("/api/geocode")
def geocode(q: Annotated[str, Query(min_length=2, max_length=100)]) -> dict[str, float]:
    """Postcode or outcode ("SE1") via postcodes.io, then any place name via OpenStreetMap."""
    try:
        hit = geo.geocode_postcode(q) or osm.geocode(q)
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
    now: Annotated[str | None, Query(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")] = None,
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
        weather=geo.weather(lat, lng),
    )


@app.websocket("/ws")
async def socket(websocket: WebSocket) -> None:
    """The VYBE web frontend (web/) talks to the server only through this socket."""
    await ws.serve(websocket, items_near)


@app.get("/classic")
def classic() -> FileResponse:
    """The earlier single-file page, kept as a fallback."""
    return FileResponse(HERE / "static" / "index.html")


VOICEOVERS = HERE.parent / "data" / "voiceovers"  # Voxtral TTS clips from the pipeline
VOICEOVERS.mkdir(parents=True, exist_ok=True)
app.mount("/voiceovers", StaticFiles(directory=VOICEOVERS), name="voiceovers")

WEB = HERE.parent / "web" / "dist"
if WEB.is_dir():  # built with `cd web && npm run build`
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
else:

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(HERE / "static" / "index.html")
