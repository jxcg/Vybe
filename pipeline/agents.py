"""Pipeline v2 agents: an orchestrator with Scout / Enricher / Verifier subagents.

Imported only from activities and tests — never from the workflow module, whose
imports are validated inside Temporal's sandbox.

The orchestrator researches live venues (deals, student prices, entry prices,
voiceover scripts) and tonight's events, and only verified claims are returned,
ready to merge into data/enriched.json (Contract 1 in docs/mistral-partner.md).
"""

import json
import os
from typing import Any

from mistralai import agents
from mistralai.client import Mistral
from mistralai.client import models as api_models
from pydantic import BaseModel, Field

ORCHESTRATOR_MODEL = "mistral-large-4"
SUBAGENT_MODEL = "mistral-medium-latest"
SEARCH_MODEL = "mistral-small-latest"  # model behind the hosted web_search tool (fast/cheap)
ORCHESTRATOR_TIMEOUT_S = 240.0
MAX_VENUES = 10  # bound the Enricher's work per refresh

ALLOWED_TAGS = ["active", "culture", "nightlife", "food", "indoors", "outdoors"]

_client: Mistral | None = None


def _mistral() -> Mistral:
    global _client
    if _client is None:
        _client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
    return _client


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.text for c in content if isinstance(c, api_models.TextChunk))


@agents.tool
async def web_search(query: str) -> str:
    """Search the web for current facts: events tonight, deals, student prices, opening hours."""
    try:
        response = await _mistral().beta.conversations.start_async(
            model=SEARCH_MODEL,
            inputs=query,
            tools=[api_models.WebSearchToolTypedDict(type="web_search")],
            store=False,
        )
        replies = [e for e in response.outputs if isinstance(e, api_models.MessageOutputEntry)]
        return _text_of(replies[-1].content) if replies else ""
    except Exception as e:  # e.g. 429 rate limit: tell the model, don't kill the turn
        return f"web search unavailable right now: {e}"


class VenueClaim(BaseModel):
    """One venue's enriched entry; `verified` is set by the Verifier."""

    id: str
    deal: str | None = None
    student_price: bool = False
    price: float | None = None
    script: str | None = Field(default=None, description="Under 15 words, upbeat, says why now")
    verified: bool
    verify_note: str | None = None
    source_url: str | None = None


class NewEvent(BaseModel):
    """A new thing the Scout found; becomes an `event-<slug>` entry with a full new_item."""

    slug: str
    name: str
    price: float | None = None
    price_level: int = 2
    student_price: bool = False
    adult_only: bool = False
    opens: str = Field(description="HH:MM")
    closes: str = Field(description="HH:MM; earlier than opens means after midnight")
    lat: float
    lng: float
    tags: list[str] = Field(default_factory=list)
    url: str | None = None
    script: str | None = None


class OrchestratorOutput(BaseModel):
    venues: list[VenueClaim] = Field(default_factory=list)
    events: list[NewEvent] = Field(default_factory=list)


ORCHESTRATOR_INSTRUCTIONS = (
    "You enrich Vybe's board of things to do near a point, right now. "
    "You have three subagents: spawn them (in parallel where possible) and combine their reports.\n"
    "- scout: finds tonight's events and one-off deals near the point (web search).\n"
    "- enricher: for each venue, researches the current deal, student price and entry price, "
    "and writes a short voiceover script (under 15 words, upbeat, says why now).\n"
    "- verifier: checks every claim against a source (venue site or reputable listing); "
    "a claim is verified=true only when confirmed, with verify_note and source_url.\n"
    "Rules: venue ids must come from the given list; only verified claims belong in `venues` "
    "(the verifier drops the rest); events get slug, opens/closes as HH:MM, tags from "
    f"{ALLOWED_TAGS}, and approximate lat/lng near the point. Answer only with the output schema."
)

SCOUT_INSTRUCTIONS = (
    "Find tonight's events and one-off deals near the given lat/lng using web_search: concerts, "
    "comedy, pop-ups, late openings, happy hours. For each, return slug (kebab-case), name, "
    "opens/closes (HH:MM), price if known, lat/lng near the point, tags from "
    f"{ALLOWED_TAGS}, url of the source, and a one-line script saying why go now. "
    "Only things actually happening tonight; verify each has a real source."
)

ENRICHER_INSTRUCTIONS = (
    "For each venue in the list, use web_search on the venue's own site and reputable listings to "
    "find: a current deal (e.g. 2-for-1, happy hour), whether student prices exist, and the entry "
    "price in GBP if shown. Write a voiceover script under 15 words, upbeat, saying why now "
    "(deal, time left, distance). Return one claim per venue id with what you found; leave fields "
    "null when not found. Do not set verified — the verifier does that."
)

VERIFIER_INSTRUCTIONS = (
    "Check every claim (deals, student prices, prices, events) with web_search against the "
    "venue's own site or a reputable source. Set verified=true only when confirmed, with a short "
    "verify_note (e.g. 'Deal confirmed on the venue's own site') and source_url. Drop unverified "
    "claims entirely — fake discounts, wrong prices and ended events must not reach the board."
)


def build_orchestrator() -> agents.Agent:
    return agents.Agent(
        model=ORCHESTRATOR_MODEL,
        name="vybe-orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        max_iterations=6,
        subagents=[
            agents.Subagent(
                name="scout",
                description="Finds tonight's events and deals near the point (web search).",
                instructions=SCOUT_INSTRUCTIONS,
                model=SUBAGENT_MODEL,
                max_iterations=4,
                tools=[web_search],
            ),
            agents.Subagent(
                name="enricher",
                description="Per venue: deal, student price, entry price, voiceover script.",
                instructions=ENRICHER_INSTRUCTIONS,
                model=SUBAGENT_MODEL,
                max_iterations=4,
                tools=[web_search],
            ),
            agents.Subagent(
                name="verifier",
                description="Confirms each claim against sources; drops anything unconfirmed.",
                instructions=VERIFIER_INSTRUCTIONS,
                model=SUBAGENT_MODEL,
                max_iterations=4,
                tools=[web_search],
            ),
        ],
        output_type=OrchestratorOutput,
    )


def merge_output(out: OrchestratorOutput, now_iso: str) -> dict[str, Any]:
    """Orchestrator output → Contract 1 mapping; only verified entries are kept."""
    enriched: dict[str, Any] = {}
    for v in out.venues:
        if not v.verified:
            continue
        enriched[v.id] = {
            "deal": v.deal,
            "student_price": v.student_price,
            "price": v.price,
            "script": v.script,
            "verified": True,
            "verify_note": v.verify_note,
            "checked_at": now_iso,
            "source_url": v.source_url,
        }
    for e in out.events:
        tags = [t for t in e.tags if t in ALLOWED_TAGS] or ["indoors"]
        enriched[f"event-{e.slug}"] = {
            "new_item": {
                "id": f"event-{e.slug}",
                "name": e.name,
                "type": "activity",
                "price": e.price,
                "price_level": e.price_level,
                "student_price": e.student_price,
                "adult_only": e.adult_only,
                "rating": None,
                "opens": e.opens,
                "closes": e.closes,
                "lat": e.lat,
                "lng": e.lng,
                "tags": tags,
                "url": e.url,
                "maps_url": None,
                "source": "Scout agent",
            },
            "script": e.script,
            "verified": True,
            "checked_at": now_iso,
        }
    return enriched


async def run_orchestrator(
    lat: float, lng: float, items: list[dict[str, Any]], now_iso: str
) -> dict[str, Any]:
    """Run the orchestrator over the venues; returns the Contract 1 claims mapping.

    Never raises for a bad/missing agent answer: returns {} so the refresh still
    writes a valid file (the caller merges it over empty per-venue entries).
    """
    prompt = json.dumps(
        {
            "lat": lat,
            "lng": lng,
            "now": now_iso,
            "venues": [
                {
                    k: i.get(k)
                    for k in (
                        "id",
                        "name",
                        "type",
                        "price",
                        "price_level",
                        "opens",
                        "closes",
                        "tags",
                        "url",
                        "lat",
                        "lng",
                    )
                }
                for i in items
            ],
        },
        ensure_ascii=False,
    )
    state = await build_orchestrator().run(prompt, timeout=ORCHESTRATOR_TIMEOUT_S)
    output = getattr(state, "output", None)
    if isinstance(output, OrchestratorOutput):
        return merge_output(output, now_iso)
    return {}
