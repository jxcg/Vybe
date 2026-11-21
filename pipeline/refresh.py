"""Pipeline: fetch venues near a point, enrich them with agents, write data/enriched.json.

The refresh fetches venues, runs the Scout, Enricher and Verifier, writes verified
claims to data/enriched.json, and starts the venue theme and voiceover workflows.

Worker:   DEPLOYMENT_NAME=vybe-hackathon uv run --env-file .env python -m pipeline.worker
Trigger:  uv run --env-file .env python -m pipeline.run_once --lat 51.5136 --lng -0.1365

Note: network/fs/agent imports are deferred into the functions that use them, because
the workflow module itself is imported inside Temporal's sandbox, which rejects
httpx/pathlib.resolve/mistralai.agents import chains at validation time.
"""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mistralai.workflows import activity, execute_workflow, workflow

from pipeline.theme_wf import ThemeAreaParams, VybeTheme
from pipeline.voiceover_wf import VoiceoverAreaParams, VybeVoiceover


def _root() -> Path:
    # computed lazily: module-level Path.resolve() is rejected by Temporal's sandbox
    return Path(__file__).resolve().parent.parent


def _enriched_path() -> Path:
    return _root() / "data" / "enriched.json"


def venues_near(lat: float, lng: float) -> list[dict[str, Any]]:
    """Live venues via the app's own sources: Google Places, else OSM, else samples."""
    import httpx

    from app import osm, places

    now = datetime.now()
    try:
        if places.api_key():
            found = places.nearby(lat, lng)
            return [i for p in found if (i := places.to_item(p, now))]
        return [i for e in osm.nearby(lat, lng) if (i := osm.to_item(e, now))]
    except httpx.HTTPError:
        samples: list[dict[str, Any]] = json.loads((_root() / "app" / "items.json").read_text())
        return samples


def write_enriched(enriched: dict[str, Any], path: Path) -> None:
    """Atomic write: temp file then rename, so the app never reads half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".enriched-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(enriched, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def read_enriched(path: Path) -> dict[str, Any]:
    """Current enriched.json as a dict ({} when missing or broken)."""
    try:
        data: Any = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def combine_enriched(
    items: list[dict[str, Any]],
    claims: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verified claims over the venues, preserving existing extras (theme, brand_color).

    Claims for unknown venue ids are dropped; event-<slug> entries pass through.
    """
    existing = existing or {}
    out: dict[str, Any] = {}
    for item in items:
        iid = item["id"]
        entry = dict(existing.get(iid, {}))
        if iid in claims:
            entry.update(claims[iid])  # claims carry every enrichment key, so nothing stale stays
        elif iid not in existing:
            entry = {}
        out[iid] = entry
    for key, value in {**existing, **claims}.items():
        if key.startswith("event-"):
            out[key] = value
    return out


@activity(
    name="fetch venues",
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy_max_attempts=2,
)
async def fetch_venues(lat: float, lng: float) -> list[dict[str, Any]]:
    return await asyncio.to_thread(venues_near, lat, lng)


@activity(
    name="orchestrate scout/enricher/verifier",
    start_to_close_timeout=timedelta(minutes=8),
    retry_policy_max_attempts=1,
)
async def orchestrate(lat: float, lng: float, items: list[dict[str, Any]]) -> dict[str, Any]:
    from pipeline.agents import run_orchestrator  # deferred: not sandbox-safe at module level

    now_iso = datetime.now(UTC).isoformat()
    try:
        return await run_orchestrator(lat, lng, items, now_iso)
    except Exception:
        return {}  # never fail the refresh: fall back to empty enrichments


@activity(
    name="write enriched.json",
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy_max_attempts=2,
)
async def write_enriched_activity(
    items: list[dict[str, Any]], claims: dict[str, Any]
) -> dict[str, Any]:
    from pipeline.refresh import read_enriched  # same module; explicit for clarity

    path = _enriched_path()
    existing = await asyncio.to_thread(read_enriched, path)
    enriched = await asyncio.to_thread(combine_enriched, items, claims, existing)
    await asyncio.to_thread(write_enriched, enriched, path)
    return {"venues": len(items), "claims": len(claims), "ids": sorted(enriched)}


@workflow.define(
    name="vybe-refresh",
    workflow_description="Fetch venues near a point, enrich via agents, write data/enriched.json",
)
class VybeRefresh:
    @workflow.entrypoint
    async def run(self, lat: float, lng: float) -> dict[str, Any]:
        items = await fetch_venues(lat, lng)
        claims = await orchestrate(lat, lng, items)
        summary = await write_enriched_activity(items, claims)
        theme = await execute_workflow(VybeTheme, params=ThemeAreaParams(lat=lat, lng=lng))
        await execute_workflow(
            VybeVoiceover, params=VoiceoverAreaParams(lat=lat, lng=lng), wait=False
        )
        return {**summary, **theme}
