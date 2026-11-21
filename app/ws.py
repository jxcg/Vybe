"""The `/ws` WebSocket the VYBE web frontend talks to (see INTEGRATION.md and web/src/contract.ts).

One socket per phone. Session state (prefs, voice chips, likes, time travel) lives only in this
connection, so nothing the user says is ever saved. The board is built from our plain-code ranking.
"""

import asyncio
import io
import json
import uuid
import wave
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app import geo, voice
from app.ranking import rank

LONDON = ZoneInfo("Europe/London")
DEFAULT_PLACE = {"lat": 51.5136, "lng": -0.1365, "label": "Soho"}
BOARD_EVERY = 20  # seconds; keeps countdowns and statuses fresh
ENRICHED = Path(__file__).parent.parent / "data" / "enriched.json"

BUDGETS = {10: 1, 20: 2, 999: 3}  # frontend budget (£ cap) → our price level
CATEGORY = {"active": "games", "culture": "culture", "nightlife": "bar", "food": "food"}
# Frontend "into" tags → our tags (for ranking boosts)
INTO = {
    "active": "active",
    "competitive": "active",
    "culture": "culture",
    "chill": "culture",
    "food": "food",
    "a laugh": "nightlife",
    "live music": "nightlife",
    "late night": "nightlife",
}
# Frontend "not into" tags → our tags to drop
NOT_INTO = {
    "clubs": "nightlife",
    "loud music": "nightlife",
    "late nights": "nightlife",
    "outdoors": "outdoors",
}
ICONS = {
    "Open now": "Clock",
    "Opens": "Clock",
    "Matches your likes": "Heart",
    "Student price": "Wallet",
    "Free entry": "Ticket",
    "Nice out": "Sparkles",
    "Indoors, it's raining": "CloudRain",
    "Top rated": "Star",
    "Short walk": "Footprints",
    "Within budget": "Wallet",
    "Active": "Zap",
    "Culture": "Palette",
    "Nightlife": "Beer",
    "Food": "Utensils",
}


def _iso(naive_local: str) -> str:
    return datetime.fromisoformat(naive_local).replace(tzinfo=LONDON).isoformat()


def _status(row_leave_by: datetime, now: datetime, outdoors: bool, raining: bool) -> str:
    mins = (row_leave_by - now).total_seconds() / 60
    if outdoors and raining and mins >= 0:
        return "delayed_rain"
    if mins < 0:
        return "departed"
    return "on_time" if mins >= 20 else "boarding" if mins >= 5 else "last_call"


def _icon(reason: str) -> str:
    return next((icon for prefix, icon in ICONS.items() if reason.startswith(prefix)), "Sparkles")


def _enriched() -> dict[str, Any]:
    """Mistral's pipeline output (Contract 1). Missing or broken file means no extras."""
    try:
        data = json.loads(ENRICHED.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def to_rows(cards: list[dict[str, Any]], now: datetime, raining: bool) -> list[dict[str, Any]]:
    extras = _enriched()
    rows = []
    for c in cards:
        extra = extras.get(c["id"]) or {}
        leave_by = datetime.fromisoformat(c["leave_by_at"])
        price = extra.get("price", c.get("price"))
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "venue": c["name"],
                "category": CATEGORY.get(c["tags"][0], "other"),
                "departure_time": _iso(c["closes_at"]),
                "departure_label": "Kitchen closes" if c["type"] == "food_deal" else "Last entry",
                "status": _status(leave_by, now, "outdoors" in c["tags"], raining),
                "leave_by": _iso(c["leave_by_at"]),
                "walk_min": c["walk_mins"],
                "your_price": price,
                "was_price": None,
                "score": round(c["match"] / 10, 1),
                "pick": None,
                "reasons": [{"icon": _icon(r), "text": r} for r in c["reasons"]][:3],
                "photo_url": None,
                "colors": None,
                "pitch": extra.get("deal") or extra.get("script") or "",
                "voiceover_url": extra.get("voiceover"),
                "booking_url": c.get("url"),
                "rating": c["rating"],
                "lat": c["lat"],
                "lng": c["lng"],
                "source_url": extra.get("source_url") or c.get("maps_url"),
                "checked_at": extra.get("checked_at") or now.replace(tzinfo=LONDON).isoformat(),
            }
        )
    live = [r for r in rows if r["status"] not in ("departed", "cancelled")]
    if live:
        live[0]["pick"] = "best"
    if len(live) > 1:
        live[1]["pick"] = "runner_up"
    # Wildcard: the best-rated place from a category the top two don't cover
    taken = {r["category"] for r in live[:2]}
    wild = sorted(
        (r for r in live[2:] if r["category"] not in taken), key=lambda r: -(r["rating"] or 0)
    )
    if wild:
        wild[0]["pick"] = "wildcard"
    return rows


def text_to_chips(text: str) -> dict[str, Any]:
    """Fallback for typed requests: pick out known tags and budget words.

    shortcut: keyword matching only; swap for a Mistral text→filters call once voice.py has one.
    """
    t = text.lower()
    chips: dict[str, Any] = {"include": [], "exclude": []}
    for tag in INTO:
        if tag in t and not any(f"{neg} {tag}" in t for neg in ("no", "not", "nothing")):
            chips["include"].append(tag)
    for tag in NOT_INTO:
        if any(f"{neg} {tag}" in t for neg in ("no", "not", "nothing", "avoid")):
            chips["exclude"].append(tag)
    if any(w in t for w in ("cheap", "free", "skint", "broke")):
        chips["budget"] = 10
    return chips


def filters_to_chips(f: dict[str, Any]) -> dict[str, Any]:
    """Voxtral filters (Contract 2) → the frontend's chip vocabulary."""
    back = {"active": "active", "culture": "culture", "food": "food", "nightlife": "late night"}
    include = [back[t] for t in f.get("include_tags", []) if t in back] + f.get("include_text", [])
    exclude = ["clubs" if t == "nightlife" else t for t in f.get("exclude_tags", [])]
    exclude += f.get("exclude_text", [])
    if f.get("indoors_only"):
        exclude.append("outdoors")
    chips: dict[str, Any] = {"include": include, "exclude": sorted(set(exclude) - set(include))}
    if "budget" in f:
        chips["budget"] = {1: 10, 2: 20, 3: 999}.get(f["budget"], 999)
    return chips


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Session:
    def __init__(self, ws: WebSocket, items_near: Any) -> None:
        self.ws = ws
        self.items_near = items_near
        self.room: str | None = None
        self.prefs: dict[str, Any] = {
            "budget": 999,
            "student": False,
            "adult": True,
            "include": [],
            "exclude": [],
        }
        self.place: dict[str, Any] = dict(DEFAULT_PLACE)
        self.liked: set[str] = set()
        self.skipped: set[str] = set()
        self.offset = timedelta()  # time travel
        self.audio = bytearray()
        self.talking = False

    async def send(self, msg: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(msg))

    def now(self) -> datetime:
        return datetime.now(LONDON).replace(tzinfo=None, microsecond=0) + self.offset

    def build_board(self) -> dict[str, Any]:
        now = self.now()
        lat, lng = self.place["lat"], self.place["lng"]
        items = self.items_near(lat, lng, now)
        drop = {NOT_INTO[t] for t in self.prefs["exclude"] if t in NOT_INTO}
        words = [t for t in self.prefs["exclude"] if t not in NOT_INTO]
        items = [
            i
            for i in items
            if i["id"] not in self.skipped
            and not drop & set(i["tags"])
            and not any(w in i["name"].lower() for w in words)
        ]
        weather = geo.weather(lat, lng)
        cards = rank(
            items,
            now,
            budget=BUDGETS.get(self.prefs["budget"], 3),
            student=self.prefs["student"],
            adult=self.prefs["adult"],
            liked=frozenset(self.liked),
            weather=weather,
            prefer=frozenset(INTO[t] for t in self.prefs["include"] if t in INTO),
        )
        raining = bool(weather and weather.raining)
        rows = to_rows(cards, now, raining)
        if weather is None:
            summary = ""
        else:
            temp = f"{weather.temp_c:.0f}°C" if weather.temp_c is not None else ""
            summary = f"{'Raining' if weather.raining else 'Dry'}, {temp}".strip(", ")
        return {
            "type": "board",
            "now": now.replace(tzinfo=LONDON).isoformat(),
            "area": self.place["label"],
            "weather": {
                "summary": summary,
                "rain_from": now.replace(tzinfo=LONDON).isoformat() if raining else None,
            },
            "count": sum(r["status"] not in ("departed", "cancelled") for r in rows),
            "members": ["You"],
            "rows": rows,
            "boarded": {},
            "decision": None,
        }

    async def board(self) -> None:
        if self.room:
            await self.send(await run_in_threadpool(self.build_board))

    async def chips(self, chips: dict[str, Any], heard: str = "") -> None:
        await self.send({"type": "chips", **chips})
        if heard:
            await self.send({"type": "note", "text": heard})

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "join":
            self.room = msg.get("room") or uuid.uuid4().hex[:8]
            await self.send({"type": "joined", "room": self.room, "you": msg.get("name") or "You"})
            await self.board()
        elif kind == "prefs":
            self.prefs = {
                "budget": msg.get("budget", 999) if msg.get("budget") in BUDGETS else 999,
                "student": bool(msg.get("student")),
                "adult": bool(msg.get("adult", True)),
                "include": [str(t).lower() for t in msg.get("include", [])][:20],
                "exclude": [str(t).lower() for t in msg.get("exclude", [])][:20],
            }
            await self.board()
        elif kind == "location":
            lat, lng = msg.get("lat"), msg.get("lng")
            if (
                isinstance(lat, int | float)
                and isinstance(lng, int | float)
                and -90 <= lat <= 90
                and -180 <= lng <= 180
            ):
                self.place = {
                    "lat": float(lat),
                    "lng": float(lng),
                    "label": str(msg.get("label") or "Near you")[:40],
                }
                await self.board()
        elif kind == "feedback" and isinstance(msg.get("item_id"), str):
            (self.liked if msg.get("kind") == "like" else self.skipped).add(msg["item_id"])
            await self.board()
        elif kind == "time_travel":
            try:
                target = (
                    datetime.fromisoformat(str(msg["now"])).astimezone(LONDON).replace(tzinfo=None)
                )
                self.offset = target - datetime.now(LONDON).replace(tzinfo=None)
            except (KeyError, ValueError):
                return
            await self.board()
        elif kind == "refresh_now":
            await self.send({"type": "note", "text": "Refreshing what's on…"})
            await self.board()
        elif kind == "talk_start":
            self.audio.clear()
            self.talking = True
        elif kind == "talk_end":
            self.talking = False
            await self.voice()
        elif kind == "talk_text" and isinstance(msg.get("text"), str):
            text = msg["text"][:300]
            await self.send({"type": "transcript", "text": text, "final": True})
            await self.chips(text_to_chips(text))

    async def voice(self) -> None:
        if not self.audio:
            await self.chips(
                {"include": [], "exclude": []}, "Didn't catch any audio. Try typing instead."
            )
            return
        context = {"now": self.now().strftime("%H:%M"), "filters": self.prefs}
        try:
            filters = await run_in_threadpool(
                voice.audio_to_filters, pcm_to_wav(bytes(self.audio)), "audio/wav", context
            )
        except voice.VoiceError:
            await self.chips(
                {"include": [], "exclude": []}, "Voice is having a moment. Try typing instead."
            )
            return
        finally:
            self.audio.clear()
        await self.chips(filters_to_chips(filters), filters.get("reply", ""))


async def serve(ws: WebSocket, items_near: Any) -> None:
    await ws.accept()
    session = Session(ws, items_near)

    async def tick() -> None:
        while True:
            await asyncio.sleep(BOARD_EVERY)
            await session.board()

    ticker = asyncio.create_task(tick())
    try:
        while True:
            frame = await ws.receive()
            if frame["type"] == "websocket.disconnect":
                break
            if frame.get("bytes") is not None:
                if session.talking and len(session.audio) < 16000 * 2 * 20:  # cap at 20 s of audio
                    session.audio.extend(frame["bytes"])
                continue
            try:
                msg = json.loads(frame.get("text") or "")
            except ValueError:
                continue
            if isinstance(msg, dict):
                await session.handle(msg)
    except WebSocketDisconnect:
        pass
    finally:
        ticker.cancel()
