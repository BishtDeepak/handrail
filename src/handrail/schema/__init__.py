"""Artifact and result contracts."""

from handrail.schema.artifact import SCHEMA_VERSION, Artifact
from handrail.schema.io import (
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactInvalid,
    ArtifactNotRunnable,
    approve,
    compute_hash,
    ensure_runnable,
    load_artifact,
    parse_artifact,
    save_artifact,
)
from handrail.schema.result import RunResult
from handrail.schema.types import ArtifactStatus, RiskClass, Sensitivity, StepOrigin

__all__ = [
    "SCHEMA_VERSION",
    "Artifact",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactInvalid",
    "ArtifactNotRunnable",
    "ArtifactStatus",
    "RiskClass",
    "RunResult",
    "Sensitivity",
    "StepOrigin",
    "approve",
    "compute_hash",
    "ensure_runnable",
    "load_artifact",
    "parse_artifact",
    "save_artifact",
]
