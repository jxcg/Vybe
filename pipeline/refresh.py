"""Pipeline v1: fetch venues near a point and write data/enriched.json.

Contract 1 shell (docs/mistral-partner.md): one JSON object keyed by item ID,
with an empty object per venue for now; the Scout/Enricher/Verifier agents and
Voxtral voiceovers get layered on next.

Worker:   uv run --env-file .env python -m pipeline.worker
Trigger:  uv run --env-file .env python -m pipeline.run_once --lat 51.5136 --lng -0.1365

Note: network/file-system imports are deferred into the functions that use them,
because the workflow module itself is imported inside Temporal's sandbox, which
rejects httpx's import chain at validation time.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
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


def refresh_enriched_sync(lat: float, lng: float, path: Path) -> dict[str, Any]:
    """One activity's worth of work, as a plain function so tests can run it offline."""
    items = venues_near(lat, lng)
    enriched: dict[str, Any] = {item["id"]: {} for item in items}
    write_enriched(enriched, path)
    return {"venues": len(enriched), "ids": sorted(enriched)}


@activity(
    name="fetch venues + write enriched.json",
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy_max_attempts=2,
)
async def refresh_enriched(lat: float, lng: float) -> dict[str, Any]:
    return await asyncio.to_thread(refresh_enriched_sync, lat, lng, _enriched_path())


@workflow.define(
    name="vybe-refresh",
    workflow_description="Fetch venues near a point, write data/enriched.json (pipeline v1)",
)
class VybeRefresh:
    @workflow.entrypoint
    async def run(self, lat: float, lng: float) -> dict[str, Any]:
        return await refresh_enriched(lat, lng)
