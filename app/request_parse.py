"""Turn what someone typed or said into the web app's chips: budget, company, student, tags.

One deterministic, lenient parser for both paths (the typed box and Voxtral's transcript), following
the speech-to-tag rules in INTEGRATION.md §5. Amounts are read exactly ("under £20" → 20), never
guessed from vague levels, and common typos are forgiven.
"""

import re
from difflib import get_close_matches
from typing import Any

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "twenty five": 25, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
}  # fmt: skip
MONEY_SLANG = {"fiver": 5, "tenner": 10, "score": 20, "pony": 25, "ton": 100}
CHEAP = ("cheap", "cheapo", "skint", "broke", "budget", "free", "low cost", "not expensive")
ANY_PRICE = (
    "no object", "whatever it costs", "splash out", "treat myself", "don't care about price",
    "dont care about price", "any price", "money is no", "forget the budget",
)  # fmt: skip
NEG = r"(?:no|not|nothing|avoid|without|hate|don't want|dont want|not into|skip)"

# Words → the UI's "into" tags (lenient: synonyms people actually say)
INTO_WORDS: dict[str, tuple[str, ...]] = {
    "a laugh": ("laugh", "comedy", "funny", "stand up", "standup", "stand-up", "comedian"),
    "chill": ("chill", "quiet", "relaxed", "relax", "calm", "low key", "lowkey", "cosy", "cozy"),
    "food": ("food", "eat", "eating", "hungry", "starving", "dinner", "lunch", "brunch", "pizza",
             "burger", "sushi", "ramen", "curry", "tacos", "noodles", "dessert", "bite"),
    "live music": ("live music", "gig", "gigs", "concert", "band", "jazz", "music"),
    "active": ("active", "bowling", "ping pong", "table tennis", "darts", "climbing", "golf",
               "karaoke", "arcade", "games", "crazy golf", "mini golf"),
    "competitive": ("competitive", "compete", "win", "beat my mates", "tournament"),
    "culture": ("culture", "museum", "gallery", "art", "exhibition", "theatre", "theater", "show"),
    "late night": ("late night", "late one", "out late", "dance", "dancing", "club", "clubbing",
                   "rave", "party", "night out"),
}  # fmt: skip
SPECIFIC_INTERESTS = {
    "pizza": ("pizza", "pizzeria"),
    "comedy": ("comedy", "comedian", "stand up", "standup", "stand-up"),
}
NOT_INTO_WORDS: dict[str, tuple[str, ...]] = {
    "clubs": ("club", "clubs", "clubbing", "nightclub"),
    "loud music": ("loud", "loud music", "noisy"),
    "outdoors": ("outdoors", "outdoor", "outside"),
    "late nights": ("late night", "late nights", "staying out late"),
    "queues": ("queue", "queues", "waiting", "lines"),
    **SPECIFIC_INTERESTS,
}
# Single words we fuzzy-match against, to forgive typos like "pizzza" or "comdey"
VOCAB = sorted({w for words in INTO_WORDS.values() for w in words if " " not in w} | set(CHEAP))


def _amount(t: str) -> int | None:
    """The spending cap mentioned, in pounds, if any ("under £20", "max 15 quid", "a tenner")."""
    cap = (
        r"(?:under|less than|below|max(?:imum)?|up to|no more than|nothing over|not over|"
        r"within|around|about|budget of|for)?"
    )
    pounds = re.search(rf"{cap}\s*£\s*(\d+)|{cap}\s*(\d+)\s*(?:pounds?|quid|gbp|£)", t)
    if pounds:
        return int(pounds.group(1) or pounds.group(2))
    trailing = re.search(r"£\s*(\d+)", t)
    if trailing:
        return int(trailing.group(1))
    for slang, value in MONEY_SLANG.items():
        if re.search(rf"\b(?:a |one )?{slang}\b", t):
            return value
    words = re.search(
        r"(?:under|less than|below|max|up to|nothing over|no more than)\s+"
        r"((?:twenty |thirty |forty |fifty )?(?:one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|fifteen|twenty|thirty|forty|fifty|hundred))\s*(?:pounds?|quid)?",
        t,
    )
    if words:
        parts = words.group(1).split()
        return sum(NUMBER_WORDS.get(p, 0) for p in parts) or None
    bare = re.search(
        r"\b(?:under|less than|below|max|up to|nothing over|no more than)\s+(\d+)\b"
        r"(?!\s*(?:min|mins|minutes?|hours?|hrs?|km|miles?|m\b))",
        t,
    )
    return int(bare.group(1)) if bare else None


def _budget(t: str) -> int | None:
    if any(p in t for p in ANY_PRICE):
        return 999
    amount = _amount(t)
    if amount is not None:
        return 10 if amount <= 10 else 20 if amount <= 20 else 999
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in CHEAP):
        return 10
    return None


def _company(t: str) -> int | None:
    if re.search(r"\b(just me|on my own|by myself|solo|alone)\b", t):
        return 1
    mates = re.search(
        r"\b(?:me and|me \+|with)\s+(\w+)\s+(?:mates|friends|pals|others|people|of my)", t
    )
    if mates:
        n = NUMBER_WORDS.get(mates.group(1)) or (
            int(mates.group(1)) if mates.group(1).isdigit() else None
        )
        if n:
            return n + 1  # count the user too
    group = re.search(
        r"\b(\w+) of us\b|\bgroup of (\w+)\b"
        r"|\bfor (\w+)\b(?! (?:pounds?|quid|minutes?|mins?|hours?))",
        t,
    )
    if group:
        word = next(g for g in group.groups() if g)
        n = NUMBER_WORDS.get(word) or (int(word) if word.isdigit() else None)
        if n and n <= 20:
            return n
    if re.search(
        r"\b(with my (girlfriend|boyfriend|partner|wife|husband|date|mate|friend)"
        r"|date night|me and my)\b",
        t,
    ):
        return 2
    return None


def _fuzzy(t: str) -> str:
    """Correct obvious typos word by word against our vocabulary ("pizzza" → "pizza")."""
    out = []
    for word in re.findall(r"[a-z']+|[^a-z']+", t):
        if word.isalpha() and len(word) >= 4 and word not in VOCAB:
            match = get_close_matches(word, VOCAB, n=1, cutoff=0.84)
            out.append(match[0] if match else word)
        else:
            out.append(word)
    return "".join(out)


def _has(t: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", t) is not None


def _negated(t: str, phrase: str) -> bool:
    return re.search(rf"\b{NEG}\s+(?:\w+\s+){{0,2}}{re.escape(phrase)}", t) is not None


def parse_request(text: str) -> dict[str, Any]:
    """Chips for the web app: include, exclude, and budget/student/company only if said."""
    t = _fuzzy(" ".join(text.lower().replace("\u2019", "'").split()))
    include: list[str] = []
    exclude: list[str] = []

    for tag, words in NOT_INTO_WORDS.items():
        if any(_negated(t, w) for w in words):
            exclude.append(tag)
    if re.search(r"\bit'?s raining\b|\braining\b", t):
        exclude.append("outdoors")

    for tag, words in INTO_WORDS.items():
        hits = [w for w in words if _has(t, w) and not _negated(t, w)]
        # "no clubs" shouldn't count as wanting a late night
        if hits and tag not in include:
            include.append(tag)
    specific = [
        tag
        for tag, terms in SPECIFIC_INTERESTS.items()
        if any(_has(t, term) and not _negated(t, term) for term in terms)
    ]
    if "pizza" in specific and "food" in include:
        include.remove("food")
    if "comedy" in specific:
        include = [tag for tag in include if tag != "a laugh"]
        # "Show" in "comedy show" is already accounted for by the comedy request.
        if "culture" in include and not any(
            _has(t, word) and not _negated(t, word)
            for word in INTO_WORDS["culture"]
            if word != "show"
        ):
            include.remove("culture")
    include.extend(specific)
    if "competitive" in include and "active" not in include:
        include.append("active")
    include = [
        i for i in include if not (i == "late night" and "clubs" in exclude and not _has(t, "late"))
    ]

    chips: dict[str, Any] = {"include": include, "exclude": sorted(set(exclude) - set(include))}
    budget = _budget(t)
    if budget is not None:
        chips["budget"] = budget
    company = _company(t)
    if company is not None:
        chips["company"] = company
    if re.search(r"\b(i'?m a student|im a student|student|uni|university)\b", t):
        chips["student"] = True
    if re.search(r"\bcheaper\b", t) and budget is None:
        chips["cheaper"] = True  # command: one step down; the session applies it
    return chips


def matches_specific_interests(item: dict[str, Any], terms: set[str]) -> bool:
    """Match any requested activity by its specific category, tags or venue/event name."""
    name = item["name"].lower()
    tags = item["tags"]
    return not terms or any(
        term in tags
        or term == item.get("category")
        or any(_has(name, alias) for alias in SPECIFIC_INTERESTS[term])
        for term in terms
    )
