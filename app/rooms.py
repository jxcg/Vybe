"""Temporary meetup state and deterministic group ranking."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from secrets import token_urlsafe
from time import monotonic
from typing import Any

from fastapi import WebSocket

from app.geo import Weather
from app.ranking import rank

BUDGETS = {10: 1, 20: 2, 999: 3}
AGES = ("under18", "18-21", "22-25", "26-35", "36+")
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
NOT_INTO = {
    "clubs": "club",
    "loud music": "music",
    "late nights": "nightlife",
    "outdoors": "outdoors",
}
ROOM_LIFETIME = 4 * 60 * 60
MAX_ROOMS = 256
MAX_MEMBERS = 10
JOIN_KEY = re.compile(r"[0-9a-f]{64}")


def strings(value: object, count: int, length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v[:length] for v in value[:count] if isinstance(v, str) and v.strip()]


def preferences(data: object) -> dict[str, Any]:
    msg = data if isinstance(data, dict) else {}
    budget = msg.get("budget")
    age = msg.get("age")
    company = msg.get("company")
    return {
        "budget": budget if type(budget) is int and budget in BUDGETS else 999,
        "student": bool(msg.get("student")),
        "adult": bool(msg.get("adult", True)) and age != "under18",
        "include": [v.strip().lower() for v in strings(msg.get("include"), 20, 80)],
        "exclude": [v.strip().lower() for v in strings(msg.get("exclude"), 20, 80)],
        "company": min(10, max(1, company)) if type(company) is int else 1,
        "age": age if age in AGES else None,
        "vibe": msg.get("vibe") if msg.get("vibe") in ("chill", "lively") else None,
    }


@dataclass
class Member:
    name: str
    prefs: dict[str, Any]
    liked: set[str]
    socket: WebSocket | None
    skipped: set[str] = field(default_factory=set)

    def feedback(self, item_id: str, kind: object) -> None:
        if kind == "like":
            if len(self.liked) < 500:
                self.liked.add(item_id)
        elif kind == "unlike":
            self.liked.discard(item_id)
        elif kind == "skip" and len(self.skipped) < 500:
            self.skipped.add(item_id)


@dataclass
class Room:
    place: dict[str, Any]
    offset: timedelta
    invite: str = field(default_factory=token_urlsafe)
    expires: float = field(default_factory=lambda: monotonic() + ROOM_LIFETIME)
    members: dict[str, Member] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    source: tuple[list[dict[str, Any]], Weather | None] | None = None
    source_at: float = float("-inf")
    published_at: float = float("-inf")


rooms: dict[str, Room] = {}


def active_room(invite: object) -> Room | None:
    now = monotonic()
    for key, room in list(rooms.items()):
        if room.expires <= now:
            del rooms[key]
    return rooms.get(invite) if isinstance(invite, str) else None


def room_for_member(key: object) -> Room | None:
    active_room(None)
    if not isinstance(key, str):
        return None
    return next((room for room in rooms.values() if key in room.members), None)


def known_price(value: object) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value < float("inf"):
        return value
    return None


def excludes(item: dict[str, Any], exclusions: list[str]) -> bool:
    tags = set(item["tags"])
    name = item["name"].lower()
    return any(NOT_INTO.get(term, term) in tags or term in name for term in exclusions)


def preferred_tags(prefs: dict[str, Any], items: list[dict[str, Any]]) -> frozenset[str]:
    tags = {tag for item in items for tag in item["tags"]}
    return frozenset(tag for term in prefs["include"] if (tag := INTO.get(term, term)) in tags)


def group_rank(
    items: list[dict[str, Any]], now: datetime, weather: Weather | None, members: list[Member]
) -> list[dict[str, Any]]:
    cap = min(
        (m.prefs["budget"] for m in members if m.prefs["budget"] != 999), default=float("inf")
    )
    scored: list[dict[str, dict[str, Any]]] = []
    preferences_by_member = []
    for member in members:
        prefs = member.prefs
        prefer = preferred_tags(prefs, items)
        preferences_by_member.append(prefer)
        cards = rank(
            items,
            now,
            budget=BUDGETS[prefs["budget"]],
            student=prefs["student"],
            adult=prefs["adult"],
            liked=frozenset(member.liked),
            weather=weather,
            prefer=prefer,
            age=prefs["age"],
            vibe=prefs["vibe"],
            company=len(members),
            # The shared cap uses prices in pounds. Guessed tiers are neutral for unknown prices.
            shared_budget=prefs["budget"],
        )
        scored.append({c["id"]: c for c in cards})

    shared = frozenset.intersection(*preferences_by_member)
    ranked = []
    for item_id, card in scored[0].items():
        price = card.get("price")
        if price is not None and price > cap:
            continue
        if any(
            item_id not in cards or item_id in m.skipped or excludes(card, m.prefs["exclude"])
            for m, cards in zip(members, scored, strict=True)
        ):
            continue
        scores = [cards[item_id]["match"] for cards in scored]
        reasons = [r for r in card["reasons"] if r.startswith(("Open now", "Opens "))]
        common = sorted(shared.intersection(card["tags"]))
        if len(members) > 1 and common:
            who = "You both" if len(members) == 2 else "Everyone"
            reasons.insert(0, f"{who} picked {common[0]}")
        if price is None:
            reasons.append("Price unknown")
        ranked.append(
            {
                **card,
                "match": min(scores),
                "average": sum(scores) / len(scores),
                "reasons": reasons,
                "over_budget": False,
                "price_unknown": price is None,
            }
        )
    return sorted(ranked, key=lambda c: (-c["match"], -c["average"], c["id"]))
