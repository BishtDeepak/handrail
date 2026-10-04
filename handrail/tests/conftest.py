from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "artifacts" / "mockbank.member.read_savings_balance" / "1.0.0.json"


@pytest.fixture
def example_dict() -> dict[str, Any]:
    """The committed, approved example artifact as a plain mapping."""
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def draft_dict(example_dict: dict[str, Any]) -> dict[str, Any]:
    """A draft copy without hash or review metadata, safe to mutate."""
    data = copy.deepcopy(example_dict)
    data["status"] = "draft"
    data.pop("content_hash", None)
    data["provenance"].pop("reviewed_by", None)
    data["provenance"].pop("approved_at", None)
    return data
