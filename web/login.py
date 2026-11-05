"""Login, logout, and first-run admin setup — see CONTEXT.md: User Account, Role, Session; ADR
0058; RHA-99 Phase 1. /setup-admin is only ever reachable while web/auth.py's AuthMiddleware sees
has_any_admin() is False — unlike the existing Setup Wizard (web/setup.py), there's no page-local
re-check here, since the middleware itself refuses to let this route matter once an admin exists.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app_paths import APP_ROOT
from web import auth_queries as q
from web.auth import SESSION_COOKIE_NAME, clear_session_cookie, set_session_cookie

_WEB_DIR = APP_ROOT / "web"
router = APIRouter(prefix="")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (_WEB_DIR / "static").iterdir() if f.is_file())
))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _current_user(request: Request) -> dict | None:
    """/login and /setup-admin are both in AuthMiddleware's public allowlist, so
    request.state.user is never set for them — check the cookie directly instead."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return q.get_session_user(token) if token else None


@router.get("/login")
def login_form(request: Request):
    if _current_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html",
        {"error": request.query_params.get("error"), "next": request.query_params.get("next", "")}
    )


@router.post("/login")
def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...), next: str = Form(default=""),
):
    ip = _client_ip(request)
    if q.is_rate_limited(username, ip):
        return RedirectResponse(
            url=f"/login?error={quote('Too many attempts — try again in a few minutes.')}", status_code=303
        )
    user = q.get_user_by_username(username)
    # Same generic failure either way — never reveals whether the username itself was wrong.
    if user is None or not user["is_active"] or not q.verify_password(password, user["password_hash"]):
        q.record_login_attempt(username, ip, succeeded=False)
        return RedirectResponse(url=f"/login?error={quote('Incorrect username or password.')}", status_code=303)
    q.record_login_attempt(username, ip, succeeded=True, user_id=user["id"])
    token = q.create_session(user["id"])
    destination = next if next and next.startswith("/") else "/"
    response = RedirectResponse(url=destination, status_code=303)
    set_session_cookie(response, request, token)
    return response


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        user = q.get_session_user(token)
        if user:
            q.log_audit("logout", actor_user_id=user["id"])
        q.delete_session(token)
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/setup-admin")
def setup_admin_form(request: Request):
    return templates.TemplateResponse(request, "setup_admin.html", {"error": request.query_params.get("error")})


@router.post("/setup-admin")
def setup_admin_submit(
    request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...),
):
    if password != confirm_password:
        return RedirectResponse(url=f"/setup-admin?error={quote('Passwords do not match.')}", status_code=303)
    try:
        user_id = q.create_user(username, password, "admin")
    except ValueError as exc:
        return RedirectResponse(url=f"/setup-admin?error={quote(str(exc))}", status_code=303)
    q.log_audit("user_created", actor_user_id=user_id, detail=f"first admin account ({username})")
    token = q.create_session(user_id)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, request, token)
    return response
