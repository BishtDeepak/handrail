"""SCH-03: the committed JSON Schema matches the models."""

from __future__ import annotations

import pytest

from handrail.schema.jsonschema import schema_documents, stale_schemas
from tests.conftest import ROOT

pytestmark = pytest.mark.unit


def test_sch03_committed_schema_is_current() -> None:
    assert stale_schemas(ROOT / "schema") == [], "run 'handrail schema export'"


def test_schema_documents_are_self_describing() -> None:
    docs = schema_documents()
    assert set(docs) == {"artifact.schema.json", "run_result.schema.json"}
    for doc in docs.values():
        assert doc["$schema"].endswith("2020-12/schema")
        assert doc["x-schema-version"] == "1.0"
