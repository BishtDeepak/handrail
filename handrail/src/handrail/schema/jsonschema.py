"""Published JSON Schema documents, committed under /schema for reviewers and callers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from handrail.schema.artifact import SCHEMA_VERSION, Artifact
from handrail.schema.result import RunResult

_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def schema_documents() -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for filename, model in (
        ("artifact.schema.json", Artifact),
        ("run_result.schema.json", RunResult),
    ):
        schema = model.model_json_schema()
        docs[filename] = {"$schema": _DIALECT, "x-schema-version": SCHEMA_VERSION, **schema}
    return docs


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def write_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, doc in schema_documents().items():
        path = out_dir / name
        path.write_text(render(doc), encoding="utf-8")
        written.append(path)
    return written


def stale_schemas(out_dir: Path) -> list[str]:
    """Names of committed schema files that differ from the models."""
    stale = []
    for name, doc in schema_documents().items():
        path = out_dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != render(doc):
            stale.append(name)
    return stale
