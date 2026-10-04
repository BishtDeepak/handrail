"""LOC-01..LOC-10: locator chains resolve deterministically on a hostile legacy surface."""

from __future__ import annotations

from typing import Any

import pytest

from handrail.schema.artifact import Condition, Target
from handrail.surface import LocatorAmbiguous, LocatorNotFound, NotActionable
from handrail.surface.playwright_surface import PlaywrightSurface
from tests.integration.conftest import MockBank

pytestmark = pytest.mark.integration

MEMBER_ID_FIELD = {
    "frame": ["main"],
    "chain": [
        {"by": "role", "role": "textbox", "name": "Member ID"},
        {"by": "label", "label": "Member ID"},
    ],
}
SEARCH_BUTTON = {"frame": ["main"], "chain": [{"by": "role", "role": "button", "name": "Search"}]}
SAVINGS_BALANCE = {
    "frame": ["main"],
    "chain": [{"by": "table_cell", "row_key": "Savings", "column": "Balance"}],
}
DETAIL = Condition.model_validate(
    {
        "all_of": [
            {"kind": "role", "frame": ["main"], "role": "heading", "name_matches": "^Member Detail"}
        ]
    }
)


def t(data: dict[str, Any]) -> Target:
    return Target.model_validate(data)


async def _open_detail(surface: PlaywrightSurface, member_id: str = "48213") -> None:
    await surface.type_text(t(MEMBER_ID_FIELD), member_id, timeout_ms=3000)
    await surface.click(t(SEARCH_BUTTON), timeout_ms=3000)
    assert await surface.wait_for_any({"detail": DETAIL}, timeout_ms=5000) == "detail"


async def test_loc01_primary_strategy(surface: PlaywrightSurface) -> None:
    res = await surface.resolve(t(SEARCH_BUTTON), timeout_ms=3000)
    assert (res.strategy, res.fallbacks, res.brittle) == (0, 0, False)


async def test_loc02_loc07_label_fallback(surface: PlaywrightSurface) -> None:
    # The legacy input has no accessible name: role+name misses, label adjacency matches.
    res = await surface.resolve(t(MEMBER_ID_FIELD), timeout_ms=3000)
    assert (res.strategy, res.fallbacks) == (1, 1)
    await surface.type_text(t(MEMBER_ID_FIELD), "48213", timeout_ms=3000)
    value, _ = await surface.read_text(t(MEMBER_ID_FIELD), timeout_ms=1000)
    assert value == "48213"


async def test_loc03_ambiguous_is_hard_failure(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(duplicate_search=True)
    await surface.navigate("/members/search")
    with pytest.raises(LocatorAmbiguous) as info:
        await surface.resolve(t(SEARCH_BUTTON), timeout_ms=3000)
    assert info.value.count == 2


async def test_loc04_frame_scoped(surface: PlaywrightSurface) -> None:
    unscoped = t({"chain": SEARCH_BUTTON["chain"]})
    with pytest.raises(LocatorNotFound):
        await surface.resolve(unscoped, timeout_ms=500)
    assert (await surface.resolve(t(SEARCH_BUTTON), timeout_ms=3000)).strategy == 0


async def test_loc05_same_name_in_two_frames(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(nav_search_button=True)
    await surface.navigate("/members/search")
    assert (await surface.resolve(t(SEARCH_BUTTON), timeout_ms=3000)).strategy == 0
    nav = t({"frame": ["nav"], "chain": SEARCH_BUTTON["chain"]})
    assert (await surface.resolve(nav, timeout_ms=3000)).strategy == 0


@pytest.mark.parametrize("reorder", [False, True])
async def test_loc06_table_cell_independent_of_row_order(
    surface: PlaywrightSurface, mockbank: MockBank, reorder: bool
) -> None:
    mockbank.set(reorder_rows=reorder)
    await _open_detail(surface)
    value, res = await surface.read_text(t(SAVINGS_BALANCE), timeout_ms=3000)
    assert value == "$8,812.40"
    assert res.strategy == 0


async def test_loc08_css_last_resort_is_flagged(surface: PlaywrightSurface) -> None:
    target = t(
        {
            "frame": ["main"],
            "chain": [
                {"by": "role", "role": "button", "name": "Lookup"},
                {"by": "css", "selector": "input[type=submit]"},
            ],
        }
    )
    res = await surface.resolve(target, timeout_ms=3000)
    assert (res.strategy, res.fallbacks, res.brittle) == (1, 1, True)


async def test_loc09_disabled_control_not_actionable(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(disabled_search=True)
    await surface.navigate("/members/search")
    with pytest.raises(NotActionable, match="disabled"):
        await surface.click(t(SEARCH_BUTTON), timeout_ms=600)


async def test_loc10_late_element_found_within_budget(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(late_render_ms=1200)
    await surface.navigate("/members/search")
    res = await surface.resolve(t(SEARCH_BUTTON), timeout_ms=4000)
    assert res.strategy == 0


async def test_late_element_past_budget(surface: PlaywrightSurface, mockbank: MockBank) -> None:
    mockbank.set(late_render_ms=3000)
    await surface.navigate("/members/search")
    with pytest.raises(LocatorNotFound) as info:
        await surface.resolve(t(SEARCH_BUTTON), timeout_ms=500)
    assert info.value.trail == ['role=button name="Search"']


async def test_renamed_button_falls_back_to_text(
    surface: PlaywrightSurface, mockbank: MockBank
) -> None:
    mockbank.set(rename_search="Find")
    await surface.navigate("/members/search")
    target = t(
        {
            "frame": ["main"],
            "chain": [
                {"by": "role", "role": "button", "name": "Search"},
                {"by": "text", "text": "Find"},
            ],
        }
    )
    res = await surface.resolve(target, timeout_ms=2000)
    assert res.fallbacks == 1
