"""SCH-02, SCH-11, SCH-12, SCH-13: round-trip, integrity and lifecycle gating."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from handrail.schema import (
    ArtifactIntegrityError,
    ArtifactNotRunnable,
    ArtifactStatus,
    approve,
    compute_hash,
    ensure_runnable,
    load_artifact,
    parse_artifact,
    save_artifact,
)
from handrail.schema.io import dump_artifact
from tests.conftest import EXAMPLE

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def test_sch02_round_trip_is_lossless() -> None:
    first = load_artifact(EXAMPLE)
    second = parse_artifact(dump_artifact(first))
    assert second == first
    assert compute_hash(second) == compute_hash(first) == first.content_hash


def test_committed_example_is_canonical() -> None:
    assert EXAMPLE.read_text(encoding="utf-8") == dump_artifact(load_artifact(EXAMPLE))


def test_sch11_edit_without_version_bump_is_refused(example_dict: dict[str, Any]) -> None:
    example_dict["steps"][2]["expect"]["timeout_ms"] = 1
    with pytest.raises(ArtifactIntegrityError, match="bump the version"):
        parse_artifact(example_dict)


def test_sch11_approved_file_cannot_be_overwritten(tmp_path: Path) -> None:
    approved = load_artifact(EXAMPLE)
    save_artifact(approved, tmp_path)
    changed = approved.model_copy(update={"description": "Something else entirely."})
    with pytest.raises(ArtifactIntegrityError, match="new version"):
        save_artifact(changed, tmp_path)


def test_hash_ignores_lifecycle_metadata(draft_dict: dict[str, Any]) -> None:
    draft = parse_artifact(draft_dict)
    approved = approve(draft, reviewer="reviewer", at=NOW)
    assert approved.status is ArtifactStatus.APPROVED
    assert approved.content_hash == compute_hash(draft)
    assert approved.provenance.reviewed_by == "reviewer"


def test_only_drafts_can_be_approved() -> None:
    with pytest.raises(ArtifactNotRunnable, match="only drafts"):
        approve(load_artifact(EXAMPLE), reviewer="reviewer", at=NOW)


def test_sch12_draft_cannot_run_unattended(draft_dict: dict[str, Any]) -> None:
    draft = parse_artifact(draft_dict)
    with pytest.raises(ArtifactNotRunnable, match="draft"):
        ensure_runnable(draft)
    ensure_runnable(draft, allow_draft=True)


def test_approved_is_runnable() -> None:
    ensure_runnable(load_artifact(EXAMPLE))


def test_sch13_deprecated_points_to_successor(example_dict: dict[str, Any]) -> None:
    example_dict["status"] = "deprecated"
    example_dict["superseded_by"] = "1.1.0"
    artifact = parse_artifact(example_dict)  # hash still valid: lifecycle is excluded
    with pytest.raises(
        ArtifactNotRunnable, match=r"mockbank\.member\.read_savings_balance@1\.1\.0"
    ):
        ensure_runnable(artifact, allow_draft=True)


def test_deprecated_requires_successor(example_dict: dict[str, Any]) -> None:
    example_dict["status"] = "deprecated"
    with pytest.raises(Exception, match="superseded_by"):
        parse_artifact(example_dict)
