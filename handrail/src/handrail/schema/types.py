"""Enumerations shared by the artifact and result contracts."""

from enum import StrEnum


class Sensitivity(StrEnum):
    """How a value must be treated in logs, evidence and model calls.

    Anything other than ``public`` is redacted wherever it appears.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"

    @property
    def redacted(self) -> bool:
        return self is not Sensitivity.PUBLIC


class RiskClass(StrEnum):
    """Risk of a step. Irreversible steps always need live human approval."""

    READ = "read"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    DEPRECATED = "deprecated"


class StepOrigin(StrEnum):
    """Who produced a step: a human author, the discovery agent, or an operator during handoff."""

    AUTHOR = "author"
    AGENT = "agent"
    HUMAN = "human"
