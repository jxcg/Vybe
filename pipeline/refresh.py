"""Pipeline: fetch venues near a point, enrich them with agents, write data/enriched.json.

v2 shape (docs/mistral-partner.md): the `vybe-refresh` workflow runs three activities —
fetch venues → orchestrate (Scout/Enricher/Verifier subagents, pipeline/agents.py) →
write data/enriched.json atomically. Verified claims only; every venue keeps at least
an empty entry so the app always has a valid file.

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

from mistralai.workflows import activity, workflow


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


def combine_enriched(items: list[dict[str, Any]], claims: dict[str, Any]) -> dict[str, Any]:
    """Empty entry per venue plus verified claims; claims for unknown venue ids are dropped."""
    out: dict[str, Any] = {item["id"]: {} for item in items}
    for key, value in claims.items():
        if key.startswith("event-") or key in out:
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
    enriched = await asyncio.to_thread(combine_enriched, items, claims)
    await asyncio.to_thread(write_enriched, enriched, _enriched_path())
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
        return await write_enriched_activity(items, claims)
