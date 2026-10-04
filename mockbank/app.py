"""MockBank: a deliberately legacy-style member-services app used as the automation target.

Hostile on purpose: a frameset shell, table layouts, form fields without labels or IDs, and no
test IDs anywhere. Every runtime condition the replay engine must handle can be switched on
through ``/__mockbank/`` (by hand) or its JSON API (from tests).

Deep links such as ``/members/search`` return the frameset with that page in the ``main`` frame,
so a route works both as a bookmark and as an artifact ``navigate`` step.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from mockbank.faults import Faults, MockBankState, OpenedAccount
from mockbank.seed import MEMBERS, RESERVED_IDS, SHARE_TYPES, Member

COOKIE = "MBSESSION"
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_BLANK = "<html><head></head><body></body></html>"


def _credentials() -> tuple[str, str]:
    return os.environ.get("MOCKBANK_USER", "operator"), os.environ.get(
        "MOCKBANK_PASSWORD", "mockbank-demo"
    )


def create_app(state: MockBankState | None = None) -> FastAPI:
    app = FastAPI(title="MockBank", docs_url=None, redoc_url=None, openapi_url=None)
    st = state or MockBankState()
    app.state.mb = st

    def render(request: Request, name: str, status: int = 200, **ctx: Any) -> HTMLResponse:
        ctx.setdefault("version", st.faults.version)
        ctx.setdefault("faults", st.faults)
        return _TEMPLATES.TemplateResponse(request, name, ctx, status_code=status)

    def authed(request: Request) -> bool:
        return request.cookies.get(COOKIE) in st.sessions

    def shell(request: Request, main_src: str) -> Response:
        if not authed(request):
            nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(nxt, safe='')}", status_code=303)
        return render(request, "shell.html", main_src=main_src)

    def frame_guard(request: Request, *, main: bool = True) -> Response | None:
        if not authed(request):
            return render(request, "expired.html")
        if main and st.faults.blank_main:
            return HTMLResponse(_BLANK)
        return None

    def denied(member: Member) -> bool:
        return member.restricted or st.faults.permission_denied_all

    # ---------------------------------------------------------------- authentication

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request, next: str = "/") -> Response:
        return render(request, "login.html", next=next, error=None)

    @app.post("/login")
    async def login(
        request: Request, u: str = Form(""), p: str = Form(""), next: str = Form("/")
    ) -> Response:
        user, password = _credentials()
        if not (secrets.compare_digest(u, user) and secrets.compare_digest(p, password)):
            return render(request, "login.html", 401, next=next, error="Invalid user or password.")
        target = next if next.startswith("/") and not next.startswith("//") else "/"
        resp = RedirectResponse(target, status_code=303)
        resp.set_cookie(COOKIE, st.new_session(), httponly=True, samesite="lax")
        return resp

    @app.get("/logout")
    async def logout(request: Request) -> Response:
        st.sessions.discard(request.cookies.get(COOKIE, ""))
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    # ---------------------------------------------------------------- shell (deep links)

    @app.get("/")
    @app.get("/home")
    async def shell_home(request: Request) -> Response:
        return shell(request, "/frame/home")

    @app.get("/members/search")
    async def shell_search(request: Request) -> Response:
        query = f"?{request.url.query}" if request.url.query else ""
        return shell(request, f"/frame/members/search{query}")

    @app.get("/members/{mid}")
    async def shell_detail(request: Request, mid: str) -> Response:
        return shell(request, f"/frame/members/{quote(mid)}")

    @app.get("/members/{mid}/open-account")
    async def shell_open(request: Request, mid: str) -> Response:
        return shell(request, f"/frame/members/{quote(mid)}/open-account")

    @app.get("/admin/users")
    async def shell_admin(request: Request) -> Response:
        return shell(request, "/frame/admin/users")

    # ---------------------------------------------------------------- frame pages

    @app.get("/frame/nav", response_class=HTMLResponse)
    async def nav(request: Request) -> Response:
        return frame_guard(request, main=False) or render(request, "nav.html")

    @app.get("/frame/home", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        return frame_guard(request) or render(request, "home.html")

    @app.get("/frame/admin/users", response_class=HTMLResponse)
    async def admin(request: Request) -> Response:
        return frame_guard(request) or render(request, "admin.html")

    @app.get("/frame/members/search", response_class=HTMLResponse)
    async def search(request: Request, mid: str | None = None, ack: str | None = None) -> Response:
        if guard := frame_guard(request):
            return guard
        f = st.faults
        if ack == "maint":
            f.unknown_dialog = False
        message, error = None, False
        if mid is not None:
            mid = mid.strip()
            member = MEMBERS.get(mid)
            if not re.fullmatch(r"\d{5}", mid):
                message, error = "Validation error: Member ID must be 5 digits.", True
            elif mid in RESERVED_IDS:
                message, error = f"Validation error: member number {mid} is reserved.", True
            elif member is None:
                message = "No member found for that ID."
            elif denied(member):
                message, error = "Access denied: you are not authorized to view this member.", True
            else:
                target = "/frame/home" if f.wrong_landing else f"/frame/members/{mid}"
                return RedirectResponse(target, status_code=303)
        return render(
            request,
            "search.html",
            message=message,
            error=error,
            search_label=f.rename_search or "Search",
            disabled=f.disabled_search,
            duplicate=f.duplicate_search,
            late_ms=f.late_render_ms,
            hostile=f.hostile_content,
            notice=st.take_notice(),
            maintenance=f.unknown_dialog,
        )

    @app.get("/frame/members/{mid}", response_class=HTMLResponse)
    async def detail(request: Request, mid: str) -> Response:
        if guard := frame_guard(request):
            return guard
        f = st.faults
        if f.slow_detail_ms:
            await asyncio.sleep(f.slow_detail_ms / 1000)
        if st.take_503():
            return HTMLResponse("<html><body><h1>503 Service Unavailable</h1></body></html>", 503)
        if f.http_500_detail:
            return HTMLResponse(
                "<html><body><h1>500 Internal Server Error</h1><p>CORE-ERR 0x1F</p></body></html>",
                500,
            )
        member = MEMBERS.get(mid)
        if member is None:
            return render(
                request,
                "search.html",
                404,
                message="No member found for that ID.",
                error=False,
                search_label="Search",
                disabled=False,
                duplicate=False,
                late_ms=0,
                hostile=False,
                notice=False,
                maintenance=False,
            )
        if denied(member):
            return render(
                request,
                "search.html",
                403,
                message="Access denied: you are not authorized to view this member.",
                error=True,
                search_label="Search",
                disabled=False,
                duplicate=False,
                late_ms=0,
                hostile=False,
                notice=False,
                maintenance=False,
            )
        shares = list(reversed(member.shares)) if f.reorder_rows else list(member.shares)
        return render(request, "detail.html", m=member, shares=shares)

    def member_or_404(mid: str) -> Member | None:
        member = MEMBERS.get(mid)
        return None if member is None or denied(member) else member

    @app.get("/frame/members/{mid}/open-account", response_class=HTMLResponse)
    async def open_form(request: Request, mid: str) -> Response:
        if guard := frame_guard(request):
            return guard
        member = member_or_404(mid)
        if member is None:
            return HTMLResponse("Not found", 404)
        return render(request, "open_account.html", m=member, share_types=SHARE_TYPES, error=None)

    @app.post("/frame/members/{mid}/open-account", response_class=HTMLResponse)
    async def open_review(
        request: Request, mid: str, share_type: str = Form(""), deposit: str = Form("")
    ) -> Response:
        if guard := frame_guard(request):
            return guard
        member = member_or_404(mid)
        if member is None:
            return HTMLResponse("Not found", 404)
        try:
            amount = Decimal(deposit.replace(",", "").replace("$", ""))
        except InvalidOperation:
            amount = Decimal(-1)
        if share_type not in SHARE_TYPES or amount <= 0:
            return render(
                request,
                "open_account.html",
                m=member,
                share_types=SHARE_TYPES,
                error="Validation error: choose a share type and a positive deposit.",
            )
        return render(
            request, "review.html", m=member, share_type=share_type, deposit=f"{amount:.2f}"
        )

    @app.post("/frame/members/{mid}/open-account/confirm", response_class=HTMLResponse)
    async def open_confirm(
        request: Request, mid: str, share_type: str = Form(""), deposit: str = Form("")
    ) -> Response:
        if guard := frame_guard(request):
            return guard
        member = member_or_404(mid)
        if member is None or share_type not in SHARE_TYPES:
            return HTMLResponse("Not found", 404)
        confirmation = "CNF-" + "".join(
            secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6)
        )
        st.opened.append(OpenedAccount(mid, share_type, deposit, confirmation))
        return render(request, "confirmed.html", confirmation=confirmation, member_id=mid)

    # ---------------------------------------------------------------- fault control (not the app)

    @app.get("/__mockbank/", response_class=HTMLResponse)
    async def control_page(request: Request) -> Response:
        fields = []
        for name, info in Faults.model_fields.items():
            value = getattr(st.faults, name)
            kind = "bool" if isinstance(value, bool) else "text"
            fields.append((name, {"kind": kind, "value": value, "help": info.description}))
        return _TEMPLATES.TemplateResponse(
            request,
            "control.html",
            {"fields": fields, "sessions": len(st.sessions), "opened": len(st.opened)},
        )

    @app.get("/__mockbank/faults")
    async def get_faults() -> dict[str, Any]:
        return st.faults.model_dump()

    @app.patch("/__mockbank/faults")
    async def patch_faults(changes: dict[str, Any]) -> Response:
        try:
            st.faults = Faults.model_validate({**st.faults.model_dump(), **changes})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(st.faults.model_dump())

    @app.post("/__mockbank/faults/form")
    async def form_faults(request: Request) -> Response:
        form = await request.form()
        data: dict[str, Any] = {}
        for name in Faults.model_fields:
            current = getattr(st.faults, name)
            raw = form.get(name)
            if isinstance(current, bool):
                data[name] = raw is not None
            elif raw is None or str(raw).strip() == "":
                data[name] = None if name == "rename_search" else Faults.model_fields[name].default
            else:
                data[name] = str(raw).strip()
        st.faults = Faults.model_validate(data)
        return RedirectResponse("/__mockbank/", status_code=303)

    @app.post("/__mockbank/reset")
    async def reset() -> Response:
        st.reset()
        return RedirectResponse("/__mockbank/", status_code=303)

    @app.post("/__mockbank/expire-sessions")
    async def expire() -> Response:
        st.expire_sessions()
        return RedirectResponse("/__mockbank/", status_code=303)

    @app.get("/__mockbank/state")
    async def get_state() -> dict[str, Any]:
        return {
            "sessions": len(st.sessions),
            "opened": [vars(o) for o in st.opened],
            "version": st.faults.version,
        }

    return app
