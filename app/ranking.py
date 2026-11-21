"""Plain-code ranking: filter to what's open soon, then a personal match % for each place.

Google's star rating is shown as-is; the match % is about *you, right now* (quality is one part).
"""

from datetime import datetime, timedelta
from typing import Any

from app.geo import Weather

LOOKAHEAD = timedelta(hours=3)
MIN_STAY = timedelta(minutes=60)


def _window(item: dict[str, Any], now: datetime) -> tuple[datetime, datetime]:
    """Today's opening window; a close at or before opening means it closes after midnight."""
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    oh, om = map(int, item["opens"].split(":"))
    ch, cm = map(int, item["closes"].split(":"))
    opens = day + timedelta(hours=oh, minutes=om)
    closes = day + timedelta(hours=ch, minutes=cm)
    if closes <= opens:
        closes += timedelta(days=1)
        # still inside last night's window, e.g. 00:30 for a 19:00-01:00 venue
        if now < opens and now < closes - timedelta(days=1):
            opens -= timedelta(days=1)
            closes -= timedelta(days=1)
    return opens, closes


def rank(
    items: list[dict[str, Any]],
    now: datetime,
    budget: int = 3,
    student: bool = False,
    adult: bool = True,
    liked: frozenset[str] = frozenset(),
    weather: Weather | None = None,
) -> list[dict[str, Any]]:
    liked_tags = {t for i in items if i["id"] in liked for t in i["tags"]}
    cards = []
    for item in items:
        if item["price_level"] > budget or (item["adult_only"] and not adult):
            continue
        opens, closes = _window(item, now)
        walk = timedelta(minutes=item["walk_mins"])
        leave_by = closes - MIN_STAY - walk
        if opens > now + LOOKAHEAD or leave_by < now:
            continue

        left = (leave_by - now).total_seconds() / 60
        badge = "plenty" if left > 60 else "soon" if left > 15 else "last"
        overlap = len(liked_tags & set(item["tags"])) / max(len(item["tags"]), 1)
        student_deal = student and item["student_price"]
        outdoors = "outdoors" in item["tags"]

        # Match out of 100: likes 25, walk 20, budget 15, quality 15, weather 15, time 10.
        likes = overlap if liked_tags else 0.5  # no likes yet: neutral, not a penalty
        price = min(
            1.0, (budget - item["price_level"] + 1) / budget + (0.25 if student_deal else 0)
        )
        if weather is None:
            sky = 0.66
        elif outdoors:
            sky = 0.0 if weather.bad else 1.0
        else:
            sky = 1.0 if weather.bad else 0.66
        timing = 0.7 if opens > now else {"plenty": 1.0, "soon": 0.6, "last": 0.2}[badge]
        # 3.5 stars or below counts as 0, 5 stars as full; unrated (OpenStreetMap) as middling
        quality = max(0.0, (item["rating"] - 3.5) / 1.5) if item["rating"] else 0.5
        match = (
            likes * 25
            + max(0.0, 1 - item["walk_mins"] / 30) * 20
            + price * 15
            + quality * 15
            + sky * 15
            + timing * 10
        )

        weather_reason = None
        if weather and weather.bad and not outdoors:
            weather_reason = "Indoors, it's raining" if weather.raining else "Indoors, it's cold"
        elif weather and not weather.bad and outdoors:
            weather_reason = "Nice out"
        reasons = [
            "Open now" if opens <= now else f"Opens {opens:%H:%M}",
            weather_reason,
            "Matches your likes" if overlap else None,
            "Student price" if student_deal else None,
            "Short walk" if item["walk_mins"] <= 10 else None,
            "Within budget",
            item["tags"][0].capitalize(),
        ]
        cards.append(
            {
                **item,
                "match": round(match),
                "badge": badge,
                "leave_by": f"{leave_by:%H:%M}",
                "reasons": [r for r in reasons if r][:3],
            }
        )
    return sorted(cards, key=lambda c: (c["match"], c["rating"] or 0), reverse=True)
