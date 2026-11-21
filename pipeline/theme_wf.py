"""Card-theme workflows: `vybe-theme` (parent) spawns a `vybe-theme-item` child per venue.

The feed never waits for these: themes are merged into data/enriched.json under
each venue id (Contract 1) and cards without a theme yet use the default gradient.

Run the worker (same as vybe-refresh) and trigger with:
    uv run --env-file .env python -m pipeline.run_once --workflow vybe-theme

Sandbox note: this module's top level stays sandbox-safe (stdlib + pydantic +
mistralai.workflows only); heavy imports happen inside the activity bodies.
"""

import asyncio
import json
from datetime import timedelta
from typing import Any

from mistralai.workflows import activity, execute_workflow, workflow
from pydantic import BaseModel

from pipeline.refresh import fetch_venues

MAX_VENUES = 25  # bound agent cost: <= 2 candidates x (pro+con) + 1 judge per venue


class ThemeItemParams(BaseModel):
    item: dict[str, Any]


@activity(
    name="theme one venue",
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy_max_attempts=1,
)
async def theme_one(item: dict[str, Any]) -> dict[str, Any]:
    from pipeline.theme import theme_item  # deferred: not sandbox-safe at module level

    return await theme_item(item)


@activity(
    name="write themes into enriched.json",
    start_to_close_timeout=timedelta(minutes=1),
    retry_policy_max_attempts=2,
)
async def write_themes(results: list[dict[str, Any]]) -> dict[str, Any]:
    from pipeline.refresh import _enriched_path, write_enriched  # deferred

    path = _enriched_path()
    try:
        enriched: dict[str, Any] = json.loads(path.read_text())
        if not isinstance(enriched, dict):
            enriched = {}
    except (OSError, ValueError):
        enriched = {}
    for r in results:
        rid = r.get("id") if isinstance(r, dict) else None
        if rid:
            enriched.setdefault(rid, {})["theme"] = r.get("theme")
    write_enriched(enriched, path)
    return {"themed": len(results)}


@workflow.define(
    name="vybe-theme-item",
    workflow_description="Theme one venue card: image debate (Pro/Con/Judge) + palette + contrast",
)
class VybeThemeItem:
    @workflow.entrypoint
    async def run(self, item: dict[str, Any]) -> dict[str, Any]:
        return await theme_one(item)


@workflow.define(
    name="vybe-theme",
    workflow_description="Theme every venue near a point (child workflow vybe-theme-item each)",
)
class VybeTheme:
    @workflow.entrypoint
    async def run(self, lat: float, lng: float) -> dict[str, Any]:
        items = (await fetch_venues(lat, lng))[:MAX_VENUES]
        results = await asyncio.gather(
            *[execute_workflow(VybeThemeItem, params=ThemeItemParams(item=i)) for i in items]
        )
        return await write_themes(list(results))
