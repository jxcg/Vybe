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
from app.colors import venue_colors
from app.ranking import rank

LONDON = ZoneInfo("Europe/London")
DEFAULT_PLACE = {"lat": 51.5136, "lng": -0.1365, "label": "Soho"}
BOARD_EVERY = 20  # seconds; keeps countdowns and statuses fresh
ENRICHED = Path(__file__).parent.parent / "data" / "enriched.json"

BUDGETS = {10: 1, 20: 2, 999: 3}  # frontend budget (£ cap) → our price level
# Fallback when an item has no category (sample data): taste tag → frontend category
CATEGORY = {"active": "games", "culture": "culture", "nightlife": "bar", "food": "food"}
GROUP = {"food": "Food", "bar": "Drinks", "culture": "Culture", "other": "Outdoors"}
# Frontend "into" tags → our taste tags (for ranking boosts)
INTO = {
    "active": "active",
    "competitive": "games",
    "culture": "culture",
    "chill": "culture",
    "food": "food",
    "a laugh": "comedy",
    "live music": "music",
    "late night": "nightlife",
}
# Frontend "not into" tags → our taste tags to drop
NOT_INTO = {
    "clubs": "club",
    "loud music": "music",
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
    "Pricier than your budget": "Wallet",
    "Active": "Zap",
    "Culture": "Palette",
    "Nightlife": "Beer",
    "Food": "Utensils",
    "Comedy": "Laugh",
    "Music": "Music",
    "Games": "Dices",
    "Film": "Film",
    "Theatre": "Ticket",
    "Club": "Moon",
    "Outdoors": "MapPin",
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


def _parse_local(value: object) -> datetime | None:
    """ISO time from the pipeline → naive London time, or None."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    return t.astimezone(LONDON).replace(tzinfo=None) if t.tzinfo else t


def _enriched() -> dict[str, Any]:
    """Mistral's pipeline output (Contract 1). Missing or broken file means no extras."""
    try:
        data = json.loads(ENRICHED.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _group_of(item: dict[str, Any]) -> str:
    category = item.get("category") or CATEGORY.get(item["tags"][0], "other")
    return str(item.get("group") or GROUP.get(category, "Entertainment"))


def to_rows(
    cards: list[dict[str, Any]], now: datetime, raining: bool, mixed: bool = True
) -> list[dict[str, Any]]:
    """`mixed`: pick the three hero cards from different groups (off when showing one group)."""
    extras = _enriched()
    rows = []
    for c in cards:
        extra = extras.get(c["id"]) or {}
        leave_by = datetime.fromisoformat(c["leave_by_at"])
        # A real start time only comes from the pipeline (an event or show found by the Scout).
        # Without one, a place is walk-in: shown as "Open till …", never as a time to turn up.
        starts = _parse_local(extra.get("starts_at"))
        if starts:
            leave_by = starts - timedelta(minutes=c["walk_mins"] + 5)
        allday = c.get("opens") == c.get("closes")
        price = extra.get("price", c.get("price"))
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "venue": c["name"],
                "category": c.get("category") or CATEGORY.get(c["tags"][0], "other"),
                # Beyond the contract: what people browse by (Food, Drinks, Entertainment, …)
                "group": c.get("group")
                or GROUP.get(
                    c.get("category") or CATEGORY.get(c["tags"][0], "other"), "Entertainment"
                ),
                "departure_time": starts.replace(tzinfo=LONDON).isoformat()
                if starts
                else _iso(c["closes_at"]),
                "departure_label": "Starts"
                if starts
                else "Open 24 hours"
                if allday
                else "Open till",
                "timed": bool(starts),
                "needs_booking": bool(c.get("needs_booking")),
                "status": _status(leave_by, now, "outdoors" in c["tags"], raining),
                "leave_by": leave_by.replace(tzinfo=LONDON).isoformat(),
                "walk_min": c["walk_mins"],
                "your_price": price,
                # Server extension: £, ££ or £££ when there's no exact price; over_budget sinks it
                "price_level": c.get("price_level", 2),
                "over_budget": bool(c.get("over_budget")),
                "was_price": None,
                "score": round(c["match"] / 10, 1),
                "pick": None,
                "reasons": [{"icon": _icon(r), "text": r} for r in c["reasons"]][:3],
                "photo_url": None,
                "colors": venue_colors(extra.get("brand_color")),
                "pitch": extra.get("deal") or extra.get("script") or "",
                "voiceover_url": extra.get("voiceover"),
                # Only bookable things get a Book button; walk-ins get Directions
                "booking_url": (extra.get("booking_url") or c.get("url"))
                if c.get("needs_booking")
                else None,
                "rating": c["rating"],
                "lat": c["lat"],
                "lng": c["lng"],
                "source_url": extra.get("source_url") or c.get("maps_url"),
                "checked_at": extra.get("checked_at") or now.replace(tzinfo=LONDON).isoformat(),
            }
        )
    # Over-budget places stay in the list but never take a hero pick
    live = [
        r for r in rows if r["status"] not in ("departed", "cancelled") and not r["over_budget"]
    ]
    # Picks: the best match, then the best from a different group, then a wildcard from a third
    # group (highest rated), so the three hero cards aren't three theatres.
    used: set[str] = set()
    for pick, key in (("best", None), ("runner_up", None), ("wildcard", "rating")):
        pool = [r for r in live if r["pick"] is None and (not mixed or r["group"] not in used)]
        if key:
            pool.sort(key=lambda r: -(r["rating"] or 0))
        if pool:
            pool[0]["pick"] = pick
            used.add(pool[0]["group"])
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
        self.group: str | None = None  # show only Food, Drinks, Entertainment, Culture or Outdoors
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
        counts: dict[str, int] = {}
        for i in items:
            g = _group_of(i)
            counts[g] = counts.get(g, 0) + 1
        if self.group:
            items = [i for i in items if _group_of(i) == self.group]
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
        rows = to_rows(cards, now, raining, mixed=self.group is None)
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
            "groups": counts,
            "group": self.group,
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
        elif kind == "show":
            g = msg.get("group")
            self.group = (
                g if g in ("Food", "Drinks", "Entertainment", "Culture", "Outdoors") else None
            )
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
