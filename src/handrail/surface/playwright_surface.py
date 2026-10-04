"""Playwright implementation of ``Surface`` for modern and legacy (frameset, table) web apps.

Resolution walks the locator chain in order on every poll. The first strategy matching exactly
one element wins; a strategy matching several is a hard failure (never a guess); no match moves
on to the next strategy. Waiting is condition-based polling bounded by the step's timeout.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page, async_playwright

from handrail.schema.artifact import (
    Condition,
    CssLocator,
    Detector,
    LabelLocator,
    RoleDetector,
    RoleLocator,
    TableCellLocator,
    Target,
    TextDetector,
    TextLocator,
    UrlDetector,
)
from handrail.schema.artifact import Locator as Strategy
from handrail.surface.base import (
    FrameSnapshot,
    LocatorAmbiguous,
    LocatorNotFound,
    NotActionable,
    Resolution,
    Snapshot,
    SurfaceLost,
    describe,
)

POLL_SECONDS = 0.1
MASK_COLOR = "#FF00FF"
# Data-bearing elements masked in every screenshot unless the caller opts out.
DATA_SELECTOR = (
    "input:not([type=submit]):not([type=button]):not([type=hidden]):not([type=image]), "
    "select, textarea, td"
)
_CONTROLS = (
    "self::input[not(@type='hidden' or @type='submit' or @type='button' or @type='image')]"
    " or self::select or self::textarea"
)

_TABLE_CELL_JS = """
([rowKey, column, table]) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const xpath = el => {
    const parts = [];
    for (; el && el.nodeType === 1; el = el.parentNode) {
      let i = 1;
      for (let s = el.previousElementSibling; s; s = s.previousElementSibling)
        if (s.tagName === el.tagName) i++;
      parts.unshift(el.tagName.toLowerCase() + '[' + i + ']');
    }
    return '/' + parts.join('/');
  };
  const out = [];
  for (const t of document.querySelectorAll('table')) {
    if (table) {
      const name = norm(t.getAttribute('aria-label') || (t.caption && t.caption.textContent));
      if (name !== table) continue;
    }
    const rows = [...t.rows];
    if (!rows.length) continue;
    const header = rows.find(r => [...r.cells].some(c => c.tagName === 'TH')) || rows[0];
    const col = [...header.cells].findIndex(c => norm(c.textContent) === column);
    if (col < 0) continue;
    for (const r of rows) {
      if (r === header || r.cells.length <= col) continue;
      if (norm(r.cells[0].textContent) === rowKey) out.push(xpath(r.cells[col]));
    }
  }
  return out;
}
"""


def xpath_literal(text: str) -> str:
    """Quote arbitrary text for XPath 1.0, which has no escape character."""
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in text.split("'")) + ")"


class PlaywrightSurface:
    def __init__(self, page: Page, base_url: str) -> None:
        self._page = page
        self._base_url = base_url.rstrip("/")

    @property
    def page(self) -> Page:
        """The live page; the handoff controller gives this same session to a human."""
        return self._page

    # ------------------------------------------------------------------ frames

    def _frame(self, path: Sequence[str]) -> Frame | None:
        frame = self._page.main_frame
        for name in path:
            # After a navigation, detached frames can linger in child_frames; skip them.
            child = next(
                (c for c in frame.child_frames if c.name == name and not c.is_detached()), None
            )
            if child is None:
                return None
            frame = child
        return frame

    def _check_alive(self) -> None:
        if self._page.is_closed():
            raise SurfaceLost("the browser page is closed")

    # ------------------------------------------------------------------ locating

    async def _match(self, frame: Frame, strategy: Strategy) -> tuple[Locator | None, int]:
        match strategy:
            case RoleLocator():
                loc = frame.get_by_role(
                    cast(Any, strategy.role), name=strategy.name, exact=strategy.exact
                )
            case LabelLocator():
                loc = frame.get_by_label(strategy.label, exact=True).filter(visible=True)
                if await loc.count() == 0:
                    text = xpath_literal(strategy.label)
                    expr = (
                        f"//*[normalize-space(.)={text} and not(*[normalize-space(.)={text}])]"
                        f"/following::*[{_CONTROLS}][1]"
                    )
                    loc = frame.locator(f"xpath={expr}").filter(visible=True)
            case TableCellLocator():
                paths: list[str] = await frame.evaluate(
                    _TABLE_CELL_JS, [strategy.row_key, strategy.column, strategy.table]
                )
                if not paths:
                    return None, 0
                return frame.locator(f"xpath={paths[0]}"), len(paths)
            case TextLocator():
                loc = frame.get_by_text(strategy.text, exact=True).filter(visible=True)
            case CssLocator():
                loc = frame.locator(strategy.selector).filter(visible=True)
        return loc, await loc.count()

    async def _try_resolve(self, target: Target) -> tuple[Locator, Resolution] | None:
        frame = self._frame(target.frame)
        if frame is None:
            return None
        for i, strategy in enumerate(target.chain):
            try:
                loc, count = await self._match(frame, strategy)
            except PlaywrightError:
                return None  # frame navigating or detached; poll again
            if count > 1:
                raise LocatorAmbiguous(target, i, count)
            if count == 1 and loc is not None:
                return loc, Resolution(
                    strategy=i,
                    fallbacks=i,
                    description=describe(strategy),
                    brittle=isinstance(strategy, CssLocator),
                )
        return None

    async def _locate(self, target: Target, timeout_ms: int) -> tuple[Locator, Resolution, float]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        while True:
            self._check_alive()
            found = await self._try_resolve(target)
            if found is not None:
                return found[0], found[1], deadline
            if loop.time() >= deadline:
                raise LocatorNotFound(target, timeout_ms)
            await asyncio.sleep(POLL_SECONDS)

    async def _actionable(self, target: Target, timeout_ms: int) -> tuple[Locator, Resolution]:
        loc, res, deadline = await self._locate(target, timeout_ms)
        loop = asyncio.get_running_loop()
        while True:
            try:
                if await loc.is_enabled():
                    return loc, res
            except PlaywrightError:
                pass
            if loop.time() >= deadline:
                raise NotActionable(
                    f"element stayed disabled for {timeout_ms} ms ({res.description})",
                    target=target,
                )
            await asyncio.sleep(POLL_SECONDS)

    # ------------------------------------------------------------------ Surface API

    async def navigate(self, route: str) -> None:
        self._check_alive()
        await self._page.goto(self._base_url + route, wait_until="load")

    async def resolve(self, target: Target, *, timeout_ms: int) -> Resolution:
        _, res, _ = await self._locate(target, timeout_ms)
        return res

    async def click(self, target: Target, *, timeout_ms: int) -> Resolution:
        loc, res = await self._actionable(target, timeout_ms)
        try:
            await loc.click(timeout=timeout_ms)
        except PlaywrightError as exc:
            raise NotActionable(f"click failed: {exc.message}", target=target) from exc
        return res

    async def type_text(self, target: Target, text: str, *, timeout_ms: int) -> Resolution:
        loc, res = await self._actionable(target, timeout_ms)
        try:
            await loc.fill(text, timeout=timeout_ms)
        except PlaywrightError as exc:
            raise NotActionable(f"typing failed: {exc.message}", target=target) from exc
        return res

    async def select(self, target: Target, value: str, *, timeout_ms: int) -> Resolution:
        loc, res = await self._actionable(target, timeout_ms)
        try:
            await loc.select_option(label=value, timeout=timeout_ms)
        except PlaywrightError as exc:
            raise NotActionable(f"select failed: {exc.message}", target=target) from exc
        return res

    async def read_text(self, target: Target, *, timeout_ms: int) -> tuple[str, Resolution]:
        loc, res, _ = await self._locate(target, timeout_ms)
        tag = await loc.evaluate("el => el.tagName.toLowerCase()")
        text = (
            await loc.input_value()
            if tag in ("input", "textarea", "select")
            else (await loc.inner_text())
        )
        return " ".join(text.split()), res

    async def _detector(self, detector: Detector) -> bool:
        if isinstance(detector, UrlDetector):
            pattern = re.compile(detector.matches)
            return any(pattern.search(f.url) for f in self._page.frames)
        frame = self._frame(detector.frame)
        if frame is None:
            return False
        try:
            if isinstance(detector, RoleDetector):
                name: str | re.Pattern[str] | None = detector.name
                if name is None and detector.name_matches is not None:
                    name = re.compile(detector.name_matches)
                loc = frame.get_by_role(cast(Any, detector.role), name=name, exact=True)
            else:
                assert isinstance(detector, TextDetector)
                loc = frame.get_by_text(re.compile(detector.matches)).filter(visible=True)
            return await loc.count() > 0
        except PlaywrightError:
            return False

    async def holds(self, condition: Condition) -> bool:
        self._check_alive()
        for detector in condition.all_of:
            if not await self._detector(detector):
                return False
        if not condition.any_of:
            return True
        for detector in condition.any_of:
            if await self._detector(detector):
                return True
        return False

    async def wait_for_any(
        self, conditions: Mapping[str, Condition], *, timeout_ms: int
    ) -> str | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        while True:
            for name, condition in conditions.items():
                if await self.holds(condition):
                    return name
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(POLL_SECONDS)

    async def wait_until_clear(self, condition: Condition, *, timeout_ms: int) -> bool:
        """Wait for a condition to stop holding, e.g. a dismissed dialog to disappear."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        while await self.holds(condition):
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(POLL_SECONDS)
        return True

    async def snapshot(self) -> Snapshot:
        self._check_alive()
        frames: list[FrameSnapshot] = []

        async def walk(frame: Frame, path: tuple[str, ...]) -> None:
            try:
                aria = await frame.locator("body").aria_snapshot(timeout=2000)
            except PlaywrightError:
                aria = ""
            frames.append(FrameSnapshot(path=path, url=frame.url, aria=aria))
            for child in frame.child_frames:
                if not child.is_detached():
                    await walk(child, (*path, child.name or "?"))

        await walk(self._page.main_frame, ())
        return Snapshot(url=self._page.url, title=await self._page.title(), frames=tuple(frames))

    async def screenshot(self, *, mask: Sequence[Target] = (), mask_data: bool = True) -> bytes:
        """Full-page PNG with data-bearing elements painted over before capture."""
        self._check_alive()
        locators: list[Locator] = []
        if mask_data:
            locators.extend(f.locator(DATA_SELECTOR) for f in self._page.frames)
        for target in mask:
            found = await self._try_resolve(target)
            if found is not None:
                locators.append(found[0])
        return await self._page.screenshot(full_page=True, mask=locators, mask_color=MASK_COLOR)


@asynccontextmanager
async def open_surface(
    base_url: str,
    *,
    executable: Path | None = None,
    headless: bool = True,
) -> AsyncIterator[PlaywrightSurface]:
    """Launch a browser and yield a surface on a fresh page; closes everything on exit."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless, executable_path=str(executable) if executable else None
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()
            yield PlaywrightSurface(page, base_url)
        finally:
            await browser.close()
