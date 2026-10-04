"""NFR-07 (local half): no secrets committed. CI additionally runs gitleaks over history."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import ROOT

pytestmark = pytest.mark.unit

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
_SECRET_RE = re.compile(
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def _files() -> list[Path]:
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file() and not _SKIP_DIRS & set(p.relative_to(ROOT).parts) and p.name != ".env"
    ]


def test_nfr07_no_secret_shaped_strings() -> None:
    hits = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _SECRET_RE.search(text) and path.name != "test_repo_hygiene.py":
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_env_example_has_no_values() -> None:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        assert value in ("", "none"), f"{key} must be empty in .env.example"


def test_env_is_gitignored() -> None:
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
