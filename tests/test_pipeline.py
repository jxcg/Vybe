import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app import osm
from pipeline import agents, refresh


@pytest.fixture(autouse=True)
def no_google_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)


# --- venue sources and atomic write -------------------------------------------------


def test_write_enriched_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "data" / "enriched.json"
    refresh.write_enriched({"a": {}, "b": {}}, target)
    assert json.loads(target.read_text()) == {"a": {}, "b": {}}
    assert list((tmp_path / "data").iterdir()) == [target]  # no temp files left behind


def test_venues_near_uses_osm_without_google_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(osm, "nearby", lambda lat, lng: [{"id": "el1"}, {"id": "el2"}])
    monkeypatch.setattr(
        osm,
        "to_item",
        lambda el, now: {"id": f"osm-x-{el['id']}"} if el["id"] == "el1" else None,
    )
    assert [i["id"] for i in refresh.venues_near(51.5, -0.1)] == ["osm-x-el1"]


def test_venues_near_falls_back_to_samples_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(lat: float, lng: float) -> list[dict[str, Any]]:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(osm, "nearby", boom)
    ids = [i["id"] for i in refresh.venues_near(51.5, -0.1)]
    assert "bowl-1" in ids  # sample data keeps the demo alive


def test_combine_enriched_merges_claims_over_empty_entries() -> None:
    items = [{"id": "a"}, {"id": "b"}]
    claims = {
        "a": {"deal": "2-for-1", "verified": True},
        "ghost": {"verified": True},
        "event-gig": {"new_item": {"id": "event-gig"}, "verified": True},
    }
    out = refresh.combine_enriched(items, claims)
    assert out["a"] == {"deal": "2-for-1", "verified": True}
    assert out["b"] == {}
    assert "ghost" not in out
    assert out["event-gig"]["new_item"]["id"] == "event-gig"


def test_combine_enriched_preserves_existing_theme_across_refreshes() -> None:
    items = [{"id": "a"}]
    claims = {
        "a": {
            "deal": None,
            "student_price": False,
            "price": None,
            "script": None,
            "verified": True,
            "verify_note": "ok",
            "checked_at": "now",
            "source_url": None,
        }
    }
    existing = {
        "a": {"theme": {"mode": "photo"}, "brand_color": "#8b2332", "deal": "old deal"},
        "event-old": {"new_item": {"id": "event-old"}, "verified": True},
    }
    out = refresh.combine_enriched(items, claims, existing)
    assert out["a"]["theme"] == {"mode": "photo"}  # theme survives the refresh
    assert out["a"]["brand_color"] == "#8b2332"
    assert out["a"]["deal"] is None  # claim keys fully replace stale enrichment
    assert out["event-old"]["new_item"]["id"] == "event-old"  # old events survive too


def test_workflow_is_registered() -> None:
    from mistralai.workflows import get_workflow_definition

    assert get_workflow_definition(refresh.VybeRefresh).name == "vybe-refresh"


# --- agents (all network mocked) ----------------------------------------------------


def test_build_orchestrator_has_scout_enricher_verifier() -> None:
    agent = agents.build_orchestrator()
    assert [s.name for s in agent.subagents] == ["scout", "enricher", "verifier"]
    assert agent.output_type is agents.OrchestratorOutput


def test_merge_output_keeps_only_verified_and_shapes_events() -> None:
    out = agents.OrchestratorOutput(
        venues=[
            agents.VenueClaim(
                id="v1",
                deal="2-for-1 bowls",
                student_price=True,
                price=6.5,
                script="Two-for-one bowls, go before nine.",
                verified=True,
                verify_note="Deal confirmed on the venue's own site",
                source_url="https://example.com",
            ),
            agents.VenueClaim(id="v2", deal="fake discount", verified=False),
        ],
        events=[
            agents.NewEvent(
                slug="comedy-night",
                name="Comedy Night",
                price=10.0,
                opens="19:00",
                closes="23:00",
                lat=51.51,
                lng=-0.13,
                tags=["culture", "loud"],
                url="https://example.com",
                script="Late comedy, five minutes away.",
            )
        ],
    )
    merged = agents.merge_output(out, "2026-11-21T18:05:00+00:00")
    assert set(merged) == {"v1", "event-comedy-night"}
    v1 = merged["v1"]
    assert v1["verified"] is True and v1["deal"] == "2-for-1 bowls"
    assert v1["checked_at"] == "2026-11-21T18:05:00+00:00"
    event = merged["event-comedy-night"]
    assert event["verified"] is True
    item = event["new_item"]
    assert item["id"] == "event-comedy-night" and item["type"] == "activity"
    assert item["tags"] == ["culture"]  # unknown tag dropped
    assert item["rating"] is None and item["source"] == "Scout agent"


def test_run_orchestrator_returns_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    output = agents.OrchestratorOutput(
        venues=[agents.VenueClaim(id="v1", verified=True, verify_note="ok")]
    )

    class FakeAgent:
        async def run(self, prompt: str, timeout: float | None = None) -> Any:
            assert "v1" in prompt
            return SimpleNamespace(output=output)

    monkeypatch.setattr(agents, "build_orchestrator", lambda: FakeAgent())
    claims = asyncio.run(agents.run_orchestrator(51.5, -0.1, [{"id": "v1"}], "now"))
    assert claims == {
        "v1": {
            "deal": None,
            "student_price": False,
            "price": None,
            "script": None,
            "verified": True,
            "verify_note": "ok",
            "checked_at": "now",
            "source_url": None,
        }
    }


def test_run_orchestrator_returns_empty_on_bad_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgent:
        async def run(self, prompt: str, timeout: float | None = None) -> Any:
            return SimpleNamespace(output=None)

    monkeypatch.setattr(agents, "build_orchestrator", lambda: FakeAgent())
    assert asyncio.run(agents.run_orchestrator(51.5, -0.1, [], "now")) == {}
