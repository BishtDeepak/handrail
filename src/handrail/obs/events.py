"""Structured JSONL events with correlation IDs, redacted before rendering.

Every event carries ``run_id``, ``step_id``, ``artifact_ref``, ``session_id`` and ``controller``
(``None`` when not applicable), so a run can be reconstructed from its log alone.
Field names are OpenTelemetry-friendly; an OTLP exporter can be added without changing callers.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from enum import StrEnum
from typing import Any, TextIO

import structlog
from structlog.contextvars import bound_contextvars, merge_contextvars

from handrail.redaction import structlog_processor

CORRELATION_KEYS = ("run_id", "step_id", "artifact_ref", "session_id", "controller")


class Event(StrEnum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    PLANNER_CALL = "planner_call"
    JUDGE_DECISION = "judge_decision"
    MODEL_DISAGREEMENT = "model_disagreement"
    LOCATOR_FALLBACK = "locator_fallback"
    RECOVERY_APPLIED = "recovery_applied"
    POLICY_BLOCK = "policy_block"
    CONTROL_TRANSITION = "control_transition"
    HUMAN_ACTION = "human_action"


def _ensure_correlation(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in CORRELATION_KEYS:
        event_dict.setdefault(key, None)
    return event_dict


def configure_logging(sink: TextIO | None = None, level: str = "INFO") -> None:
    """Route all events to ``sink`` (stdout by default) as one JSON object per line.

    Redaction runs after exception formatting (so tracebacks are redacted too) and before the
    timestamp is added (so timestamps are never mistaken for sensitive digits).
    """
    structlog.configure(
        processors=[
            merge_contextvars,
            _ensure_correlation,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog_processor,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.WriteLoggerFactory(file=sink or sys.stdout),
        cache_logger_on_first_use=False,
    )


_ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz"


def new_run_id() -> str:
    """Random 128-bit ID spelled in letters only.

    Hex or decimal IDs contain digit runs that the account-number pattern would mask wherever
    the ID is embedded in text (evidence paths, messages). Letters-only IDs never collide with it.
    """
    n = uuid.uuid4().int
    chars = []
    while n:
        n, r = divmod(n, len(_ID_ALPHABET))
        chars.append(_ID_ALPHABET[r])
    return "run_" + "".join(chars)


@contextmanager
def run_context(
    run_id: str,
    *,
    artifact_ref: str | None = None,
    session_id: str | None = None,
    controller: str = "automation",
) -> Iterator[None]:
    with bound_contextvars(
        run_id=run_id, artifact_ref=artifact_ref, session_id=session_id, controller=controller
    ):
        yield


@contextmanager
def step_context(step_id: str) -> Iterator[None]:
    with bound_contextvars(step_id=step_id):
        yield


def get_logger() -> Any:
    return structlog.get_logger()


def emit(event: Event, **fields: Any) -> None:
    get_logger().info(event.value, **fields)
