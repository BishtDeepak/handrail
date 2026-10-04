"""Loading, saving, hashing and lifecycle checks for artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from handrail.schema.artifact import Artifact
from handrail.schema.types import ArtifactStatus

# Lifecycle and review metadata are excluded from the hash: approving or deprecating an
# artifact must not change its identity. Everything that affects behaviour is covered.
_HASH_EXCLUDE = {"content_hash", "status", "superseded_by", "provenance"}


class ArtifactError(Exception):
    """Base class for artifact problems."""


class ArtifactInvalid(ArtifactError):
    """The file does not satisfy the schema."""


class ArtifactIntegrityError(ArtifactError):
    """The content no longer matches its recorded hash."""


class ArtifactNotRunnable(ArtifactError):
    """The artifact's lifecycle state forbids running it."""


def compute_hash(artifact: Artifact) -> str:
    payload = artifact.model_dump(mode="json", exclude=_HASH_EXCLUDE)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_artifact(data: str | bytes | dict[str, Any]) -> Artifact:
    """Validate and integrity-check an artifact from JSON text or a decoded mapping."""
    try:
        if isinstance(data, dict):
            artifact = Artifact.model_validate(data)
        else:
            artifact = Artifact.model_validate_json(data)
    except ValidationError as exc:
        raise ArtifactInvalid(str(exc)) from exc
    if artifact.content_hash is not None:
        actual = compute_hash(artifact)
        if actual != artifact.content_hash:
            raise ArtifactIntegrityError(
                f"{artifact.ref}: content changed since it was hashed "
                f"(recorded {artifact.content_hash}, actual {actual}); bump the version"
            )
    return artifact


def load_artifact(path: Path) -> Artifact:
    return parse_artifact(path.read_bytes())


def dump_artifact(artifact: Artifact) -> str:
    return artifact.model_dump_json(indent=2, exclude_none=True) + "\n"


def save_artifact(artifact: Artifact, root: Path) -> Path:
    """Write to ``<root>/<id>/<version>.json``. Approved versions are never overwritten."""
    path = root / artifact.id / f"{artifact.version}.json"
    if path.exists():
        existing = load_artifact(path)
        if existing.status is ArtifactStatus.APPROVED and existing.content_hash != compute_hash(
            artifact
        ):
            raise ArtifactIntegrityError(f"{artifact.ref} is approved; publish a new version")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_artifact(artifact), encoding="utf-8")
    return path


def approve(artifact: Artifact, *, reviewer: str, at: datetime) -> Artifact:
    """Return the approved form of a draft: status, reviewer, time and content hash set."""
    if artifact.status is not ArtifactStatus.DRAFT:
        raise ArtifactNotRunnable(
            f"only drafts can be approved; {artifact.ref} is {artifact.status}"
        )
    data = artifact.model_dump(mode="json")
    data["status"] = ArtifactStatus.APPROVED.value
    data["provenance"]["reviewed_by"] = reviewer
    data["provenance"]["approved_at"] = at.isoformat()
    data["content_hash"] = compute_hash(artifact)
    return parse_artifact(data)


def ensure_runnable(artifact: Artifact, *, allow_draft: bool = False) -> None:
    """Gate unattended execution on lifecycle state."""
    if artifact.status is ArtifactStatus.DEPRECATED:
        raise ArtifactNotRunnable(
            f"{artifact.ref} is deprecated; use {artifact.id}@{artifact.superseded_by}"
        )
    if artifact.status is ArtifactStatus.DRAFT and not allow_draft:
        raise ArtifactNotRunnable(f"{artifact.ref} is a draft; approve it or pass allow_draft")
