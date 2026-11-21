import asyncio
import struct

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
    assert theme.palette([])["colors"] == theme.DEFAULT_PALETTE[:-1]  # Vybe fallback


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
        venue: str, cand: theme.ImageCandidate, pro: theme.Argument, con: theme.Argument
    ) -> theme.JudgeVerdict:
        return theme.JudgeVerdict(
            use_image=cand.url.endswith("big.jpg"), image_url=cand.url, reason="ok"
        )

    monkeypatch.setattr(theme, "_argue", fake_argue)
    monkeypatch.setattr(theme, "judge", fake_judge)
    cands = [
        theme.ImageCandidate(url="https://x/big.jpg", width=1920, height=1080),
        theme.ImageCandidate(url="https://x/small.jpg", width=1200, height=1200),
    ]
    verdict = asyncio.run(theme.pick_image("Test Venue", cands))
    assert verdict.use_image and verdict.image_url == "https://x/big.jpg"
    # all rejected -> gradient mode
    monkeypatch.setattr(theme, "judge", lambda v, c, p, co: _rejected())
    verdict2 = asyncio.run(theme.pick_image("Test Venue", cands))
    assert not verdict2.use_image and "gradient" in verdict2.reason


async def _rejected() -> theme.JudgeVerdict:
    return theme.JudgeVerdict(use_image=False, reason="blurry")


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
    assert out["theme"]["colors"]  # fallback palette present


def test_theme_workflows_registered() -> None:
    from mistralai.workflows import get_workflow_definition

    from pipeline import theme_wf

    assert get_workflow_definition(theme_wf.VybeTheme).name == "vybe-theme"
    assert get_workflow_definition(theme_wf.VybeThemeItem).name == "vybe-theme-item"
