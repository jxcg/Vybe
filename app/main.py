import json
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse

HERE = Path(__file__).parent

app = FastAPI(title="Vybe")


@app.get("/api/items")
def items() -> list[dict[str, Any]]:
    # shortcut: reads the sample file on every request, swap for the refresh pipeline's output
    return cast(list[dict[str, Any]], json.loads((HERE / "items.json").read_text()))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
