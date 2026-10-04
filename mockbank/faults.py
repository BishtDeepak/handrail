"""Switchable runtime conditions, one per test scenario. Settable over HTTP or by hand."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_VERSION = "3.4.2"


class Faults(BaseModel):
    """All switches default to the happy path."""

    model_config = ConfigDict(extra="forbid")

    notice_dialog: int = Field(0, ge=0, description="Show the 'System Notice' interstitial N times")
    unknown_dialog: bool = Field(
        False, description="Show an undeclared 'Maintenance Window' dialog"
    )
    slow_detail_ms: int = Field(0, ge=0, le=60_000, description="Delay the member detail page")
    transient_503: int = Field(0, ge=0, description="Fail the next N detail requests with 503")
    http_500_detail: bool = Field(False, description="Member detail returns HTTP 500")
    blank_main: bool = Field(False, description="Main frame pages render an empty body")
    rename_search: str | None = Field(None, description="Rename the Search button (drift)")
    wrong_landing: bool = Field(False, description="Search lands on Home instead of detail")
    permission_denied_all: bool = Field(False, description="Every member lookup is denied")
    duplicate_search: bool = Field(False, description="Two buttons named Search in main")
    nav_search_button: bool = Field(False, description="A Search button also in the nav frame")
    reorder_rows: bool = Field(False, description="Reverse the share table row order")
    disabled_search: bool = Field(False, description="Search button stays disabled")
    late_render_ms: int = Field(0, ge=0, le=60_000, description="Render the search form late")
    hostile_content: bool = Field(False, description="Off-allowlist links and injected text")
    version: str = Field(DEFAULT_VERSION, description="Version string in every footer")


@dataclass
class OpenedAccount:
    member_id: str
    share_type: str
    deposit: str
    confirmation: str


@dataclass
class MockBankState:
    faults: Faults = field(default_factory=Faults)
    sessions: set[str] = field(default_factory=set)
    opened: list[OpenedAccount] = field(default_factory=list)

    def reset(self) -> None:
        self.faults = Faults()
        self.sessions.clear()
        self.opened.clear()

    def new_session(self) -> str:
        token = secrets.token_urlsafe(24)
        self.sessions.add(token)
        return token

    def expire_sessions(self) -> None:
        self.sessions.clear()

    def take_notice(self) -> bool:
        if self.faults.notice_dialog > 0:
            self.faults.notice_dialog -= 1
            return True
        return False

    def take_503(self) -> bool:
        if self.faults.transient_503 > 0:
            self.faults.transient_503 -= 1
            return True
        return False
