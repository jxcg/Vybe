"""The `/ws` WebSocket the VYBE web frontend talks to (see INTEGRATION.md and web/src/contract.ts).

Solo state lives on each connection. Shared plans keep only their members and the preferences
they bring in memory. Both boards use the plain-code ranking.
"""

import asyncio
import io
import json
import uuid
import wave
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app import geo, rooms, voice
from app.colors import venue_colors
from app.ranking import rank
from app.request_parse import parse_request
from app.rooms import BUDGETS, INTO, NOT_INTO

LONDON = ZoneInfo("Europe/London")
DEFAULT_PLACE = {"lat": 51.5136, "lng": -0.1365, "label": "Soho"}
BOARD_EVERY = 20  # seconds; keeps countdowns and statuses fresh
ENRICHED = Path(__file__).parent.parent / "data" / "enriched.json"
VOICEOVERS = ENRICHED.parent / "voiceovers"

# Review-based fields from Mistral's Enricher that ranking uses (Contract 1)
PERSONAL_FIELDS = (
    "audience",
    "liveliness",
    "good_for_groups",
    "audience_note",
)  # frontend budget (£ cap) → our price level
# Fallback when an item has no category (sample data): taste tag → frontend category
CATEGORY = {"active": "games", "culture": "culture", "nightlife": "bar", "food": "food"}
GROUP = {"food": "Food", "bar": "Drinks", "culture": "Culture", "other": "Outdoors"}
INTEREST_GROUP = {
    "food": "Food",
    "late night": "Drinks",
    "active": "Entertainment",
    "competitive": "Entertainment",
    "a laugh": "Entertainment",
    "live music": "Entertainment",
    "culture": "Culture",
    "chill": "Culture",
}
BROWSE_GROUPS = ("Food", "Drinks", "Entertainment", "Culture", "Outdoors")
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
    "Popular with": "Users",
    "Good for groups": "Users",
    "Lively": "Zap",
    "Laid-back": "Coffee",
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


def _voiceover_url(path: object) -> str | None:
    """`data/voiceovers/x.mp3` (from the pipeline) → `/voiceovers/x.mp3`, served by main.py."""
    if not isinstance(path, str) or not path:
        return None
    name = Path(path).name
    return f"/voiceovers/{name}" if (VOICEOVERS / name).is_file() else None


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
    rows = _board_rows(cards, now, raining)
    _assign_picks(rows, mixed)
    return rows


def _board_rows(
    cards: list[dict[str, Any]], now: datetime, raining: bool, shared: bool = False
) -> list[dict[str, Any]]:
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
        price = c.get("price") if shared else extra.get("price", c.get("price"))
        cached_theme = extra.get("theme")
        theme = cached_theme if isinstance(cached_theme, dict) else {}
        photo_url = theme.get("image_url")
        photo_credit = theme.get("image_credit")
        fade_start = theme.get("fade_start")
        has_photo = (
            theme.get("mode") == "photo"
            and isinstance(photo_url, str)
            and photo_url.startswith("https://")
            and isinstance(photo_credit, str)
            and bool(photo_credit.strip())
        )
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "venue": c["name"],
                "category": c.get("category") or CATEGORY.get(c["tags"][0], "other"),
                # Beyond the contract: what people browse by (Food, Drinks, Entertainment, …)
                "group": _group_of(c),
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
                "price_unknown": bool(c.get("price_unknown")),
                "was_price": None,
                "score": round(c["match"] / 10, 1),
                "pick": None,
                "reasons": [{"icon": _icon(r), "text": r} for r in c["reasons"]][:3],
                "photo_url": photo_url if has_photo else None,
                "google_place_photo": c.get("source") == "Google Places"
                and (not theme or isinstance(theme.get("google_photo"), dict)),
                "photo_credit": photo_credit if has_photo else None,
                "photo_fade_start": fade_start
                if theme.get("mode") == "photo"
                and type(fade_start) is int
                and 0 <= fade_start <= 60
                else None,
                "colors": venue_colors(theme.get("base") or extra.get("brand_color")),
                "pitch": extra.get("deal") or extra.get("script") or "",
                "voiceover_url": _voiceover_url(extra.get("voiceover")),
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
    return rows


def _assign_picks(rows: list[dict[str, Any]], mixed: bool) -> None:
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


SILENCE_PEAK = 600  # out of 32767: below this the clip is effectively silent


def _peak(pcm: bytes) -> int:
    """Loudest sample in little-endian PCM16."""
    samples = memoryview(pcm[: len(pcm) - len(pcm) % 2]).cast("h")
    return max((abs(x) for x in samples), default=0)


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
        self.prefs = rooms.preferences({})
        self.shared: rooms.Room | None = None
        self.credential: str | None = None
        self.place: dict[str, Any] = dict(DEFAULT_PLACE)
        self.liked: set[str] = set()
        self.skipped: set[str] = set()
        self.offset = timedelta()  # time travel
        self.group: str | None = None
        self.group_chosen = False
        self.audio = bytearray()
        self.talking = False

    async def send(self, msg: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(msg))

    def now(self) -> datetime:
        return datetime.now(LONDON).replace(tzinfo=None, microsecond=0) + self.offset

    def source(
        self, place: dict[str, Any], now: datetime
    ) -> tuple[list[dict[str, Any]], geo.Weather | None]:
        lat, lng = place["lat"], place["lng"]
        items = self.items_near(lat, lng, now)
        extras = _enriched()
        items = [
            {
                **i,
                **{
                    k: extras[i["id"]][k]
                    for k in PERSONAL_FIELDS
                    if k in (extras.get(i["id"]) or {})
                },
            }
            for i in items
        ]
        return items, geo.weather(lat, lng)

    def build_board(self) -> dict[str, Any]:
        now = self.now()
        items, weather = self.source(self.place, now)
        drop = {NOT_INTO[t] for t in self.prefs["exclude"] if t in NOT_INTO}
        words = [t for t in self.prefs["exclude"] if t not in NOT_INTO]
        items = [
            i
            for i in items
            if i["id"] not in self.skipped
            and not drop & set(i["tags"])
            and not any(w in i["name"].lower() for w in words)
        ]
        cards = rank(
            items,
            now,
            budget=BUDGETS.get(self.prefs["budget"], 3),
            student=self.prefs["student"],
            adult=self.prefs["adult"],
            liked=frozenset(self.liked),
            weather=weather,
            prefer=frozenset(INTO[t] for t in self.prefs["include"] if t in INTO),
            age=self.prefs.get("age"),
            vibe=self.prefs.get("vibe"),
            company=self.prefs.get("company", 1),
        )
        raining = bool(weather and weather.raining)
        rows = _board_rows(cards, now, raining)
        counts: dict[str, int] = {}
        for row in rows:
            if row["status"] not in ("departed", "cancelled"):
                g = row["group"]
                counts[g] = counts.get(g, 0) + 1
        group = self.group
        if not self.group_chosen:
            group = next(
                (g for tag in self.prefs["include"] if (g := INTEREST_GROUP.get(tag)) in counts),
                None,
            )
        if group:
            rows = [row for row in rows if row["group"] == group]
        _assign_picks(rows, mixed=group is None)
        return self.board_message(now, self.place, weather, rows, ["You"], counts, group)

    @staticmethod
    def board_message(
        now: datetime,
        place: dict[str, Any],
        weather: geo.Weather | None,
        rows: list[dict[str, Any]],
        members: list[str],
        counts: dict[str, int],
        group: str | None,
    ) -> dict[str, Any]:
        raining = bool(weather and weather.raining)
        if weather is None:
            summary = ""
        else:
            temp = f"{weather.temp_c:.0f}°C" if weather.temp_c is not None else ""
            summary = f"{'Raining' if weather.raining else 'Dry'}, {temp}".strip(", ")
        return {
            "type": "board",
            "now": now.replace(tzinfo=LONDON).isoformat(),
            "area": place["label"],
            "weather": {
                "summary": summary,
                "rain_from": now.replace(tzinfo=LONDON).isoformat() if raining else None,
            },
            "count": sum(r["status"] not in ("departed", "cancelled") for r in rows),
            "members": members,
            "rows": rows,
            "boarded": {},
            "decision": None,
            "groups": counts,
            "group": group,
        }

    async def board(self) -> None:
        if self.room and not self.shared:
            board = await run_in_threadpool(self.build_board)
            if not self.shared:
                await self.send(board)

    def member(self, room: rooms.Room) -> rooms.Member | None:
        member = room.members.get(self.credential or "")
        return member if member and member.socket is self.ws else None

    async def publish(self, room: rooms.Room) -> None:
        """Called under the room lock so every connected member sees updates in order."""
        if not room.members:
            return
        now = datetime.now(LONDON).replace(tzinfo=None, microsecond=0) + room.offset
        if room.source is None or monotonic() - room.source_at >= 60:
            items, weather = await run_in_threadpool(self.source, room.place, now)
            extras = _enriched()
            for item in items:
                enriched_price = rooms.known_price((extras.get(item["id"]) or {}).get("price"))
                item["price"] = (
                    enriched_price
                    if enriched_price is not None
                    else rooms.known_price(item.get("price"))
                )
            room.source = items, weather
            room.source_at = monotonic()
        items, weather = room.source
        members = list(room.members.values())
        cards = rooms.group_rank(items, now, weather, members)
        rows = _board_rows(cards, now, bool(weather and weather.raining), shared=True)
        rows = [row for row in rows if row["status"] not in ("departed", "cancelled")]
        for row, pick in zip(rows, ("best", "runner_up", "wildcard"), strict=False):
            row["pick"] = pick
        board = self.board_message(
            now, room.place, weather, rows, [m.name for m in members], {}, None
        )
        payload = json.dumps(board)

        async def deliver(member: rooms.Member) -> None:
            if member.socket is None:
                return
            try:
                await asyncio.wait_for(member.socket.send_text(payload), timeout=3)
            except (WebSocketDisconnect, RuntimeError, OSError, TimeoutError):
                member.socket = None

        await asyncio.gather(*(deliver(member) for member in members))
        room.published_at = monotonic()

    async def room_error(self, message: str) -> None:
        await self.send({"type": "room_error", "message": message})

    async def room_message(self, kind: str, msg: dict[str, Any]) -> None:
        room: rooms.Room | None
        supplied = msg.get("credential")
        join_key = (
            supplied if isinstance(supplied, str) and rooms.JOIN_KEY.fullmatch(supplied) else None
        )
        if kind == "room_create":
            if self.shared:
                return
            room = rooms.room_for_member(join_key)
            if room is None:
                if len(rooms.rooms) >= rooms.MAX_ROOMS:
                    await self.room_error("Vybe is hosting too many plans. Try again later.")
                    return
                room = rooms.Room(dict(self.place), self.offset)
                rooms.rooms[room.invite] = room
        elif kind == "room_resume" and msg.get("invite") is None:
            room = rooms.room_for_member(supplied)
        else:
            room = rooms.active_room(msg.get("invite"))
        if room is None:
            await self.room_error("This invite is invalid or has expired.")
            return
        async with room.lock:
            if rooms.active_room(room.invite) is None:
                await self.room_error("This invite is invalid or has expired.")
                return
            if kind == "room_check":
                await self.send({"type": "room_ready", "area": room.place["label"]})
                return
            if self.shared:
                return
            credential = supplied if kind == "room_resume" else join_key or token_urlsafe()
            member = room.members.get(credential) if isinstance(credential, str) else None
            if member is not None:
                member.socket = self.ws
            elif kind == "room_resume" or not isinstance(credential, str):
                await self.room_error("Your place in this plan has expired.")
                return
            else:
                if len(room.members) >= rooms.MAX_MEMBERS:
                    await self.room_error("This plan is full.")
                    return
                name = str(msg.get("name") or "").strip()[:32] or "Host"
                member = rooms.Member(
                    name,
                    rooms.preferences(msg.get("prefs")),
                    set(rooms.strings(msg.get("liked"), 500, 256)),
                    self.ws,
                )
                room.members[credential] = member
            self.shared, self.credential = room, credential
            await self.send(
                {
                    "type": "room_joined",
                    "invite": room.invite,
                    "credential": credential,
                    "prefs": member.prefs,
                    "liked": sorted(member.liked),
                }
            )
            await self.publish(room)

    async def update_room(self, kind: str, msg: dict[str, Any]) -> None:
        room = self.shared
        if room is None:
            return
        refresh_solo = False
        async with room.lock:
            member = self.member(room)
            if member is None or rooms.active_room(room.invite) is None:
                self.shared, self.credential = None, None
                await self.room_error("Your shared plan has ended.")
            elif kind == "room_leave":
                if self.credential:
                    del room.members[self.credential]
                if not room.members:
                    rooms.rooms.pop(room.invite, None)
                self.shared, self.credential = None, None
                self.room = self.room or uuid.uuid4().hex[:8]
                await self.send({"type": "room_left"})
                refresh_solo = True
                await self.publish(room)
            elif kind == "room_prefs":
                member.prefs = rooms.preferences(msg.get("prefs"))
                await self.publish(room)
            elif kind == "feedback":
                item_id = msg.get("item_id")
                if isinstance(item_id, str) and 0 < len(item_id) <= 256:
                    member.feedback(item_id, msg.get("kind"))
                    await self.publish(room)
            elif monotonic() - room.published_at >= BOARD_EVERY:
                await self.publish(room)
        if refresh_solo:
            await self.board()

    async def disconnect(self) -> None:
        room = self.shared
        if room:
            async with room.lock:
                member = self.member(room)
                if member:
                    member.socket = None

    def current_prefs(self) -> dict[str, Any]:
        member = self.member(self.shared) if self.shared else None
        return member.prefs if member else self.prefs

    def resolve(self, chips: dict[str, Any]) -> dict[str, Any]:
        """Relative requests: "cheaper" steps the budget down one notch (999 → 20 → 10)."""
        if chips.pop("cheaper", False):
            chips["budget"] = {999: 20, 20: 10, 10: 10}[self.current_prefs()["budget"]]
        return chips

    async def chips(self, chips: dict[str, Any], heard: str = "") -> None:
        await self.send({"type": "chips", **chips})
        if heard:
            await self.send({"type": "note", "text": heard})

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind in ("room_create", "room_join", "room_resume", "room_check"):
            await self.room_message(kind, msg)
        elif self.shared and kind in ("room_leave", "room_prefs", "feedback", "refresh_now"):
            await self.update_room(kind, msg)
        elif kind == "join" and not self.shared:
            self.room = uuid.uuid4().hex[:8]
            if "liked" in msg:
                self.liked = set(rooms.strings(msg["liked"], 500, 256))
            await self.send({"type": "joined", "room": self.room, "you": msg.get("name") or "You"})
            await self.board()
        elif kind == "prefs":
            previous_interests = self.prefs["include"]
            self.prefs = rooms.preferences(msg)
            if "liked" in msg:
                self.liked = set(rooms.strings(msg["liked"], 500, 256))
            if previous_interests != self.prefs["include"]:
                self.group_chosen = False
                self.group = None
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
            if msg.get("kind") == "like":
                self.liked.add(msg["item_id"])
            elif msg.get("kind") == "unlike":
                self.liked.discard(msg["item_id"])
            elif msg.get("kind") == "skip":
                self.skipped.add(msg["item_id"])
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
            self.group_chosen = True
            self.group = g if g in BROWSE_GROUPS else None
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
            await self.chips(self.resolve(parse_request(text)))

    async def voice(self) -> None:
        if not self.audio or _peak(bytes(self.audio)) < SILENCE_PEAK:
            # Silence makes speech models guess, so don't ask: just say we didn't hear anything.
            self.audio.clear()
            await self.chips(
                {"include": [], "exclude": []}, "Didn't catch that. Try again, or type instead."
            )
            return
        context = {"now": self.now().strftime("%H:%M"), "filters": self.current_prefs()}
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
        transcript = filters.get("transcript", "")
        if transcript:
            await self.send({"type": "transcript", "text": transcript, "final": True})
            # Exact amounts, group size and student come from the words said, not a vague level.
            chips = parse_request(transcript)
            # Keep specific things Voxtral picked out that were really said (e.g. "bowling")
            said = transcript.lower()
            extra = [
                w
                for w in filters.get("include_text", [])
                if w in said and w not in chips["include"]
            ]
            chips["include"] += extra
        else:
            chips = filters_to_chips(filters)
        await self.chips(self.resolve(chips), filters.get("reply", ""))


async def serve(ws: WebSocket, items_near: Any) -> None:
    await ws.accept()
    session = Session(ws, items_near)

    async def tick() -> None:
        while True:
            await asyncio.sleep(BOARD_EVERY)
            if session.shared:
                await session.update_room("tick", {})
            else:
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
        await session.disconnect()
