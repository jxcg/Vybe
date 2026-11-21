"""Card themes: per-venue photo/gradient themes, decided in the background.

Main rule from the plan: code handles anything measurable (image size, palette
clustering, WCAG contrast); Mistral agents only decide "does this look good?".
The result is a `theme` dict merged into data/enriched.json under the venue id
(Contract 1) — the feed never waits for it; cards without a theme use the
default Vybe gradient.
"""

import asyncio
import re
from typing import Any

import httpx
from mistralai import agents
from pydantic import BaseModel, Field

VISION_MODEL = "mistral-large-4"  # pro/con look at the image
JUDGE_MODEL = "mistral-medium-latest"  # judge reads the arguments
MAX_CANDIDATES = 2  # keeps agent cost down: 2 candidates x (pro+con) + 1 judge
MIN_WIDTH = 1080  # reject smaller images
MAX_DOWNLOAD = 8 * 1024 * 1024
DEFAULT_PALETTE = ["#7c3aed", "#db2777", "#f59e0b", "#111827"]  # Vybe fallback


# --- measurable: image dimensions from raw bytes (no PIL needed) -------------------


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from PNG / JPEG / GIF / WebP headers, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) > 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) > 30:
        chunk = data[12:16]
        if chunk == b"VP8 " and len(data) > 30:
            return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(
                data[28:30], "little"
            ) & 0x3FFF
        if chunk in (b"VP8L", b"VP8X") and len(data) > 30:
            b = data[21:26]
            w = 1 + (b[0] | (b[1] & 0x3F) << 8)
            h = 1 + ((b[1] >> 6) | b[2] << 2 | (b[3] & 0xF) << 10)
            return w, h
    if data[:2] == b"\xff\xd8":  # JPEG: scan for a SOF marker
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            ):
                return int.from_bytes(data[i + 7 : i + 9], "big"), int.from_bytes(
                    data[i + 5 : i + 7], "big"
                )
            i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


# --- measurable: candidates, pre-filter, palette, contrast ---------------------------


class ImageCandidate(BaseModel):
    url: str
    source: str = "og:image"  # og:image | twitter:image | logo | places
    alt: str = ""
    width: int = 0
    height: int = 0


_LOGOISH = re.compile(r"logo|icon|favicon|screenshot|sprite|badge", re.I)


def collect_from_html(html: str, base_url: str) -> list[ImageCandidate]:
    """Sharing image + logo candidates from a website's HTML (og:image etc.)."""
    out: list[ImageCandidate] = []
    for prop, source in (("og:image", "og:image"), ("twitter:image", "twitter:image")):
        m = re.search(
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
            html,
            re.I,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
                html,
                re.I,
            )
        if m:
            out.append(ImageCandidate(url=m.group(1), source=source))
    m = re.search(
        r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]+href=["\']([^"\']+)', html, re.I
    ) or re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'][^"\']*icon', html, re.I)
    if m:
        out.append(ImageCandidate(url=m.group(1), source="logo"))
    seen, uniq = set(), []
    for c in out:
        if c.url not in seen and c.url.startswith(("http://", "https://")):
            seen.add(c.url)
            uniq.append(c)
    return uniq[:4]


def prefilter(cands: list[ImageCandidate]) -> list[ImageCandidate]:
    """Code-only gate: size, logo/screenshot rejection, portrait-croppable. Best 2 kept."""
    ok = []
    for c in cands:
        if c.width < MIN_WIDTH or c.height <= 0:
            continue
        if _LOGOISH.search(c.url) or _LOGOISH.search(c.alt):
            continue
        aspect = c.width / c.height
        if (
            not 0.45 <= aspect <= 2.2
        ):  # can crop to a 9:16-ish portrait card without losing the subject
            continue
        ok.append(c)
    return sorted(ok, key=lambda c: -c.width)[:MAX_CANDIDATES]


_HEX = re.compile(r"#([0-9a-fA-F]{6})\b|#([0-9a-fA-F]{3})\b")
_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def _norm_hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def css_colors(*texts: str) -> list[tuple[int, int, int]]:
    """All hex/rgb() colours found in HTML or CSS text."""
    colors: list[tuple[int, int, int]] = []
    for t in texts:
        for m in _HEX.finditer(t):
            colors.append(_norm_hex(m.group(1) or m.group(2)))
        for m in _RGB.finditer(t):
            colors.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return colors


def _hue(c: tuple[int, int, int]) -> float:
    r, g, b = (x / 255 for x in c)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return -1.0  # achromatic
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def _lum(c: tuple[int, int, int]) -> float:
    def f(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = c
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """WCAG contrast ratio 1..21."""
    l1, l2 = _lum(c1), _lum(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _darken(c: tuple[int, int, int], step: float) -> tuple[int, int, int]:
    return tuple(max(0, int(x * (1 - step))) for x in c)  # type: ignore[return-value]


def palette(colors: list[tuple[int, int, int]], max_colors: int = 4) -> dict[str, Any]:
    """Group similar colours, drop greys/white/black, keep the top brand colours.

    Base = darkest kept colour, darkened until white text passes WCAG AA (4.5:1).
    """
    chromatic = [c for c in colors if _hue(c) >= 0 and max(c) - min(c) >= 24]
    clusters: list[list[tuple[int, int, int]]] = []
    for c in sorted(chromatic, key=_hue):
        h = _hue(c)
        for cl in clusters:
            if abs(_hue(cl[0]) - h) <= 30 or abs(_hue(cl[0]) - h) >= 330:
                cl.append(c)
                break
        else:
            clusters.append([c])
    clusters.sort(key=len, reverse=True)
    picked = [cl[0] for cl in clusters[:max_colors]]
    if not picked:
        picked = [_norm_hex(DEFAULT_PALETTE[-1])]
        colors_out = DEFAULT_PALETTE[:-1]
    else:
        colors_out = [f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for c in picked]
    base = min(picked, key=_lum)
    step = 0.0
    while contrast(base, (255, 255, 255)) < 4.5 and step < 0.9:
        step += 0.1
        base = _darken(picked[min(range(len(picked)), key=lambda i: _lum(picked[i]))], step)
    return {
        "colors": colors_out,
        "base": f"#{base[0]:02x}{base[1]:02x}{base[2]:02x}",
        "base_contrast": round(contrast(base, (255, 255, 255)), 2),
    }


def build_theme(
    verdict: "JudgeVerdict", pal: dict[str, Any], candidates: list[ImageCandidate]
) -> dict[str, Any]:
    """theme = {mode, image_url, crop, colors[], base, overlay_strength}."""
    chosen = next((c for c in candidates if verdict.use_image and c.url == verdict.image_url), None)
    if verdict.use_image and chosen is None and candidates:
        chosen = candidates[0]
    if chosen is None:
        return {
            "mode": "gradient",
            "image_url": None,
            "crop": None,
            "colors": pal["colors"],
            "base": pal["base"],
            "overlay_strength": 0.0,
            "reason": verdict.reason,
        }
    # centre portrait crop (9:16) inside the image — code decides the geometry
    target = 9 / 16
    aspect = chosen.width / max(chosen.height, 1)
    if aspect > target:
        w = chosen.height * target
        x = (chosen.width - w) / 2
        crop = {
            "x": round(x / chosen.width, 3),
            "y": 0.0,
            "w": round(w / chosen.width, 3),
            "h": 1.0,
        }
    else:
        h = chosen.width / target
        y = (chosen.height - h) / 2
        crop = {
            "x": 0.0,
            "y": round(y / chosen.height, 3),
            "w": 1.0,
            "h": round(h / chosen.height, 3),
        }
    return {
        "mode": "photo",
        "image_url": chosen.url,
        "crop": crop,
        "colors": pal["colors"],
        "base": pal["base"],
        "overlay_strength": 0.55,  # photo fades into base colour from 40% to 65% of card height
        "reason": verdict.reason,
    }


# --- agents: the only "does this look good?" part ------------------------------------


class Argument(BaseModel):
    stance: str
    points: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    use_image: bool
    image_url: str | None = None
    reason: str = ""


def _agent(name: str, instructions: str, model: str) -> agents.Agent:
    return agents.Agent(
        model=model,
        name=name,
        instructions=instructions,
        output_type=Argument if model == VISION_MODEL else None,
    )


async def _argue(name: str, stance: str, venue: str, cand: ImageCandidate) -> Argument:
    agent = agents.Agent(
        model=VISION_MODEL,
        name=name,
        instructions=(
            f"You are the {stance} in a design debate for a Vybe card about '{venue}'. "
            "Look at the image. Argue in 2-3 short points. Answer only with the schema."
        ),
        output_type=Argument,
    )
    content = [
        agents.TextContentBlock(text=f"Venue: {venue}\nImage: {cand.url} (source: {cand.source})"),
        agents.ImageContentBlock(uri=cand.url),
    ]
    state = await agent.run(content, timeout=90)
    out = getattr(state, "output", None)
    if isinstance(out, Argument):
        out.stance = stance
        return out
    return Argument(stance=stance, points=[str(getattr(state, "text", "") or "no argument")])


async def judge(venue: str, cand: ImageCandidate, pro: Argument, con: Argument) -> JudgeVerdict:
    agent = agents.Agent(
        model=JUDGE_MODEL,
        name="theme-judge",
        instructions=(
            f"Judge a design debate for a Vybe card about '{venue}'. Pro and Con argued about "
            f"using this image: {cand.url}. Decide use_image yes/no (ties go to no), which image "
            "(the url), and a one-line reason. Answer only with the schema."
        ),
        output_type=JudgeVerdict,
    )
    prompt = f"PRO ({pro.stance}): {pro.points}\nCON ({con.stance}): {con.points}"
    state = await agent.run(prompt, timeout=60)
    out = getattr(state, "output", None)
    if isinstance(out, JudgeVerdict):
        return out
    return JudgeVerdict(use_image=False, reason="judge failed to parse; gradient mode")


async def pick_image(venue: str, candidates: list[ImageCandidate]) -> JudgeVerdict:
    """Pro ∥ Con per candidate, then a judge; best candidate wins, else gradient mode."""
    if not candidates:
        return JudgeVerdict(use_image=False, reason="no image candidates passed the pre-filter")
    verdicts: list[JudgeVerdict] = []
    for cand in candidates:
        pro, con = await asyncio.gather(
            _argue("theme-pro", "pro", venue, cand), _argue("theme-con", "con", venue, cand)
        )
        verdicts.append(await judge(venue, cand, pro, con))
    best = next((v for v in verdicts if v.use_image and v.image_url), None)
    if best:
        return best
    return JudgeVerdict(use_image=False, reason="judge rejected every candidate; gradient mode")


# --- network (mocked in tests) ---------------------------------------------------------


async def fetch_text(url: str, limit: int = 200_000) -> str:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "vybe-hackathon-theme/0.1"})
        r.raise_for_status()
        return r.text[:limit]


async def fetch_size(cand: ImageCandidate) -> ImageCandidate:
    try:
        async with (
            httpx.AsyncClient(timeout=10, follow_redirects=True) as client,
            client.stream("GET", cand.url, headers={"User-Agent": "vybe-hackathon-theme/0.1"}) as r,
        ):
            r.raise_for_status()
            data = b""
            async for chunk in r.aiter_bytes(65536):
                data += chunk
                if len(data) > MAX_DOWNLOAD:
                    break
        size = image_size(data)
        if size:
            cand.width, cand.height = size
    except Exception:
        pass  # unsized candidate is dropped by the pre-filter
    return cand


_STYLESHEET = re.compile(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)', re.I)


async def theme_item(item: dict[str, Any]) -> dict[str, Any]:
    """One venue → its theme dict (agents debate images, code does the rest)."""
    venue = f"{item.get('name', '')} ({item.get('type', '')})"
    html = ""
    cands: list[ImageCandidate] = []
    texts = [""]  # inline HTML first; linked CSS appended below
    url = item.get("url")
    if url:
        try:
            html = await fetch_text(url)
            texts[0] = html
            cands = collect_from_html(html, url)
            sheets = [m.group(1) for m in _STYLESHEET.finditer(html)][:3]
            css_texts = await asyncio.gather(
                *[
                    fetch_text(
                        s if s.startswith("http") else url.rstrip("/") + "/" + s.lstrip("/"),
                        100_000,
                    )
                    for s in sheets
                ],
                return_exceptions=True,
            )
            texts += [t for t in css_texts if isinstance(t, str)]
        except Exception:
            html = ""
    cands = list(await asyncio.gather(*[fetch_size(c) for c in cands])) if cands else []
    shortlist = prefilter(cands)
    verdict = await pick_image(venue, shortlist)
    pal = palette(css_colors(*texts))
    return {"id": item["id"], "theme": build_theme(verdict, pal, shortlist)}
