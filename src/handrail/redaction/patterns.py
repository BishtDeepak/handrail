"""Detectors for regulated data in free text.

Numeric patterns use digit lookarounds rather than ``\\b`` so values glued to letters
(``ssn123-45-6789``) are still caught. Checksums (Luhn, ABA) keep false positives down for the
specific labels; any remaining 8-17 digit run is masked as a possible account number.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


def luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def aba_ok(digits: str) -> bool:
    if len(digits) != 9 or not digits.isdigit():
        return False
    d = [int(c) for c in digits]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


@dataclass(frozen=True)
class PiiPattern:
    label: str
    regex: re.Pattern[str]
    check: Callable[[str], bool] | None = None


# Order matters: specific, checksummed patterns first; the generic account catch-all last.
PATTERNS: tuple[PiiPattern, ...] = (
    PiiPattern("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    PiiPattern("card", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), luhn_ok),
    PiiPattern("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    PiiPattern(
        "phone",
        re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\d)"),
    ),
    PiiPattern("routing", re.compile(r"(?<!\d)\d{9}(?!\d)"), aba_ok),
    PiiPattern("account", re.compile(r"(?<!\d)\d{8,17}(?!\d)")),
)

DOB_RE = re.compile(
    r"(?i)\b(dob|date of birth|birth\s?date)(\s*[:=]?\s*)(\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4})"
)

# Mapping keys whose values are always masked, whatever they contain.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set_cookie",
        "ssn",
        "dob",
        "date_of_birth",
        "birth_date",
        "card_number",
        "account_number",
        "routing_number",
    }
)
_SENSITIVE_SUFFIXES = ("_password", "_secret", "_api_key", "_token")


def is_sensitive_key(key: str) -> bool:
    k = key.lower().replace("-", "_")
    return k in SENSITIVE_KEYS or k.endswith(_SENSITIVE_SUFFIXES)
