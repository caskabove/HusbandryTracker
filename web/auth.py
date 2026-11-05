"""Login enforcement — see CONTEXT.md: User Account, Role, Session; ADR 0058; RHA-99 Phase 1.

AuthMiddleware is the first middleware this app has ever had (web/main.py's app.add_middleware
was previously unused). It runs in front of every route, including the dashboard and every /admin
page — there is deliberately no "skip login for localhost" shortcut (Windows port forwarding and
Tailscale can make an outside request look like localhost — see RHA-99). Two gates, in order:

1. No admin account exists yet (has_any_admin() is False) -> everything redirects to /setup-admin
   except /setup-admin itself and the allowlisted static/login paths.
2. Otherwise, every non-allowlisted path needs a valid session cookie -> redirects to /login.

A second, narrower gate lives here too: ADMIN_ONLY_PREFIXES/ADMIN_ONLY_EXACT name the whole-page
subtrees RHA-99 puts in the Admin-only bucket unconditionally (device/plugin registration, global
app settings and user management) — see docs/adr/0058. Everything else (the dashboard, an
Enclosure's own Admin page, Animal/Care/Plant editing) is open to any logged-in user in this phase;
per-record ownership filtering is Phase 2's job, not this middleware's.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse

from web import auth_queries as q

SESSION_COOKIE_NAME = "session"
SESSION_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60  # ~180 days — "phone PWA stays signed in" (RHA-99)

# Reachable with no session at all.
_PUBLIC_EXACT = {"/login", "/favicon.ico"}
_PUBLIC_PREFIXES = ("/static/",)

# Reachable only while has_any_admin() is False.
_SETUP_ADMIN_PATH = "/setup-admin"

# Whole-page subtrees that are Admin-only unconditionally in Phase 1 — see module docstring and
# docs/adr/0058. The bare "/admin"/"/admin/" is the global Sensors/Plugs device list + registration
# page; "/admin/app" is App Admin (settings, plugins, Tuya credentials, Users); the three wizards
# are all Room/Enclosure/device setup. Everything else under /admin/ (Enclosure detail pages,
# Animal/Plant/Care editing) stays open to any logged-in user this phase.
ADMIN_ONLY_EXACT = {"/admin", "/admin/"}
ADMIN_ONLY_PREFIXES = ("/admin/app", "/setup", "/add-pet", "/backfill")


def _is_admin_only_path(path: str) -> bool:
    return path in ADMIN_ONLY_EXACT or path.startswith(ADMIN_ONLY_PREFIXES)


def require_admin(request: Request) -> None:
    """Defense-in-depth check for a route that's always admin-only regardless of where it's
    mounted — AuthMiddleware's prefix gate already covers every route reachable through the pages
    named above, so this is for anything added later that doesn't fit that path shape."""
    user = getattr(request.state, "user", None)
    if user is None or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")


def set_session_cookie(response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME, token,
        max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        httponly=True, samesite="lax", secure=(request.url.scheme == "https"),
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        if not q.has_any_admin():
            if path != _SETUP_ADMIN_PATH:
                return RedirectResponse(url=_SETUP_ADMIN_PATH, status_code=303)
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE_NAME)
        user = q.get_session_user(token) if token else None
        if user is None:
            if request.method == "GET":
                return RedirectResponse(url=f"/login?next={path}", status_code=303)
            return RedirectResponse(url="/login", status_code=303)

        if _is_admin_only_path(path) and user["role"] != "admin":
            # A plain Response, not raise HTTPException: this middleware sits outside Starlette's
            # ExceptionMiddleware in the stack, so an HTTPException raised here would be caught
            # only by ServerErrorMiddleware (a generic 500), not turned into a real 403.
            return PlainTextResponse("Admin only.", status_code=403)

        request.state.user = user
        return await call_next(request)
