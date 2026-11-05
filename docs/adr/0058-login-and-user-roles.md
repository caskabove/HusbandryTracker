# Login, roles, sessions, and first-admin setup (RHA-99 Phase 1)

**Status**: accepted

**Context**: Husbandry Tracker has never had authentication — `web/main.py`'s own docstring said
so outright, and the app was protected only by listening on `127.0.0.1`. RHA-99 asks for real
login with two roles (Admin sees/edits everything and manages users/devices/settings; User sees/
edits only what they entered) and per-record ownership. That's a large change touching nearly
every page and query module, so it's being delivered in phases. This ADR covers Phase 1: the
`user` table, password hashing, sessions, the login page, first-run admin setup, basic user
management, audit logging, rate-limited logins, and the tray's "Reset admin password" recovery
item — not yet `owner_user_id` columns or per-query ownership filtering.

**Decision**: Add `user`, `session`, and `audit_log` tables (db/schema.sql) and a new
`AuthMiddleware` (web/auth.py) — the first middleware this app has ever registered — that runs in
front of every request. Passwords are hashed with argon2id (`argon2-cffi`). A session is a random
token (`secrets.token_urlsafe(32)`) stored server-side in `session` and handed to the browser as an
`HttpOnly`, `SameSite=Lax` cookie (`Secure` only over HTTPS), long-lived (~180 days) with no
idle-timeout column — the model is explicit revocation (logout, an admin resetting a password,
"sign out everywhere"), not expiry. `audit_log` doubles as the rate-limiter's source of truth: a
login counts recent `login_failed` rows by username and by IP instead of a separate counters table.

AuthMiddleware enforces two gates in order: while no active admin exists, every path except
`/setup-admin` and the static/login allowlist redirects there; once one exists, every
non-allowlisted path needs a valid session, else it redirects to `/login`. There is deliberately no
"skip login for localhost" shortcut — Windows port forwarding and Tailscale can make an outside
request look like localhost (RHA-99's own requirement).

A third thing the same middleware enforces: RHA-99 puts device/plugin registration and app-wide
settings in the Admin-only bucket unconditionally, with zero dependency on ownership columns. So
`ADMIN_ONLY_EXACT`/`ADMIN_ONLY_PREFIXES` in web/auth.py gate the bare `/admin` page (the global
Sensors/Plugs device list and registration page), `/admin/app` (App Admin — settings, plugins,
Tuya credentials, and the new Users card), and the three wizards (`/setup`, `/add-pet`,
`/backfill` — all Room/Enclosure/device setup) to Admin only, centrally, rather than scattering a
`require_admin()` call across every route in those files. `require_admin(request)` still exists in
web/auth.py as a defense-in-depth helper for anything added later that doesn't fit that path shape.

**Scope, this version**:
- Admin-only (enforced centrally, by path, in AuthMiddleware): `/admin`, `/admin/app/*`,
  `/setup/*`, `/add-pet/*`, `/backfill/*`.
- Open to any logged-in user, **not yet filtered by ownership**: the dashboard, an Enclosure's own
  Admin page (`/admin/enclosures/*` — Animals, Plants, Care, that Enclosure's own Sensor/Plug
  cards), View Data, Graphs, Help. A User can currently see and edit every Enclosure, not just
  their own — closing that gap is Phase 2's entire purpose, along with `owner_user_id` columns and
  single/bulk ownership reassignment.
- One known, accepted side effect: the only "Add Animal" form today lives on the now Admin-only
  App Admin page (it moved there under ADR 0050), so a non-admin currently has no UI path to create
  a brand-new Animal row at all. Animal creation isn't meant to be Admin-only per RHA-99's own
  ownership model — Phase 2, which already has to revisit this page's contents alongside ownership
  filtering, should move Add Animal somewhere a User can reach, or special-case the route.
- SQLCipher at-rest encryption is explicitly out of scope — split into its own ticket.
- `sensor`/`plug` *data* (readings, on/off status) for an Enclosure a User owns, versus device
  *setup* staying Admin-only, is RHA-99's own proposal for Phase 2 — not attempted here, since it
  needs the same per-route audit as the rest of ownership filtering.

**Considered Options**:
- **JWT/signed cookies instead of a server-side session table** — rejected: RHA-99 explicitly asks
  for "a random session token in a cookie," and a DB-backed session is what makes "sign out
  everywhere" and an admin-triggered password reset actually revoke access immediately, rather than
  waiting out a signed token's own expiry.
- **`require_admin(request)` called at the top of every admin-only route function**, scattered
  across web/admin.py, web/setup.py, web/add_pet.py, web/backfill.py — rejected in favor of the
  centralized path-prefix check in AuthMiddleware: it can't be missed on a route added later under
  an already-gated page, and it needed no changes at all to setup.py/add_pet.py/backfill.py, whose
  entire prefix is already unambiguously Admin-only.
- **A separate rate-limit counters table** — rejected: `audit_log` already records every failed
  login; counting recent rows by username/IP is one query, and it's also the audit trail RHA-99
  separately asks for.
- **A second tray exception that writes a request file for Ingest to notice** (matching "Back Up
  Now"'s shape) for Reset Admin Password — rejected in favor of tray/supervisor.py importing
  `db.db.get_connection()` directly: the operation is one bounded `UPDATE` + `DELETE`, the same kind
  of concurrent write web/ and ingest/ already make to this database constantly, so a round-trip
  through Ingest's scan interval would only add latency for no safety benefit. The module docstring
  now describes this as its second exception to "never opens the database itself" (Restore was the
  first).

**Consequences**: `db/schema.sql` gains `user`/`session`/`audit_log`; `tools/migrate_2026_11_05_
user_auth.py` brings an already-installed database up to date (gitignored like every other
`tools/migrate_*.py`, per the existing convention — flagged to the user as an auth-relevant
exception worth reconsidering). New modules: `web/auth_queries.py` (hashing, sessions, user CRUD,
rate-limiting), `web/auth.py` (AuthMiddleware, `require_admin`, cookie helpers), `web/login.py`
(`/login`, `/logout`, `/setup-admin`). `web/main.py` registers `AuthMiddleware` and the login
router and drops its "no auth" docstring line. `web/admin.py` gains a Users card on App Admin
(create, disable/enable, change role, reset password — the last active admin can't be disabled or
demoted) backed by new `/admin/app/users/...` routes. `_nav.html` shows the logged-in username/role
and a Log Out button, reading `request.state.user` directly — Starlette's `Jinja2Templates.
TemplateResponse(request, name, context)` already injects `request` into every template, so this
needed no change to any existing route's own context dict. `tray/supervisor.py` gets a "Reset Admin
Password" menu item. New dependencies: `argon2-cffi` (runtime), `httpx` (dev/test only, for
`tests/test_auth.py`'s `starlette.testclient.TestClient` — the first endpoint-level test in this
repo, needed because the existing direct-route-call test pattern in `tests/test_nav_pages.py` never
goes through ASGI middleware and so can't exercise login at all).
