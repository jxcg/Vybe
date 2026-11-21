"""Plain-code ranking: filter to what's open soon, then score out of 10."""

from datetime import datetime, timedelta
from typing import Any

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
    raining: bool = False,
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
        score = (
            item["rating"] / 5 * 3
            + (budget - item["price_level"] + 1) / budget * 2
            + (0.5 if student_deal else 0)
            + max(0.0, 1 - item["walk_mins"] / 30) * 2
            + overlap * 2.5
            + (-1.5 if raining and outdoors else 0)
        )

        reasons = [
            "Open now" if opens <= now else f"Opens {opens:%H:%M}",
            "Indoors, it's raining" if raining and not outdoors else None,
            "Student price" if student_deal else "Within budget",
            "Matches your likes" if overlap else None,
            "Short walk" if item["walk_mins"] <= 10 else None,
            f"Rated {item['rating']}",
            item["tags"][0].capitalize(),
        ]
        cards.append(
            {
                **item,
                "score": round(min(score, 10), 1),
                "badge": badge,
                "leave_by": f"{leave_by:%H:%M}",
                "reasons": [r for r in reasons if r][:3],
            }
        )
    return sorted(cards, key=lambda c: c["score"], reverse=True)
