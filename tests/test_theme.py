import asyncio
import struct
from typing import Any

import pytest

from pipeline import theme

# --- measurable code -------------------------------------------------------------------


def _png(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", w, h) + b"\x00" * 10


def _gif(w: int, h: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 10


def _jpeg(w: int, h: int) -> bytes:
    sof = b"\xff\xc0" + b"\x00\x11" + b"\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x00" * 6
    return b"\xff\xd8" + b"\xff\xe0" + b"\x00\x10" + b"JFIF\x00" + b"\x00" * 9 + sof


def test_image_size_parsers() -> None:
    assert theme.image_size(_png(1920, 1080)) == (1920, 1080)
    assert theme.image_size(_gif(800, 600)) == (800, 600)
    assert theme.image_size(_jpeg(1600, 900)) == (1600, 900)
    assert theme.image_size(b"not an image") is None


def test_collect_from_html_finds_sharing_image_and_logo() -> None:
    html = (
        '<meta property="og:image" content="https://x.test/share.jpg">'
        '<meta name="twitter:image" content="https://x.test/tw.jpg">'
        '<link rel="icon" href="https://x.test/favicon.png">'
    )
    cands = theme.collect_from_html(html, "https://x.test")
    urls = [c.url for c in cands]
    assert "https://x.test/share.jpg" in urls and "https://x.test/favicon.png" in urls
    assert len(theme.collect_from_html("<html></html>", "https://x.test")) == 0


def test_prefilter_drops_small_logos_and_extreme_aspects() -> None:
    cands = [
        theme.ImageCandidate(url="https://x/big.jpg", width=1920, height=1080),  # keep
        theme.ImageCandidate(url="https://x/tall.jpg", width=1080, height=1920),  # keep (portrait)
        theme.ImageCandidate(url="https://x/small.jpg", width=800, height=600),  # too small
        theme.ImageCandidate(url="https://x/logo.png", width=2000, height=500),  # logoish
        theme.ImageCandidate(
            url="https://x/wide.jpg", width=3000, height=500
        ),  # can't crop portrait
    ]
    kept = theme.prefilter(cands)
    assert [c.url for c in kept] == ["https://x/big.jpg", "https://x/tall.jpg"]


def test_css_colors_and_palette() -> None:
    colors = theme.css_colors("body{color:#7C3AED} a{background:rgb(219, 39, 119)} .x{--c:#fff}")
    assert (0x7C, 0x3A, 0xED) in colors and (219, 39, 119) in colors
    pal = theme.palette(
        [(124, 58, 237), (219, 39, 119), (250, 250, 250), (10, 10, 10), (128, 128, 128)]
    )
    assert len(pal["colors"]) == 2  # white/black/grey dropped
    assert pal["base_contrast"] >= 4.5  # base darkened until white text passes AA
    # no real brand colour -> nothing written (the app falls back to category colour)
    assert theme.palette([]) == {"colors": [], "base": None, "base_contrast": None}
    # declared theme-color leads the palette
    pal2 = theme.palette([(200, 30, 30)], preferred=(30, 60, 200))
    assert pal2["colors"][0] == "#1e3cc8"


def test_theme_color_meta_and_manifest() -> None:
    assert theme.theme_color('<meta name="theme-color" content="#8B2332">') == (0x8B, 0x23, 0x32)
    assert theme.theme_color("<html>", '{"theme_color": "#1e5aa0"}') == (30, 90, 160)
    assert theme.theme_color("<html>", "") is None


def test_host_public_blocks_private_ips(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def fake_getaddrinfo(host: str, port: Any) -> list[tuple[Any, ...]]:
        ip = "127.0.0.1" if host == "localhost" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert not theme._host_public("localhost")
    assert theme._host_public("example.com")


def test_merge_themes_writes_brand_color_only_with_base() -> None:
    existing = {"a": {"deal": "2-for-1", "verified": True}}
    results = [
        {"id": "a", "theme": {"mode": "photo", "base": "#8b2332", "colors": ["#8b2332"]}},
        {"id": "b", "theme": {"mode": "gradient", "base": None, "colors": []}},
    ]
    out = theme.merge_themes(existing, results)
    assert out["a"]["brand_color"] == "#8b2332" and out["a"]["theme"]["mode"] == "photo"
    assert out["a"]["deal"] == "2-for-1"  # existing extras survive
    assert "brand_color" not in out["b"]  # no fallback palette written


def test_contrast_wcag() -> None:
    assert theme.contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert theme.contrast((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)


def test_build_theme_photo_and_gradient() -> None:
    pal = theme.palette([(124, 58, 237), (219, 39, 119)])
    cands = [theme.ImageCandidate(url="https://x/big.jpg", width=1920, height=1080)]
    photo = theme.build_theme(
        theme.JudgeVerdict(use_image=True, image_url=cands[0].url, reason="great"), pal, cands
    )
    assert photo["mode"] == "photo" and photo["image_url"] == cands[0].url
    assert photo["crop"]["h"] == 1.0 and 0 < photo["crop"]["w"] < 1  # centre portrait crop
    assert photo["overlay_strength"] == 0.55
    grad = theme.build_theme(theme.JudgeVerdict(use_image=False, reason="no"), pal, [])
    assert grad["mode"] == "gradient" and grad["image_url"] is None


# --- agents (mocked) -------------------------------------------------------------------


def test_pick_image_debates_then_judges(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_argue(
        name: str, stance: str, venue: str, cand: theme.ImageCandidate
    ) -> theme.Argument:
        return theme.Argument(stance=stance, points=[f"{stance} point"])

    async def fake_judge(
        venue: str, debates: list[tuple[str, theme.Argument, theme.Argument]]
    ) -> theme.JudgeVerdict:
        assert [url for url, _, _ in debates] == ["https://x/big.jpg", "https://x/small.jpg"]
        assert [(pro.stance, con.stance) for _, pro, con in debates] == [("pro", "con")] * 2
        return theme.JudgeVerdict(use_image=True, image_url=debates[0][0], reason="ok")

    monkeypatch.setattr(theme, "_argue", fake_argue)
    monkeypatch.setattr(theme, "judge", fake_judge)
    cands = [
        theme.ImageCandidate(url="https://x/big.jpg", width=1920, height=1080),
        theme.ImageCandidate(url="https://x/small.jpg", width=1200, height=1200),
    ]
    verdict = asyncio.run(theme.pick_image("Test Venue", cands))
    assert verdict.use_image and verdict.image_url == "https://x/big.jpg"
    # all rejected -> gradient mode
    monkeypatch.setattr(theme, "judge", lambda venue, debates: _rejected())
    verdict2 = asyncio.run(theme.pick_image("Test Venue", cands))
    assert not verdict2.use_image and "gradient" in verdict2.reason


async def _rejected() -> theme.JudgeVerdict:
    return theme.JudgeVerdict(use_image=False, reason="blurry")


async def _reviewed_photo(url: str, colors: list[tuple[int, int, int]]) -> dict[str, Any]:
    return {"base": "#32254a", "colors": ["#784abd"], "fade_start": 40, "contrast": 5.2}


def test_theme_item_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_text(url: str, limit: int = 200_000) -> str:
        return '<meta property="og:image" content="https://x/share.jpg"> body{color:#7C3AED}'

    async def fake_fetch_size(cand: theme.ImageCandidate) -> theme.ImageCandidate:
        cand.width, cand.height = 1920, 1080
        return cand

    async def fake_pick(venue: str, cands: list[theme.ImageCandidate]) -> theme.JudgeVerdict:
        return theme.JudgeVerdict(
            use_image=True, image_url="https://x/share.jpg", reason="on brand"
        )

    monkeypatch.setattr(theme, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(theme, "fetch_size", fake_fetch_size)
    monkeypatch.setattr(theme, "pick_image", fake_pick)
    monkeypatch.setattr(theme, "read_photo_theme", _reviewed_photo)
    out = asyncio.run(
        theme.theme_item({"id": "v1", "name": "Test", "type": "food_deal", "url": "https://x.test"})
    )
    assert out["id"] == "v1"
    assert out["theme"]["mode"] == "photo" and out["theme"]["image_url"] == "https://x/share.jpg"
    assert out["theme"]["base"].startswith("#")


def test_theme_item_no_website_is_gradient(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_pick(venue: str, cands: list[theme.ImageCandidate]) -> theme.JudgeVerdict:
        return theme.JudgeVerdict(use_image=False, reason="no candidates")

    monkeypatch.setattr(theme, "pick_image", fake_pick)
    out = asyncio.run(
        theme.theme_item({"id": "v2", "name": "Park", "type": "activity", "url": None})
    )
    assert out["theme"]["mode"] == "gradient"
    assert out["theme"]["colors"] == [] and out["theme"]["base"] is None  # no fallback palette


def test_theme_workflows_registered() -> None:
    from mistralai.workflows import get_workflow_definition

    from pipeline import theme_wf

    assert get_workflow_definition(theme_wf.VybeTheme).name == "vybe-theme"
    assert get_workflow_definition(theme_wf.VybeThemeItem).name == "vybe-theme-item"


def test_workflow_selects_google_photo_without_storing_its_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import places

    photos: list[dict[str, Any]] = [
        {"url": "https://example.com/front", "index": 0, "width": 1600, "height": 1000},
        {"url": "https://example.com/interior", "index": 1, "width": 1440, "height": 1080},
    ]
    monkeypatch.setattr(places, "photo_candidates", lambda _: photos)

    async def choose(_: str, candidates: list[theme.ImageCandidate]) -> theme.JudgeVerdict:
        assert [candidate.url for candidate in candidates] == [photo["url"] for photo in photos]
        return theme.JudgeVerdict(
            use_image=True, image_url=photos[1]["url"], reason="Inviting interior"
        )

    monkeypatch.setattr(theme, "pick_image", choose)
    monkeypatch.setattr(theme, "read_photo_theme", _reviewed_photo)
    result = asyncio.run(theme.theme_item({"id": "venue", "source": "Google Places"}))
    assert result["theme"]["mode"] == "photo"
    assert result["theme"]["google_photo"] == {"index": 1, "width": 1440, "height": 1080}
    assert result["theme"]["image_url"] is None
    assert result["theme"]["fade_start"] == 40

    async def unreadable(url: str, colors: list[tuple[int, int, int]]) -> None:
        return None

    monkeypatch.setattr(theme, "read_photo_theme", unreadable)
    result = asyncio.run(theme.theme_item({"id": "venue", "source": "Google Places"}))
    assert result["theme"]["mode"] == "gradient"
    assert "google_photo" not in result["theme"]


def test_photo_readability_adjusts_fade_and_preserves_photo_hue() -> None:
    from io import BytesIO

    from PIL import Image

    def image_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (80, 60), color).save(output, "PNG")
        return output.getvalue()

    dark = theme.photo_readability(image_bytes((16, 38, 80)), [])
    bright = theme.photo_readability(image_bytes((214, 235, 255)), [])
    assert dark is not None and bright is not None
    assert bright["fade_start"] < dark["fade_start"]
    assert bright["base"] is not None and bright["colors"][0] == "#d6ebff"
    assert bright["contrast"] >= 4.5
    assert theme.photo_readability(b"broken image", []) is None
