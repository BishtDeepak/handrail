"""OBS-01, OBS-09 and redaction through the real logging pipeline (RED-05, RED-14)."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from pydantic import SecretStr

from handrail.obs import (
    CORRELATION_KEYS,
    Event,
    configure_logging,
    emit,
    get_logger,
    new_run_id,
    run_context,
    step_context,
)
from handrail.redaction import sensitive_values

pytestmark = pytest.mark.unit


@pytest.fixture
def sink() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    configure_logging(buffer, level="DEBUG")
    yield buffer
    structlog.reset_defaults()


def _events(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


def test_obs01_correlation_ids_on_every_event(sink: io.StringIO) -> None:
    run_id = new_run_id()
    with run_context(run_id, artifact_ref="a.b@1.0.0", session_id="sess_1"):
        emit(Event.RUN_START, mode="replay")
        with step_context("submit_search"):
            emit(Event.STEP_START, action="click")
        emit(Event.RUN_END)
    emit(Event.POLICY_BLOCK, rule="outside run")

    events = _events(sink)
    assert [e["event"] for e in events] == ["run_start", "step_start", "run_end", "policy_block"]
    for event in events:
        assert set(CORRELATION_KEYS) <= set(event)
    assert events[1]["step_id"] == "submit_search"
    assert events[0]["step_id"] is None
    assert events[0]["run_id"] == run_id
    assert events[0]["controller"] == "automation"
    assert events[3]["run_id"] is None


def test_obs09_every_line_is_json(sink: io.StringIO) -> None:
    for event in Event:
        emit(event, n=1)
    lines = sink.getvalue().splitlines()
    assert len(lines) == len(Event)
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_log_pipeline_redacts_fields_and_values(sink: io.StringIO) -> None:
    with run_context(new_run_id()), sensitive_values({"input:member_id": "48213"}):
        emit(
            Event.STEP_END,
            observed="No member found for 48213; SSN 123-45-6789",
            api_key=SecretStr("sk-test-123"),
        )
    text = sink.getvalue()
    for leaked in ("48213", "123-45-6789", "sk-test-123"):
        assert leaked not in text


def test_red14_tracebacks_redacted(sink: io.StringIO) -> None:
    try:
        raise RuntimeError("card 4111 1111 1111 1111 declined")
    except RuntimeError:
        get_logger().exception("step_failed")
    (event,) = _events(sink)
    assert "4111 1111 1111 1111" not in json.dumps(event)
    assert "RuntimeError" in event["exception"]


def test_timestamps_survive_redaction(sink: io.StringIO) -> None:
    emit(Event.RUN_START)
    (event,) = _events(sink)
    assert "REDACTED" not in event["ts"]


def test_run_ids_do_not_look_like_accounts() -> None:
    from handrail.redaction import redact_text

    run_id = new_run_id()
    assert redact_text(run_id) == run_id
