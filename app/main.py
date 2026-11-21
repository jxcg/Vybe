import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

from app.ranking import rank

HERE = Path(__file__).parent

app = FastAPI(title="Vybe")


def load_items() -> list[dict[str, Any]]:
    # shortcut: reads the sample file on every request, swap for the refresh pipeline's output
    return cast(list[dict[str, Any]], json.loads((HERE / "items.json").read_text()))


@app.get("/api/items")
def items() -> list[dict[str, Any]]:
    return load_items()


@app.get("/api/feed")
def feed(
    budget: Annotated[int, Query(ge=1, le=3)] = 3,
    student: bool = False,
    adult: bool = True,
    liked: str = "",
    now: Annotated[str | None, Query(pattern=r"^\d{2}:\d{2}$")] = None,
) -> list[dict[str, Any]]:
    """`liked` is comma-separated item ids from the browser; `now` (HH:MM) is for time travel."""
    at = datetime.now()
    if now:
        h, m = map(int, now.split(":"))
        at = at.replace(hour=h, minute=m, second=0, microsecond=0)
    return rank(
        load_items(),
        at,
        budget=budget,
        student=student,
        adult=adult,
        liked=frozenset(filter(None, liked.split(","))),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
