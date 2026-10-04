"""Phase 2 exit: every fault switch is reachable and changes what the app renders."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from mockbank.app import create_app
from mockbank.faults import MockBankState
from mockbank.seed import CANARIES, MEMBERS

pytestmark = pytest.mark.integration


@pytest.fixture
def state() -> MockBankState:
    return MockBankState()


@pytest.fixture
def client(state: MockBankState) -> Iterator[TestClient]:
    with TestClient(create_app(state)) as c:
        r = c.post("/login", data={"u": "operator", "p": "mockbank-demo", "next": "/"})
        assert r.status_code == 200
        yield c


def _search(client: TestClient, mid: str) -> str:
    text: str = client.get("/frame/members/search", params={"mid": mid}).text
    return text


def test_login_required(state: MockBankState) -> None:
    with TestClient(create_app(state)) as c:
        r = c.get("/members/search", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login")
        assert "Session Expired" in c.get("/frame/members/search").text


def test_bad_credentials(state: MockBankState) -> None:
    with TestClient(create_app(state)) as c:
        r = c.post("/login", data={"u": "operator", "p": "wrong"})
        assert r.status_code == 401


def test_deep_link_is_frameset(client: TestClient) -> None:
    html = client.get("/members/search").text
    assert '<frame name="main" src="/frame/members/search">' in html
    assert '<frame name="nav"' in html


def test_happy_path_and_canaries_render(client: TestClient) -> None:
    r = client.get("/frame/members/search", params={"mid": "48213"})
    assert r.url.path == "/frame/members/48213"
    for value in (m := MEMBERS["48213"]).name, m.ssn, m.email, m.card:
        assert value in r.text
    assert "$8,812.40" in r.text
    assert set(CANARIES) >= {m.ssn, m.dob, m.phone, m.address}


def test_legacy_markup_has_no_test_ids_or_labels(client: TestClient) -> None:
    html = client.get("/frame/members/search").text
    assert "data-testid" not in html
    assert "<label" not in html
    assert ' id="' not in html


@pytest.mark.parametrize(
    ("mid", "expected"),
    [
        ("99999", "No member found"),
        ("12a45", "Validation error: Member ID must be 5 digits"),
        ("00000", "reserved"),
        ("51007", "Access denied"),
    ],
)
def test_business_outcomes(client: TestClient, mid: str, expected: str) -> None:
    assert expected in _search(client, mid)


def test_fault_permission_denied_all(client: TestClient, state: MockBankState) -> None:
    state.faults.permission_denied_all = True
    assert "Access denied" in _search(client, "48213")


def test_fault_notice_dialog_counts_down(client: TestClient, state: MockBankState) -> None:
    state.faults.notice_dialog = 2
    page = client.get("/frame/members/search").text
    assert 'aria-label="System Notice"' in page
    assert 'aria-label="System Notice"' in client.get("/frame/members/search").text
    assert 'aria-label="System Notice"' not in client.get("/frame/members/search").text


def test_fault_unknown_dialog_and_ack(client: TestClient, state: MockBankState) -> None:
    state.faults.unknown_dialog = True
    assert 'aria-label="Maintenance Window"' in client.get("/frame/members/search").text
    client.get("/frame/members/search", params={"ack": "maint"})
    assert state.faults.unknown_dialog is False


def test_fault_transient_503(client: TestClient, state: MockBankState) -> None:
    state.faults.transient_503 = 1
    assert client.get("/frame/members/48213").status_code == 503
    assert client.get("/frame/members/48213").status_code == 200


def test_fault_http_500(client: TestClient, state: MockBankState) -> None:
    state.faults.http_500_detail = True
    assert client.get("/frame/members/48213").status_code == 500


def test_fault_blank_main(client: TestClient, state: MockBankState) -> None:
    state.faults.blank_main = True
    assert "<body></body>" in client.get("/frame/members/search").text


def test_fault_rename_and_disable_and_duplicate(client: TestClient, state: MockBankState) -> None:
    state.faults.rename_search = "Find"
    state.faults.disabled_search = True
    state.faults.duplicate_search = True
    html = client.get("/frame/members/search").text
    assert 'value="Find" disabled' in html
    assert html.count('value="Find"') == 2


def test_fault_wrong_landing(client: TestClient, state: MockBankState) -> None:
    state.faults.wrong_landing = True
    r = client.get("/frame/members/search", params={"mid": "48213"})
    assert r.url.path == "/frame/home"


def test_fault_reorder_rows(client: TestClient, state: MockBankState) -> None:
    normal = client.get("/frame/members/48213").text
    state.faults.reorder_rows = True
    reordered = client.get("/frame/members/48213").text
    assert normal.index("Savings</td>") < normal.index("Holiday Club</td>")
    assert reordered.index("Savings</td>") > reordered.index("Holiday Club</td>")


def test_fault_late_render(client: TestClient, state: MockBankState) -> None:
    state.faults.late_render_ms = 1500
    html = client.get("/frame/members/search").text
    assert "setTimeout" in html


def test_fault_nav_and_hostile_content(client: TestClient, state: MockBankState) -> None:
    state.faults.nav_search_button = True
    state.faults.hostile_content = True
    nav = client.get("/frame/nav").text
    assert "<button" in nav
    assert "/admin/users" in nav
    assert "https://evil.example" in nav
    assert "ignore all previous rules" in client.get("/frame/members/search").text


def test_fault_version(client: TestClient, state: MockBankState) -> None:
    assert "MockBank 3.4.2" in client.get("/frame/home").text
    state.faults.version = "4.0.0"
    assert "MockBank 4.0.0" in client.get("/frame/home").text


def test_session_expiry(client: TestClient, state: MockBankState) -> None:
    client.post("/__mockbank/expire-sessions")
    assert "Session Expired" in client.get("/frame/members/search").text


def test_open_account_only_submit_commits(client: TestClient, state: MockBankState) -> None:
    review = client.post(
        "/frame/members/48213/open-account", data={"share_type": "Certificate", "deposit": "500"}
    )
    assert "Review Sub-Account" in review.text
    assert state.opened == []
    done = client.post(
        "/frame/members/48213/open-account/confirm",
        data={"share_type": "Certificate", "deposit": "500.00"},
    )
    assert "Sub-Account Opened" in done.text
    assert len(state.opened) == 1
    assert state.opened[0].confirmation in done.text


def test_open_account_validation(client: TestClient) -> None:
    r = client.post(
        "/frame/members/48213/open-account", data={"share_type": "Savings", "deposit": "-5"}
    )
    assert "Validation error" in r.text


def test_control_api_and_form(client: TestClient, state: MockBankState) -> None:
    r = client.patch("/__mockbank/faults", json={"slow_detail_ms": 1200, "reorder_rows": True})
    assert r.json()["slow_detail_ms"] == 1200
    assert client.patch("/__mockbank/faults", json={"nope": 1}).status_code == 422
    assert "fault control" in client.get("/__mockbank/").text
    client.post("/__mockbank/faults/form", data={"duplicate_search": "on", "late_render_ms": "300"})
    assert state.faults.duplicate_search is True
    assert state.faults.reorder_rows is False  # unchecked box clears it
    assert state.faults.late_render_ms == 300
    client.post("/__mockbank/reset")
    assert state.faults.duplicate_search is False
