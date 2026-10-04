"""Fixtures: an in-process MockBank server, one browser per session, a fresh page per test."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest
import uvicorn
from mockbank.app import create_app
from mockbank.faults import Faults, MockBankState
from playwright.async_api import Browser, async_playwright

from handrail.config import Settings
from handrail.surface.playwright_surface import PlaywrightSurface


@dataclass
class MockBank:
    url: str
    state: MockBankState

    def set(self, **faults: object) -> None:
        self.state.faults = Faults.model_validate({**self.state.faults.model_dump(), **faults})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def mockbank_server() -> Iterator[MockBank]:
    state = MockBankState()
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(state), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("MockBank did not start")
        time.sleep(0.05)
    yield MockBank(f"http://127.0.0.1:{port}", state)
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def mockbank(mockbank_server: MockBank) -> MockBank:
    mockbank_server.state.faults = Faults()
    mockbank_server.state.opened.clear()
    return mockbank_server


@pytest.fixture(scope="session")
async def browser() -> AsyncIterator[Browser]:
    settings = Settings()
    async with async_playwright() as pw:
        exe = str(settings.browser_executable) if settings.browser_executable else None
        b = await pw.chromium.launch(headless=True, executable_path=exe)
        yield b
        await b.close()


@pytest.fixture
async def surface(browser: Browser, mockbank: MockBank) -> AsyncIterator[PlaywrightSurface]:
    """A signed-in session on MockBank's member search page."""
    context = await browser.new_context()
    page = await context.new_page()
    page.set_default_timeout(5000)
    await page.goto(f"{mockbank.url}/login?next=/members/search")
    await page.locator("input[name=u]").fill("operator")
    await page.locator("input[name=p]").fill("mockbank-demo")
    await page.locator("input[type=submit]").click()
    await page.wait_for_url("**/members/search")
    yield PlaywrightSurface(page, mockbank.url)
    await context.close()
