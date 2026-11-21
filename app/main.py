import json
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse

HERE = Path(__file__).parent
DB_PATH = os.environ.get("VYBE_DB", "vybe.db")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            settings TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS likes (
            device_id TEXT NOT NULL REFERENCES devices(id),
            item_id TEXT NOT NULL,
            liked INTEGER NOT NULL,
            PRIMARY KEY (device_id, item_id)
        );
        """
    )
    return conn


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db().close()
    yield


app = FastAPI(title="Vybe", lifespan=lifespan)


@app.get("/api/items")
def items() -> list[dict[str, Any]]:
    # shortcut: reads the sample file on every request, swap for the refresh pipeline's output
    return cast(list[dict[str, Any]], json.loads((HERE / "items.json").read_text()))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
