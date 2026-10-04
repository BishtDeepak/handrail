"""SCH-14: concrete routes become parameterized patterns and render back."""

from __future__ import annotations

import pytest

from handrail.schema.canonical import (
    TemplateError,
    canonicalize_route,
    render_route,
    render_template,
)

pytestmark = pytest.mark.unit


def test_sch14_route_canonicalization() -> None:
    route, bind = canonicalize_route("/member/12345/shares", {"member_id": "12345"})
    assert route == "/member/:member_id/shares"
    assert bind == {"member_id": "{{inputs.member_id}}"}


def test_render_route_round_trip() -> None:
    route, bind = canonicalize_route("/member/12345", {"member_id": "12345"})
    assert render_route(route, bind, {"member_id": "67890"}) == "/member/67890"


def test_render_route_escapes_values() -> None:
    assert (
        render_route("/q/:term", {"term": "{{inputs.term}}"}, {"term": "a/b c"}) == "/q/a%2Fb%20c"
    )


def test_ambiguous_segment_rejected() -> None:
    with pytest.raises(TemplateError, match="several inputs"):
        canonicalize_route("/x/7777", {"a": "7777", "b": "7777"})


def test_missing_input_rejected() -> None:
    with pytest.raises(TemplateError, match="member_id"):
        render_template("{{inputs.member_id}}", {})
