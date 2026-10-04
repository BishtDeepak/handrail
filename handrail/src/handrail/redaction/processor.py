"""The single redaction choke point for logs, evidence and outbound model payloads.

Three layers, applied in order:

1. **Registered values** - the exact runtime values of every non-public input or output,
   registered per run through :func:`sensitive_values`. Catches short IDs no pattern would.
2. **Sensitive keys** - mapping keys such as ``password`` or ``ssn`` mask their whole value.
3. **Patterns** - SSNs, cards, routing/account numbers, emails, phones, dates of birth.

Registered values live in a ``ContextVar`` so concurrent runs on one event loop stay isolated.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import quote, quote_plus

from pydantic import BaseModel, SecretBytes, SecretStr

from handrail.redaction.patterns import DOB_RE, PATTERNS, is_sensitive_key
from handrail.schema.types import Sensitivity

MIN_REGISTERED_LENGTH = 3

_registered: ContextVar[tuple[tuple[str, str], ...]] = ContextVar(
    "handrail_sensitive_values", default=()
)


def mask(label: str) -> str:
    return f"[REDACTED:{label}]"


class _HasSensitivity(Protocol):
    @property
    def sensitivity(self) -> Sensitivity: ...


@contextmanager
def sensitive_values(values: Mapping[str, object]) -> Iterator[None]:
    """Register ``{label: value}`` pairs for the duration of the block."""
    extra = tuple(
        (label, str(value))
        for label, value in values.items()
        if value is not None and len(str(value)) >= MIN_REGISTERED_LENGTH
    )
    token = _registered.set(_registered.get() + extra)
    try:
        yield
    finally:
        _registered.reset(token)


def labelled_values(
    specs: Mapping[str, _HasSensitivity], values: Mapping[str, object], *, prefix: str
) -> dict[str, object]:
    """Pick the values whose declared sensitivity requires redaction."""
    return {
        f"{prefix}:{name}": value
        for name, value in values.items()
        if name in specs and specs[name].sensitivity.redacted
    }


def _registered_patterns() -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    # Longest first so a value containing another value is masked whole.
    for label, value in sorted(_registered.get(), key=lambda p: -len(p[1])):
        forms = {value, quote(value, safe=""), quote_plus(value)}
        alternation = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
        out.append((label, re.compile(rf"(?<![0-9A-Za-z])(?:{alternation})(?![0-9A-Za-z])")))
    return out


def redact_text(text: str) -> str:
    for label, pattern in _registered_patterns():
        text = pattern.sub(mask(label), text)
    text = DOB_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{mask('dob')}", text)
    for p in PATTERNS:
        check = p.check

        def repl(m: re.Match[str], label: str = p.label, check: Any = check) -> str:
            if check is None or check(m.group(0)):
                return mask(label)
            return m.group(0)

        text = p.regex.sub(repl, text)
    return text


def redact(value: Any, *, key: str | None = None) -> Any:
    """Return a redacted copy of ``value``. Containers are walked; keys are preserved."""
    if key is not None and is_sensitive_key(key) and value is not None:
        return mask(key.lower())
    if isinstance(value, SecretStr | SecretBytes):
        return mask("secret")
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | Decimal):
        text = str(value)
        redacted = redact_text(text)
        return value if redacted == text else redacted
    if isinstance(value, float | datetime | date):
        return value
    if isinstance(value, BaseModel):
        return redact(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {k: redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v) for v in value]
    if isinstance(value, BaseException):
        return redact_text(f"{type(value).__name__}: {value}")
    return redact_text(repr(value))


# System-generated fields that never carry user data; redacting them would break correlation.
_SYSTEM_KEYS = frozenset(
    {"event", "level", "run_id", "step_id", "artifact_ref", "session_id", "controller"}
)


def structlog_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: redact every field of every event before it is rendered."""
    return {k: v if k in _SYSTEM_KEYS else redact(v, key=k) for k, v in event_dict.items()}
