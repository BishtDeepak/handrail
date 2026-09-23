"""The replay/discovery result contract returned to the caller.

The outcome is a closed, discriminated union. The caller can always tell a legitimate business
answer (``business_outcome``) from a failure that needs debugging (``hard_failure``).
Recoverable conditions never appear here; they are handled inside the engine and logged.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

OutputValue = str | int | Decimal | bool | date


class FailureKind(StrEnum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    LOCATOR_AMBIGUOUS = "locator_ambiguous"
    NOT_ACTIONABLE = "not_actionable"
    CHECKPOINT_MISMATCH = "checkpoint_mismatch"
    OUTPUT_MISSING = "output_missing"
    OUTPUT_PARSE = "output_parse"
    APP_ERROR = "app_error"
    TIMEOUT = "timeout"
    RECOVERY_EXHAUSTED = "recovery_exhausted"
    POLICY_VIOLATION = "policy_violation"
    VERSION_MISMATCH = "version_mismatch"
    SURFACE_LOST = "surface_lost"
    TARGET_UNREACHABLE = "target_unreachable"
    INVALID_ARTIFACT = "invalid_artifact"


class EscalationReason(StrEnum):
    STUCK = "stuck"
    IRREVERSIBLE_STEP = "irreversible_step"
    UNKNOWN_STATE = "unknown_state"
    SESSION_EXPIRED = "session_expired"
    MODEL_DISAGREEMENT = "model_disagreement"
    JUDGE_UNAVAILABLE = "judge_unavailable"
    LOW_CONFIDENCE = "low_confidence"


class BuiltinOutcome(StrEnum):
    """Business outcomes every artifact can return without declaring them."""

    INVALID_INPUT = "INVALID_INPUT"
    APPROVAL_DENIED = "APPROVAL_DENIED"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Success(_Model):
    status: Literal["success"] = "success"
    outputs: dict[str, OutputValue] = Field(default_factory=dict)


class BusinessOutcome(_Model):
    status: Literal["business_outcome"] = "business_outcome"
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str
    fields: dict[str, str] = Field(default_factory=dict)


class HardFailure(_Model):
    """Stop and surface a debuggable error: which step, what was expected, what was observed."""

    status: Literal["hard_failure"] = "hard_failure"
    kind: FailureKind
    step_id: str | None
    expected: str
    observed: str
    evidence: list[str] = Field(default_factory=list)


class NeedsHuman(_Model):
    status: Literal["needs_human"] = "needs_human"
    reason: EscalationReason
    step_id: str | None
    request_id: str


class Aborted(_Model):
    status: Literal["aborted"] = "aborted"
    reason: str
    step_id: str | None = None


Outcome = Annotated[
    Success | BusinessOutcome | HardFailure | NeedsHuman | Aborted,
    Field(discriminator="status"),
]


class StepRecord(_Model):
    step_id: str
    started_at: datetime
    duration_ms: int = Field(ge=0)
    locator_strategy: int | None = None
    fallbacks: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    result: Literal["ok", "recovered", "outcome", "failed", "escalated"]


class RunResult(_Model):
    run_id: str
    mode: Literal["discovery", "replay"]
    artifact_ref: str | None = None
    outcome: Outcome
    steps: list[StepRecord] = Field(default_factory=list)
    recoveries_applied: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
