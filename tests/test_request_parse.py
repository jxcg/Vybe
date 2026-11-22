"""Typed and spoken requests → chips. Follows INTEGRATION.md §5; regression cases from real bugs."""

from typing import Any

import pytest

from app.request_parse import parse_request

CASES = [
    # The bug: "under £20" became £10
    (
        "I want to go eat some pizza under £20 and go dance afterwards",
        {"budget": 20, "include": ["pizza", "late night"]},
    ),
    ("under 20", {"budget": 20}),
    ("nothing over 15 quid", {"budget": 20}),
    ("less than twenty pounds please", {"budget": 20}),
    ("something under a tenner", {"budget": 10}),
    ("under £10", {"budget": 10}),
    ("£25 max", {"budget": 999}),
    ("about 30 pounds each", {"budget": 999}),
    ("money's no object", {"budget": 999}),
    ("somewhere cheap", {"budget": 10}),
    ("I'm skint", {"budget": 10}),
    ("free stuff only", {"budget": 10}),
    ("a fiver", {"budget": 10}),
    # Group size and student
    (
        "me and two mates want a laugh, nothing over a tenner",
        {"budget": 10, "company": 3, "include": ["a laugh"]},
    ),
    ("dinner for two under 40 quid", {"budget": 999, "company": 2, "include": ["food"]}),
    ("three of us, something active", {"company": 3, "include": ["active"]}),
    ("just me tonight", {"company": 1}),
    ("date night with my girlfriend", {"company": 2}),
    ("I'm a student, something chill", {"student": True, "include": ["chill"]}),
    # Numbers that aren't money or people
    ("within 10 minutes walk", {"no": ["budget"]}),
    ("under 5 minutes away", {"no": ["budget"]}),
    ("something for 2 hours", {"no": ["company", "budget"]}),
    # Negation
    ("bowling, no clubs", {"include": ["active"], "exclude": ["clubs"]}),
    ("nothing outdoors, it's raining", {"exclude": ["outdoors"]}),
    ("not too loud please", {"exclude": ["loud music"]}),
    ("I don't want food", {"no_include": ["food"]}),
    # Lenient: typos and slang
    ("pizzza and a gig", {"include": ["pizza", "live music"]}),
    ("somthing funny, comdey maybe", {"include": ["a laugh"]}),
    ("hungry af", {"include": ["food"]}),
    ("UNDER £20!!!", {"budget": 20}),
    ("", {}),
    # Everyday phrasing must not become a junk concrete search that empties the board
    ("just somewhere to eat", {"include": ["food"], "no": ["requested"]}),
    ("a quiet pint", {"include": ["chill", "late night"], "no": ["requested"]}),
    ("quiz night at the pub", {"no": ["requested"]}),
    (
        "no clubs, just somewhere to eat",
        {"include": ["food"], "exclude": ["clubs"], "no": ["requested"]},
    ),
    # A known activity phrase wins over the words around it
    ("karaoke night with the lads", {"requested": ["karaoke"]}),
    ("stand-up comedy", {"requested": ["comedy"], "include": ["comedy"]}),
    ("chill museum or gallery", {"requested": ["culture"], "include": ["chill", "culture"]}),
    ("I want to dance tonight", {"requested": ["dancing"], "include": ["late night"]}),
    ("i fancy a curry tonight", {"requested": ["curry"]}),
    # Negation: drink words exclude late nights; "or" carries the negation; "just" is a lead-in
    ("no bars", {"exclude": ["late nights"], "no_include": ["late night"]}),
    ("no pub, somewhere for curry", {"exclude": ["late nights"]}),
    ("just pizza", {"requested": ["pizza"]}),
    ("no museum or gallery", {"exclude": ["culture"], "no_include": ["culture"]}),
    ("avoid loud music or queues", {"exclude": ["loud music", "queues"]}),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_parse_request(text: str, expected: dict[str, Any]) -> None:
    got = parse_request(text)
    for key, value in expected.items():
        if key == "no":
            for k in value:
                assert k not in got, f"{text!r}: unexpected {k}={got.get(k)}"
        elif key == "no_include":
            assert not set(value) & set(got["include"]), f"{text!r}: {got['include']}"
        elif key in ("include", "exclude"):
            assert set(value) <= set(got[key]), f"{text!r}: {key}={got[key]}"
        else:
            assert got.get(key) == value, f"{text!r}: {key}={got.get(key)}"


def test_broad_food_and_comedy_request() -> None:
    assert parse_request("I want to have a laugh and eat food") == {
        "include": ["a laugh", "food", "comedy"],
        "exclude": [],
        "requested": ["comedy", "food"],
    }


def test_only_what_was_said() -> None:
    assert parse_request("bowling") == {
        "include": ["active", "bowling"],
        "requested": ["bowling"],
        "exclude": [],
    }
    assert parse_request("Pizza and a comedy show") == {
        "include": ["pizza", "comedy"],
        "requested": ["pizza", "comedy"],
        "exclude": [],
    }


def test_cheaper_is_relative() -> None:
    assert parse_request("cheaper please").get("cheaper") is True
    assert "cheaper" not in parse_request("cheaper, under £20")  # an explicit amount wins


@pytest.mark.parametrize(
    ("text", "terms"),
    [
        ("I fancy ice cream", {"ice cream"}),
        ("I would love some cheap ice cream for two", {"ice cream"}),
        ("pizza and music", {"pizza", "music"}),
        ("sushi and karaoke", {"sushi", "karaoke"}),
        ("I want a pottery class", {"pottery class"}),
        ("ice cream but no pizza", {"ice cream"}),
    ],
)
def test_named_requests_keep_the_requested_things(text: str, terms: set[str]) -> None:
    assert terms <= set(parse_request(text)["include"])


def test_group_phrase_does_not_swallow_the_request() -> None:
    assert parse_request("me and two mates want pizza under £20") == {
        "include": ["pizza"],
        "exclude": [],
        "requested": ["pizza"],
        "budget": 20,
        "company": 3,
    }
