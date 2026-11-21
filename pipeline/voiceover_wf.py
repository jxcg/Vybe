"""`vybe-voiceover` workflow: Voxtral TTS mp3 per venue card, written to
data/voiceovers/ and referenced from data/enriched.json (`voiceover` key).

Trigger:  uv run --env-file .env python -m pipeline.run_once --workflow vybe-voiceover

Sandbox note: top level stays sandbox-safe; heavy imports happen in activity bodies.
"""

import asyncio
from datetime import timedelta
from typing import Any

from mistralai.workflows import activity, workflow

from pipeline.refresh import fetch_venues


@activity(
    name="generate voiceovers (Voxtral TTS)",
    start_to_close_timeout=timedelta(minutes=6),
    retry_policy_max_attempts=1,
)
async def voiceover_all(items: list[dict[str, Any]]) -> dict[str, str]:
    from pipeline.refresh import _enriched_path, read_enriched  # deferred
    from pipeline.voiceover import make_voiceovers  # deferred

    enriched = await asyncio.to_thread(read_enriched, _enriched_path())
    return await make_voiceovers(items, enriched)


@activity(
    name="write voiceover paths into enriched.json",
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy_max_attempts=2,
)
async def write_voiceovers(mapping: dict[str, str]) -> dict[str, Any]:
    from pipeline.refresh import _enriched_path, read_enriched, write_enriched  # deferred
    from pipeline.voiceover import merge_voiceovers  # deferred

    path = _enriched_path()
    existing = await asyncio.to_thread(read_enriched, path)
    enriched = await asyncio.to_thread(merge_voiceovers, existing, mapping)
    await asyncio.to_thread(write_enriched, enriched, path)
    return {"voiceovers": len(mapping)}


@workflow.define(
    name="vybe-voiceover",
    workflow_description="Voxtral TTS voiceover per venue near a point (background only)",
)
class VybeVoiceover:
    @workflow.entrypoint
    async def run(self, lat: float, lng: float) -> dict[str, Any]:
        items = await fetch_venues(lat, lng)
        mapping = await voiceover_all(items)
        return await write_voiceovers(mapping)
