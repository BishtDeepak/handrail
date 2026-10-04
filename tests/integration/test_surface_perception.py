"""Detectors, waits, snapshots and masked screenshots (RED-06)."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from mockbank.seed import MEMBERS

from handrail.schema.artifact import Condition, Target
from handrail.surface.playwright_surface import MASK_COLOR, PlaywrightSurface
from tests.integration.conftest import MockBank

pytestmark = pytest.mark.integration


def c(data: dict[str, Any]) -> Condition:
    return Condition.model_validate(data)


SEARCH_FORM = c(
    {"all_of": [{"kind": "role", "frame": ["main"], "role": "heading", "name": "Member Search"}]}
)
NOT_FOUND = c({"any_of": [{"kind": "text", "frame": ["main"], "matches": "No member found"}]})
NOTICE = c(
    {"all_of": [{"kind": "role", "role": "dialog", "frame": ["main"], "name": "System Notice"}]}
)
EXPIRED = c({"any_of": [{"kind": "text", "frame": ["main"], "matches": "session has expired"}]})


async def test_checkpoint_holds(surface: PlaywrightSurface) -> None:
    assert await surface.holds(SEARCH_FORM)
    assert not await surface.holds(NOT_FOUND)


async def test_url_detector(surface: PlaywrightSurface) -> None:
    assert await surface.holds(
        c({"any_of": [{"kind": "url", "matches": r"/frame/members/search"}]})
    )


async def test_wait_for_business_outcome(surface: PlaywrightSurface) -> None:
    await surface.navigate("/members/search?mid=99999")
    found = await surface.wait_for_any(
        {"x": SEARCH_FORM.model_copy(), "nf": NOT_FOUND}, timeout_ms=3000
    )
    assert found in {"x", "nf"}
    assert await surface.wait_for_any({"nf": NOT_FOUND}, timeout_ms=3000) == "nf"


async def test_wait_times_out(surface: PlaywrightSurface) -> None:
    assert await surface.wait_for_any({"nf": NOT_FOUND}, timeout_ms=300) is None


async def test_dialog_detected_and_dismissed(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(notice_dialog=1)
    await surface.navigate("/members/search")
    assert await surface.holds(NOTICE)
    ok = Target.model_validate(
        {"frame": ["main"], "chain": [{"by": "role", "role": "button", "name": "OK"}]}
    )
    await surface.click(ok, timeout_ms=2000)
    assert await surface.wait_until_clear(NOTICE, timeout_ms=3000)
    assert await surface.holds(SEARCH_FORM)


async def test_dialog_that_stays_is_reported(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(notice_dialog=1)
    await surface.navigate("/members/search")
    assert not await surface.wait_until_clear(NOTICE, timeout_ms=300)


async def test_session_expiry_detected(surface: PlaywrightSurface, mockbank: MockBank) -> None:
    mockbank.state.expire_sessions()
    await surface.page.frame(name="main").goto(f"{mockbank.url}/frame/members/search")  # type: ignore[union-attr]
    assert await surface.holds(EXPIRED)


async def test_snapshot_lists_frames(surface: PlaywrightSurface) -> None:
    snap = await surface.snapshot()
    paths = [f.path for f in snap.frames]
    assert paths == [(), ("nav",), ("main",)]
    main = snap.frames[2]
    assert "Member Search" in main.aria
    assert 'button "Search"' in main.aria
    assert len(snap.state_hash) == 64
    assert snap.state_hash == (await surface.snapshot()).state_hash


async def test_snapshot_changes_with_state(surface: PlaywrightSurface) -> None:
    before = (await surface.snapshot()).state_hash
    await surface.navigate("/members/search?mid=99999")
    await surface.wait_for_any({"nf": NOT_FOUND}, timeout_ms=3000)
    assert (await surface.snapshot()).state_hash != before


async def _pixel(surface: PlaywrightSurface, png: bytes, x: float, y: float) -> list[int]:
    """Read one pixel of a PNG by drawing it on a canvas in a scratch page."""
    page = await surface.page.context.new_page()
    try:
        data = base64.b64encode(png).decode()
        await page.set_content("<canvas id=c></canvas>")
        rgba: list[int] = await page.evaluate(
            """async ([src, x, y]) => {
                const img = new Image(); img.src = src; await img.decode();
                const c = document.getElementById('c'); c.width = img.width; c.height = img.height;
                const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
                return Array.from(ctx.getImageData(x, y, 1, 1).data);
            }""",
            [f"data:image/png;base64,{data}", int(x), int(y)],
        )
        return rgba
    finally:
        await page.close()


async def test_red06_screenshot_masks_sensitive_cells(surface: PlaywrightSurface) -> None:
    await surface.navigate("/members/48213")
    main = surface.page.frame(name="main")
    assert main is not None
    ssn_cell = main.get_by_text(MEMBERS["48213"].ssn, exact=True)
    box = await ssn_cell.bounding_box()
    assert box is not None
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    magenta = [int(MASK_COLOR[i : i + 2], 16) for i in (1, 3, 5)]

    masked = await surface.screenshot()
    assert (await _pixel(surface, masked, cx, cy))[:3] == magenta

    raw = await surface.screenshot(mask_data=False)
    assert (await _pixel(surface, raw, cx, cy))[:3] != magenta


async def test_screenshot_masks_explicit_target(surface: PlaywrightSurface) -> None:
    heading = Target.model_validate(
        {"frame": ["main"], "chain": [{"by": "role", "role": "heading", "name": "Member Search"}]}
    )
    main = surface.page.frame(name="main")
    assert main is not None
    box = await main.get_by_role("heading").bounding_box()
    assert box is not None
    png = await surface.screenshot(mask=[heading], mask_data=False)
    pixel = await _pixel(surface, png, box["x"] + 5, box["y"] + box["height"] / 2)
    assert pixel[:3] == [255, 0, 255]
