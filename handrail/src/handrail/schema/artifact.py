"""The capability artifact: a typed, versioned, reviewable contract plus the steps that fulfil it.

A calling agent reads the contract half (``inputs``, ``outputs``, ``outcomes``); the replay
engine executes the flow half (``steps``, ``checkpoints``, ``recoveries``, ``success``).
Every model is frozen and forbids unknown fields, so a typo or a smuggled field (for example a
raw model transcript) is a load error rather than silently ignored data.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from handrail.schema.types import ArtifactStatus, RiskClass, Sensitivity, StepOrigin

SCHEMA_VERSION = "1.0"

IDENT_PATTERN = r"^[a-z][a-z0-9_]*$"
CODE_PATTERN = r"^[A-Z][A-Z0-9_]*$"
ARTIFACT_ID_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
EXPECT_REF_PATTERN = r"^(checkpoint:[a-z][a-z0-9_]*|outcome:[A-Z][A-Z0-9_]*)$"

PLACEHOLDER_RE = re.compile(r"\{\{\s*inputs\.([a-z][a-z0-9_]*)\s*\}\}")
ROUTE_PARAM_RE = re.compile(r":([a-z][a-z0-9_]*)")

Ident = Annotated[str, StringConstraints(pattern=IDENT_PATTERN)]
OutcomeCode = Annotated[str, StringConstraints(pattern=CODE_PATTERN)]
ValueType = Literal["string", "integer", "decimal", "boolean", "date"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_regex(value: str | None) -> str | None:
    if value is not None:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regular expression {value!r}: {exc}") from exc
    return value


# --------------------------------------------------------------------------------------------
# Locators: surface-neutral strategies, tried in chain order at replay time.
# --------------------------------------------------------------------------------------------


class RoleLocator(_Model):
    """Accessibility role plus accessible name. Most stable; maps onto desktop UIA/AX trees."""

    by: Literal["role"] = "role"
    role: str = Field(min_length=1)
    name: str = Field(min_length=1)
    exact: bool = True


class LabelLocator(_Model):
    """The control tied to (or next to) a text label. For unlabeled legacy forms."""

    by: Literal["label"] = "label"
    label: str = Field(min_length=1)


class TableCellLocator(_Model):
    """A cell addressed by row key and column header, independent of row order."""

    by: Literal["table_cell"] = "table_cell"
    row_key: str = Field(min_length=1)
    column: str = Field(min_length=1)
    table: str | None = None


class TextLocator(_Model):
    """An element found by its visible text."""

    by: Literal["text"] = "text"
    text: str = Field(min_length=1)


class CssLocator(_Model):
    """Last resort. Tied to markup; replay flags every use as brittle."""

    by: Literal["css"] = "css"
    selector: str = Field(min_length=1)


Locator = Annotated[
    RoleLocator | LabelLocator | TableCellLocator | TextLocator | CssLocator,
    Field(discriminator="by"),
]


class Target(_Model):
    """How to find one control.

    ``frame`` is a container path: frames on web, window or pane on desktop.
    """

    frame: list[str] = Field(default_factory=list)
    chain: list[Locator] = Field(min_length=1)
    recorded_match: int | None = Field(default=None, ge=0)
    rationale: str | None = None

    @model_validator(mode="after")
    def _recorded_match_in_chain(self) -> Target:
        if self.recorded_match is not None and self.recorded_match >= len(self.chain):
            raise ValueError("recorded_match points past the end of the locator chain")
        return self


# --------------------------------------------------------------------------------------------
# Detectors and conditions: assertions about page state (checkpoints, outcomes, recoveries).
# --------------------------------------------------------------------------------------------


class RoleDetector(_Model):
    kind: Literal["role"] = "role"
    frame: list[str] = Field(default_factory=list)
    role: str = Field(min_length=1)
    name: str | None = None
    name_matches: str | None = None

    _regex = field_validator("name_matches")(_check_regex)


class TextDetector(_Model):
    kind: Literal["text"] = "text"
    frame: list[str] = Field(default_factory=list)
    matches: str = Field(min_length=1)

    _regex = field_validator("matches")(_check_regex)


class UrlDetector(_Model):
    kind: Literal["url"] = "url"
    matches: str = Field(min_length=1)

    _regex = field_validator("matches")(_check_regex)


Detector = Annotated[RoleDetector | TextDetector | UrlDetector, Field(discriminator="kind")]


class Condition(_Model):
    all_of: list[Detector] = Field(default_factory=list)
    any_of: list[Detector] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_empty(self) -> Condition:
        if not self.all_of and not self.any_of:
            raise ValueError("a condition needs at least one detector in all_of or any_of")
        return self


# --------------------------------------------------------------------------------------------
# Contract: inputs, outputs, business outcomes.
# --------------------------------------------------------------------------------------------


class InputParam(_Model):
    type: ValueType
    sensitivity: Sensitivity
    pattern: str | None = None
    required: bool = True
    description: str | None = None

    _regex = field_validator("pattern")(_check_regex)


class OutputSpec(_Model):
    type: ValueType
    sensitivity: Sensitivity
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    description: str | None = None


class OutcomeSpec(_Model):
    """A legitimate business result the caller must handle, e.g. MEMBER_NOT_FOUND."""

    kind: Literal["business"] = "business"
    detect: Condition
    message: str = Field(min_length=1)
    extract: dict[Ident, Target] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Recoveries: known interstitials and transient states.
# --------------------------------------------------------------------------------------------


class ClickRecovery(_Model):
    do: Literal["click"] = "click"
    target: Target


class WaitRecovery(_Model):
    do: Literal["wait"] = "wait"
    ms: int = Field(gt=0, le=60_000)


class ReloadRecovery(_Model):
    do: Literal["reload"] = "reload"


RecoveryAction = Annotated[ClickRecovery | WaitRecovery | ReloadRecovery, Field(discriminator="do")]


class Recovery(_Model):
    id: Ident
    detect: Condition
    action: RecoveryAction
    max_attempts: int = Field(default=1, ge=1, le=5)
    retry_step: bool = True


# --------------------------------------------------------------------------------------------
# Steps.
# --------------------------------------------------------------------------------------------


class Expect(_Model):
    """What must hold after a step. References are ``checkpoint:<name>`` or ``outcome:<CODE>``."""

    any_of: list[Annotated[str, StringConstraints(pattern=EXPECT_REF_PATTERN)]] = Field(
        min_length=1
    )
    timeout_ms: int = Field(default=10_000, gt=0, le=120_000)


class _StepBase(_Model):
    id: Ident
    risk: RiskClass
    expect: Expect | None = None
    origin: StepOrigin = StepOrigin.AGENT
    description: str | None = None


class NavigateStep(_StepBase):
    """Navigate to a canonical route such as ``/member/:member_id``; ``bind`` fills parameters."""

    action: Literal["navigate"] = "navigate"
    route: str = Field(pattern=r"^/")
    bind: dict[Ident, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _params_bound(self) -> NavigateStep:
        params = set(ROUTE_PARAM_RE.findall(self.route))
        if params != set(self.bind):
            raise ValueError(
                f"route parameters {sorted(params)} must match bind keys {sorted(self.bind)}"
            )
        return self


class TypeStep(_StepBase):
    action: Literal["type"] = "type"
    target: Target
    value: str


class SelectStep(_StepBase):
    action: Literal["select"] = "select"
    target: Target
    value: str


class ClickStep(_StepBase):
    action: Literal["click"] = "click"
    target: Target


class ExtractStep(_StepBase):
    action: Literal["extract"] = "extract"
    target: Target
    output: Ident
    parse: Literal["text", "currency", "integer", "date"] = "text"


class AssertStep(_StepBase):
    action: Literal["assert"] = "assert"
    checkpoint: Ident


Step = Annotated[
    NavigateStep | TypeStep | SelectStep | ClickStep | ExtractStep | AssertStep,
    Field(discriminator="action"),
]


# --------------------------------------------------------------------------------------------
# Metadata.
# --------------------------------------------------------------------------------------------


class AppRef(_Model):
    product: Ident
    product_version: str = Field(description="PEP 440 specifier, e.g. '>=3.1,<4'")

    @field_validator("product_version")
    @classmethod
    def _valid_specifier(cls, value: str) -> str:
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError(f"invalid version specifier {value!r}") from exc
        return value


class SuccessSpec(_Model):
    checkpoint: Ident
    outputs_present: list[Ident] = Field(default_factory=list)


class Triage(_Model):
    """Opt-in, bounded judge triage for unknown states. Only allowed on approved artifacts."""

    enabled: bool = False
    allowed_recoveries: list[Ident] = Field(default_factory=list)
    threshold: float = Field(default=0.85, ge=0.5, le=1.0)


class Provenance(_Model):
    created_by: Literal["discovery", "author"]
    created_at: datetime
    discovery_run_id: str | None = None
    planner_model: str | None = None
    judge_model: str | None = None
    reviewed_by: str | None = None
    approved_at: datetime | None = None


# --------------------------------------------------------------------------------------------
# The artifact.
# --------------------------------------------------------------------------------------------


class Artifact(_Model):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    status: ArtifactStatus
    description: str = Field(min_length=1)
    app: AppRef
    inputs: dict[Ident, InputParam] = Field(default_factory=dict)
    outputs: dict[Ident, OutputSpec] = Field(default_factory=dict)
    outcomes: dict[OutcomeCode, OutcomeSpec] = Field(default_factory=dict)
    recoveries: list[Recovery] = Field(default_factory=list)
    steps: list[Step] = Field(min_length=1)
    checkpoints: dict[Ident, Condition] = Field(default_factory=dict)
    success: SuccessSpec
    triage: Triage = Field(default_factory=Triage)
    provenance: Provenance
    superseded_by: str | None = Field(default=None, pattern=SEMVER_PATTERN)
    content_hash: str | None = Field(default=None, pattern=HASH_PATTERN)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @model_validator(mode="after")
    def _consistent(self) -> Artifact:
        errors: list[str] = []

        step_ids = [s.id for s in self.steps]
        dupes = sorted({i for i in step_ids if step_ids.count(i) > 1})
        if dupes:
            errors.append(f"duplicate step ids: {dupes}")
        recovery_ids = [r.id for r in self.recoveries]
        if len(set(recovery_ids)) != len(recovery_ids):
            errors.append("duplicate recovery ids")

        def check_ref(ref: str, where: str) -> None:
            kind, _, name = ref.partition(":")
            pool = self.checkpoints if kind == "checkpoint" else self.outcomes
            if name not in pool:
                errors.append(f"{where}: unknown {kind} {name!r}")

        extracted: set[str] = set()
        for step in self.steps:
            if step.expect is not None:
                for ref in step.expect.any_of:
                    check_ref(ref, f"step {step.id}")
            templates: list[str] = []
            if isinstance(step, TypeStep | SelectStep):
                templates.append(step.value)
            elif isinstance(step, NavigateStep):
                templates.extend(step.bind.values())
            elif isinstance(step, ExtractStep):
                if step.output not in self.outputs:
                    errors.append(f"step {step.id}: extracts undeclared output {step.output!r}")
                extracted.add(step.output)
            elif isinstance(step, AssertStep) and step.checkpoint not in self.checkpoints:
                errors.append(f"step {step.id}: unknown checkpoint {step.checkpoint!r}")
            for template in templates:
                for name in PLACEHOLDER_RE.findall(template):
                    if name not in self.inputs:
                        errors.append(f"step {step.id}: placeholder uses undeclared input {name!r}")

        for name in sorted(set(self.outputs) - extracted):
            errors.append(f"output {name!r} is declared but never extracted")
        if self.success.checkpoint not in self.checkpoints:
            errors.append(f"success: unknown checkpoint {self.success.checkpoint!r}")
        for name in self.success.outputs_present:
            if name not in self.outputs:
                errors.append(f"success: unknown output {name!r}")
        for rid in self.triage.allowed_recoveries:
            if rid not in recovery_ids:
                errors.append(f"triage: unknown recovery {rid!r}")

        if self.status is ArtifactStatus.APPROVED and self.content_hash is None:
            errors.append("approved artifacts must carry a content_hash")
        if self.status is ArtifactStatus.DEPRECATED and self.superseded_by is None:
            errors.append("deprecated artifacts must name superseded_by")

        if errors:
            raise ValueError("; ".join(errors))
        return self
