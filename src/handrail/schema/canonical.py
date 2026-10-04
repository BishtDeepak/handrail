"""Canonicalization of concrete routes and values into parameterized patterns.

Discovery records ``/member/12345``; the artifact stores ``/member/:member_id`` with
``bind = {"member_id": "{{inputs.member_id}}"}`` so no tenant or member data is baked in.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import quote

from handrail.schema.artifact import PLACEHOLDER_RE, ROUTE_PARAM_RE


class TemplateError(ValueError):
    """A placeholder or route parameter could not be resolved."""


def canonicalize_route(path: str, input_values: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Replace path segments equal to an input's value with ``:<input name>``."""
    by_value: dict[str, list[str]] = {}
    for name, value in input_values.items():
        if value:
            by_value.setdefault(value, []).append(name)
    segments: list[str] = []
    bind: dict[str, str] = {}
    for segment in path.split("/"):
        names = by_value.get(segment, [])
        if len(names) > 1:
            raise TemplateError(f"segment {segment!r} matches several inputs: {sorted(names)}")
        if names:
            segments.append(f":{names[0]}")
            bind[names[0]] = f"{{{{inputs.{names[0]}}}}}"
        else:
            segments.append(segment)
    return "/".join(segments), bind


def render_template(template: str, inputs: Mapping[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in inputs:
            raise TemplateError(f"no value for input {name!r}")
        return inputs[name]

    return PLACEHOLDER_RE.sub(sub, template)


def render_route(route: str, bind: Mapping[str, str], inputs: Mapping[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in bind:
            raise TemplateError(f"route parameter {name!r} is not bound")
        return quote(render_template(bind[name], inputs), safe="")

    return ROUTE_PARAM_RE.sub(sub, route)
