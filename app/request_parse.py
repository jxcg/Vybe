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
# Activity phrasing and evidence from the catalogue. These describe venue capabilities,
# so a nightclub can match dancing without treating every venue named "Club" as a nightclub.
ACTIVITY_TERMS = {
    "dancing": ("dance", "dancing"),
    "comedy": ("comedy", "laugh", "stand up", "standup"),
    "food": ("food", "dinner", "lunch", "brunch"),
    "karaoke": ("sing", "singing", "karaoke"),
    "film": ("film", "films", "movie", "movies", "cinema"),
    "climbing": ("climb", "climbing"),
    "music": ("music", "live music", "gig", "gigs"),
}
ACTIVITY_NAMES = {
    phrase: activity for activity, phrases in ACTIVITY_TERMS.items() for phrase in phrases
}
ACTIVITY_EVIDENCE = {"dancing": {"club", "night club", "nightclub"}}

CLAUSES = re.compile(r"[,;.!?]+|\b(?:and|or|but|then|followed by)\b")
LEAD_IN = re.compile(
    r"^(?:i (?:really )?(?:would (?:like|love)|want|fancy|feel like|am looking for)|"
    r"i'd (?:like|love)|can we|let's|looking for|want|fancy|find|"
    r"to|go(?: get| for| to| out)?|get|eat(?:ing)?|have|see|hear|watch|"
    r"some|a|an|the|something like|something|maybe|please)\b\s*"
)
CONTEXT = re.compile(
    r"\b(?:under|within|less than|nothing over|max(?:imum)?|up to|"
    r"near(?:by| me)?|tonight|today|afterwards|please|with|for)\b"
)

NOT_INTO_WORDS: dict[str, tuple[str, ...]] = {
    "clubs": ("club", "clubs", "clubbing", "nightclub"),
    "loud music": ("loud", "loud music", "noisy"),
    "outdoors": ("outdoors", "outdoor", "outside"),
    "late nights": ("late night", "late nights", "staying out late"),
    "queues": ("queue", "queues", "waiting", "lines"),
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
    named, negative = named_requests(t)
    if named:
        inferred = set(include)
        # Keep independent broad requests, but drop categories inferred from a concrete phrase.
        include = [
            tag for tag in include if _has(t, tag) or (tag == "a laugh" and _has(t, "funny"))
        ]
        if "late night" in inferred and "late night" not in include:
            include.append("late night")
        if "live music" in inferred and "live music" not in include:
            include.append("live music")
        if "active" in inferred and "active" not in include:
            include.append("active")
    include = list(dict.fromkeys([*include, *named]))
    exclude.extend(negative)
    if "competitive" in include and "active" not in include:
        include.append("active")
    include = [
        i for i in include if not (i == "late night" and "clubs" in exclude and not _has(t, "late"))
    ]

    chips: dict[str, Any] = {"include": include, "exclude": sorted(set(exclude) - set(include))}
    budget = _budget(t)
    if named:
        chips["requested"] = list(dict.fromkeys(named))
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


def normalise_interest(value: str) -> str:
    term = " ".join(re.findall(r"[^\W_]+", value.casefold()))
    return ACTIVITY_NAMES.get(term, term)


def _strip_lead_in(clause: str) -> str:
    while (clean := LEAD_IN.sub("", clause)) != clause:
        clause = clean
    return clause


def named_requests(text: str) -> tuple[list[str], list[str]]:
    """Keep a concrete noun phrase from each request clause, even if it is new to Vybe."""
    include: list[str] = []
    exclude: list[str] = []
    mood_words = {
        word for tag in ("chill", "competitive", "late night") for word in INTO_WORDS[tag]
    }
    broad_words = {
        *(mood_words - ACTIVITY_NAMES.keys()),
        *INTO_WORDS,
        *CHEAP,
        *MONEY_SLANG,
        "eat",
        "eating",
        "hungry",
        "hungry af",
        "starving",
        "dinner",
        "lunch",
        "brunch",
        "bite",
        "laugh",
        "funny",
        "show",
        "stuff",
        "stuff only",
        "somewhere",
        "anything",
        "whatever",
        "cheaper",
        "just me",
        "date night",
        "me",
        "me too",
    }
    context_words = ("student", "tonight", "raining", "want", "mates", "loud", "object", "skint")
    for clause in CLAUSES.split(text):
        clause = _strip_lead_in(clause.strip())
        negation = re.match(rf"^(?:i )?{NEG}\b\s*", clause)
        if negation:
            clause = _strip_lead_in(clause[negation.end() :])
        clause = CONTEXT.split(clause, maxsplit=1)[0].strip()
        for qualifier in CHEAP:
            if clause.startswith(qualifier + " "):
                clause = _strip_lead_in(clause[len(qualifier) :].strip())
                break
        if _company(clause) is not None or _budget(clause) is not None:
            continue
        clause = re.sub(r"\s+(?:show|maybe|only)$", "", clause)
        if (
            not clause
            or not re.fullmatch(r"[a-z][a-z &'\-]*(?:[a-z])?", clause)
            or len(clause.split()) > 5
            or (clause in broad_words and clause not in ACTIVITY_NAMES)
            or any(_has(clause, word) for word in context_words)
            or any(clause in words for words in NOT_INTO_WORDS.values())
        ):
            continue
        term = normalise_interest(clause)
        (exclude if negation else include).append(term)
    return include, exclude


def specific_interests(terms: list[str]) -> set[str]:
    return {term for value in terms if (term := normalise_interest(value))}


def matches_interest(item: dict[str, Any], term: str) -> bool:
    """Match a phrase against venue names and specific source metadata."""
    metadata = [*item["tags"], *item.get("interest_terms", [])]
    capability = ACTIVITY_EVIDENCE.get(term, set())
    if capability and any(normalise_interest(value) in capability for value in metadata):
        return True
    evidence = [item["name"], *metadata]
    if item.get("category") not in (None, "music", "games", "food", "other"):
        evidence.append(item["category"])
    for value in evidence:
        normalised = normalise_interest(value)
        if any(
            _has(normalised, phrase) or re.search(rf"\b{re.escape(phrase)}(?:s|es)\b", normalised)
            for phrase in (term, *ACTIVITY_TERMS.get(term, ()))
        ):
            return True
    return False


def matches_specific_interests(item: dict[str, Any], terms: set[str]) -> bool:
    return not terms or any(matches_interest(item, term) for term in terms)
