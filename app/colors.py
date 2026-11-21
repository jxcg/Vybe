"""Venue colours for the frontend's `colors: {deep, soft, light}` from one brand colour.

The brand colour comes from the venue's own website (found by Mistral's pipeline). We keep its hue
and set lightness and chroma ourselves, so every card stays readable whatever the brand looks like.
This follows the frontend's rule in INTEGRATION.md, with a little more chroma so brands stand out.
"""

import math
import re

# (lightness, max chroma) in OKLCH
LEVELS = {"deep": (0.30, 0.07), "soft": (0.42, 0.09), "light": (0.89, 0.035)}
HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _oklch(hex_colour: str) -> tuple[float, float, float]:
    r, g, b = (_to_linear(int(hex_colour[i : i + 2], 16) / 255) for i in (0, 2, 4))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def _hex(lightness: float, chroma: float, hue: float) -> str:
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    return "#" + "".join(f"{round(_from_linear(c) * 255):02x}" for c in rgb)


def venue_colors(brand: object) -> dict[str, str] | None:
    """`#e4002b` → {"deep", "soft", "light"} hex colours; None if the input isn't a hex colour."""
    m = HEX.match(brand) if isinstance(brand, str) else None
    if not m:
        return None
    _, chroma, hue = _oklch(m.group(1))
    return {
        name: _hex(lightness, min(chroma, cap), hue) for name, (lightness, cap) in LEVELS.items()
    }
