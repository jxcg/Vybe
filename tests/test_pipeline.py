import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import osm
from pipeline import refresh


@pytest.fixture(autouse=True)
def no_google_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)


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


def test_refresh_enriched_sync_writes_empty_object_per_venue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        refresh, "venues_near", lambda lat, lng: [{"id": "a"}, {"id": "b"}, {"id": "a"}]
    )
    target = tmp_path / "enriched.json"
    out = refresh.refresh_enriched_sync(51.5, -0.1, target)
    assert out == {"venues": 2, "ids": ["a", "b"]}
    assert json.loads(target.read_text()) == {"a": {}, "b": {}}


def test_workflow_is_registered() -> None:
    from mistralai.workflows import get_workflow_definition

    assert get_workflow_definition(refresh.VybeRefresh).name == "vybe-refresh"
