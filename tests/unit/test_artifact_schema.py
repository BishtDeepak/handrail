"""SCH-01, SCH-04..SCH-10, SCH-15: the schema accepts good contracts and rejects bad ones."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from handrail.schema import Artifact, ArtifactInvalid, parse_artifact
from handrail.schema.artifact import ClickStep, ExtractStep, NavigateStep, TypeStep

pytestmark = pytest.mark.unit


def _invalid(data: dict[str, Any]) -> str:
    with pytest.raises(ArtifactInvalid) as info:
        parse_artifact(data)
    return str(info.value)


def test_sch01_valid_artifact_loads(example_dict: dict[str, Any]) -> None:
    artifact = parse_artifact(example_dict)
    assert isinstance(artifact, Artifact)
    assert artifact.ref == "mockbank.member.read_savings_balance@1.0.0"
    assert [type(s) for s in artifact.steps] == [NavigateStep, TypeStep, ClickStep, ExtractStep]


def test_sch04_unknown_step_action(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][2]["action"] = "hover"
    assert "hover" in _invalid(draft_dict)


def test_sch05_dangling_expect_reference(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][2]["expect"]["any_of"].append("outcome:ACCOUNT_LOCKED")
    assert "ACCOUNT_LOCKED" in _invalid(draft_dict)


def test_sch05_dangling_success_checkpoint(draft_dict: dict[str, Any]) -> None:
    draft_dict["success"]["checkpoint"] = "nowhere"
    assert "nowhere" in _invalid(draft_dict)


def test_sch06_undeclared_placeholder(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][1]["value"] = "{{inputs.account_no}}"
    assert "account_no" in _invalid(draft_dict)


def test_sch07_output_never_extracted(draft_dict: dict[str, Any]) -> None:
    draft_dict["outputs"]["checking_balance"] = {"type": "decimal", "sensitivity": "confidential"}
    assert "checking_balance" in _invalid(draft_dict)


def test_sch07_extract_undeclared_output(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][3]["output"] = "mystery"
    assert "mystery" in _invalid(draft_dict)


def test_sch08_duplicate_step_ids(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"].append(copy.deepcopy(draft_dict["steps"][0]))
    assert "duplicate step ids" in _invalid(draft_dict)


def test_sch09_risk_is_mandatory(draft_dict: dict[str, Any]) -> None:
    del draft_dict["steps"][2]["risk"]
    assert "risk" in _invalid(draft_dict)


def test_sch10_unsupported_schema_version(draft_dict: dict[str, Any]) -> None:
    draft_dict["schema_version"] = "2.0"
    assert "schema_version" in _invalid(draft_dict)


def test_sch15_no_transcript_in_artifact(draft_dict: dict[str, Any]) -> None:
    # Unknown fields are forbidden, so a raw model transcript cannot ride along.
    draft_dict["transcript"] = [{"role": "assistant", "content": "click Search"}]
    assert "transcript" in _invalid(draft_dict)
    assert not {"transcript", "messages", "prompt"} & set(Artifact.model_fields)


def test_route_params_must_be_bound(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][0]["route"] = "/member/:member_id"
    assert "bind" in _invalid(draft_dict)


def test_invalid_regex_rejected(draft_dict: dict[str, Any]) -> None:
    draft_dict["inputs"]["member_id"]["pattern"] = "(unclosed"
    assert "regular expression" in _invalid(draft_dict)


def test_recorded_match_within_chain(draft_dict: dict[str, Any]) -> None:
    draft_dict["steps"][1]["target"]["recorded_match"] = 5
    assert "recorded_match" in _invalid(draft_dict)


def test_triage_recovery_must_exist(draft_dict: dict[str, Any]) -> None:
    draft_dict["triage"] = {"enabled": True, "allowed_recoveries": ["reboot_mainframe"]}
    assert "reboot_mainframe" in _invalid(draft_dict)


def test_sensitivity_is_mandatory(draft_dict: dict[str, Any]) -> None:
    del draft_dict["inputs"]["member_id"]["sensitivity"]
    assert "sensitivity" in _invalid(draft_dict)


def test_artifact_is_immutable(example_dict: dict[str, Any]) -> None:
    artifact = parse_artifact(example_dict)
    with pytest.raises(ValueError, match="frozen"):
        artifact.version = "9.9.9"  # type: ignore[misc]
