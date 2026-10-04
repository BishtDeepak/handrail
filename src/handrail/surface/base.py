"""The seam between "how we perceive and act on a surface" and "the recorded flow".

Artifacts describe *what* to target in surface-neutral terms (role, label, table cell, text,
container path). A ``Surface`` decides *how* to find it: Playwright for web, UI Automation for
desktop, OCR for surfaces with no usable tree. The replay engine only ever sees this Protocol.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from handrail.schema.artifact import (
    Condition,
    CssLocator,
    LabelLocator,
    Locator,
    RoleLocator,
    TableCellLocator,
    Target,
    TextLocator,
)
from handrail.schema.result import FailureKind


def describe(locator: Locator) -> str:
    """Human-readable form of one strategy, used in logs and failure reports."""
    match locator:
        case RoleLocator():
            return f'role={locator.role} name="{locator.name}"'
        case LabelLocator():
            return f'label="{locator.label}"'
        case TableCellLocator():
            return f'table_cell row="{locator.row_key}" column="{locator.column}"'
        case TextLocator():
            return f'text="{locator.text}"'
        case CssLocator():
            return f"css={locator.selector}"


def describe_target(target: Target) -> str:
    where = "/".join(target.frame) or "top"
    return f"[{where}] " + " -> ".join(describe(loc) for loc in target.chain)


class SurfaceError(Exception):
    """A surface-level problem, already classified for the result contract."""

    kind: FailureKind = FailureKind.APP_ERROR

    def __init__(self, message: str, *, target: Target | None = None) -> None:
        super().__init__(message)
        self.target = target


class LocatorNotFound(SurfaceError):
    kind = FailureKind.LOCATOR_NOT_FOUND

    def __init__(self, target: Target, timeout_ms: int) -> None:
        super().__init__(
            f"no strategy matched within {timeout_ms} ms: {describe_target(target)}", target=target
        )
        self.trail = [describe(loc) for loc in target.chain]


class LocatorAmbiguous(SurfaceError):
    kind = FailureKind.LOCATOR_AMBIGUOUS

    def __init__(self, target: Target, strategy: int, count: int) -> None:
        super().__init__(
            f"strategy {strategy} ({describe(target.chain[strategy])}) matched {count} elements; "
            "refusing to guess",
            target=target,
        )
        self.strategy = strategy
        self.count = count


class NotActionable(SurfaceError):
    kind = FailureKind.NOT_ACTIONABLE


class SurfaceLost(SurfaceError):
    kind = FailureKind.SURFACE_LOST


@dataclass(frozen=True)
class Resolution:
    """Which strategy in the chain matched. ``fallbacks > 0`` is the drift signal."""

    strategy: int
    fallbacks: int
    description: str
    brittle: bool = False


@dataclass(frozen=True)
class FrameSnapshot:
    path: tuple[str, ...]
    url: str
    aria: str


@dataclass(frozen=True)
class Snapshot:
    url: str
    title: str
    frames: tuple[FrameSnapshot, ...] = field(default_factory=tuple)

    @property
    def state_hash(self) -> str:
        """Stable fingerprint of what is on screen, for repeated-state (stuck) detection."""
        digest = hashlib.sha256()
        for frame in self.frames:
            digest.update("/".join(frame.path).encode())
            digest.update(b"\0")
            digest.update(frame.aria.encode())
            digest.update(b"\0")
        return digest.hexdigest()

    def text(self) -> str:
        """All frames as one document, for logs and (redacted) model input."""
        parts = []
        for frame in self.frames:
            parts.append(f"# frame: {'/'.join(frame.path) or 'top'}  ({frame.url})")
            parts.append(frame.aria)
        return "\n".join(parts)


class Surface(Protocol):
    async def navigate(self, route: str) -> None: ...

    async def snapshot(self) -> Snapshot: ...

    async def resolve(self, target: Target, *, timeout_ms: int) -> Resolution: ...

    async def click(self, target: Target, *, timeout_ms: int) -> Resolution: ...

    async def type_text(self, target: Target, text: str, *, timeout_ms: int) -> Resolution: ...

    async def select(self, target: Target, value: str, *, timeout_ms: int) -> Resolution: ...

    async def read_text(self, target: Target, *, timeout_ms: int) -> tuple[str, Resolution]: ...

    async def holds(self, condition: Condition) -> bool: ...

    async def wait_for_any(
        self, conditions: Mapping[str, Condition], *, timeout_ms: int
    ) -> str | None: ...

    async def wait_until_clear(self, condition: Condition, *, timeout_ms: int) -> bool: ...

    async def screenshot(self, *, mask: Sequence[Target] = (), mask_data: bool = True) -> bytes: ...
