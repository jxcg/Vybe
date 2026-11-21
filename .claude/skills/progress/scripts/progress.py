"""Print progress bars from a markdown checklist (docs/roadmap.md by default).

Milestones are `## ` headings; tasks are `- [ ]` / `- [x]` lines under them.
The milestone marked `(now)` is the current one; otherwise the first unfinished one.
"""

import re
import sys
from pathlib import Path

WIDTH = 20


def bar(done: int, total: int) -> str:
    pct = round(100 * done / total) if total else 0
    filled = round(WIDTH * done / total) if total else 0
    return f"{'█' * filled}{'░' * (WIDTH - filled)} {pct:3d}%  ({done}/{total})"


def main(path: str) -> None:
    milestones: list[dict[str, object]] = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            now = "(now)" in title
            milestones.append({"title": title.replace("(now)", "").strip(), "now": now, "tasks": []})
        elif (m := re.match(r"\s*- \[( |x|X)\] (.+)", line)) and milestones:
            tasks = milestones[-1]["tasks"]
            assert isinstance(tasks, list)
            tasks.append((m.group(1).lower() == "x", m.group(2).strip()))

    def tasks_of(ms: dict[str, object]) -> list[tuple[bool, str]]:
        t = ms["tasks"]
        assert isinstance(t, list)
        return t

    all_tasks = [t for ms in milestones for t in tasks_of(ms)]
    done = sum(d for d, _ in all_tasks)
    current = next((ms for ms in milestones if ms["now"]), None) or next(
        (ms for ms in milestones if not all(d for d, _ in tasks_of(ms))), None
    )

    print(f"OVERALL    {bar(done, len(all_tasks))}")
    if current:
        ct = tasks_of(current)
        print(f"NOW        {bar(sum(d for d, _ in ct), len(ct))}  {current['title']}")
    print()
    for ms in milestones:
        mt = tasks_of(ms)
        mark = "▶" if ms is current else ("✓" if all(d for d, _ in mt) else " ")
        print(f"{mark} {str(ms['title'])[:22]:<22} {bar(sum(d for d, _ in mt), len(mt))}")
    if current:
        print(f"\nIn '{current['title']}':")
        for d, text in tasks_of(current):
            print(f"  {'[x]' if d else '[ ]'} {text}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/roadmap.md")
