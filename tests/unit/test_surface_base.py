"""Pure helpers behind the surface seam."""

from __future__ import annotations

import pytest

from handrail.schema.artifact import Target
from handrail.surface import FrameSnapshot, LocatorNotFound, Snapshot, describe_target
from handrail.surface.playwright_surface import xpath_literal

pytestmark = pytest.mark.unit


def test_xpath_literal_quotes() -> None:
    assert xpath_literal("Member ID") == "'Member ID'"
    assert xpath_literal("Member's ID") == '"Member\'s ID"'
    assert xpath_literal("""a'b"c""") == "concat('a', \"'\", 'b\"c')"


def test_describe_target() -> None:
    target = Target.model_validate(
        {
            "frame": ["main"],
            "chain": [
                {"by": "role", "role": "button", "name": "Search"},
                {"by": "css", "selector": "input[type=submit]"},
            ],
        }
    )
    assert describe_target(target) == '[main] role=button name="Search" -> css=input[type=submit]'
    err = LocatorNotFound(target, 500)
    assert err.kind.value == "locator_not_found"
    assert len(err.trail) == 2


def test_snapshot_hash_depends_on_content_only() -> None:
    a = Snapshot("u", "t", (FrameSnapshot(("main",), "u1", "- heading"),))
    b = Snapshot("other", "t2", (FrameSnapshot(("main",), "u2", "- heading"),))
    c = Snapshot("u", "t", (FrameSnapshot(("main",), "u1", "- button"),))
    assert a.state_hash == b.state_hash != c.state_hash
    assert "# frame: main" in a.text()
