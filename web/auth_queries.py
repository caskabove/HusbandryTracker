"""Write/read access backing login, sessions, and user management — the auth-system counterpart
to web/admin_queries.py (same short-lived-connection-per-call, ValueError-for-user-facing-errors
conventions). See CONTEXT.md: User Account, Role, Session, Audit Log; ADR 0058; RHA-99 Phase 1.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from db.db import get_connection

_hasher = PasswordHasher()

# "Per account and per IP" (RHA-99) in one query: a login_failed row within this window counts
# against both its username_attempted and its ip_address.
_RATE_LIMIT_WINDOW_MINUTES = 15
_RATE_LIMIT_MAX_ATTEMPTS = 5


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def has_any_admin() -> bool:
    """True once at least one active admin exists — the first-run gate AuthMiddleware checks on
    every request (see web/auth.py). Derived live from table state, same "no persisted flag"
    shape as admin_queries.is_fresh_install(); safe to recompute because set_user_active() and
    set_user_role() below never let the active-admin count reach zero once it's above zero."""
    with get_connection() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM user WHERE role = 'admin' AND is_active = 1"
        ).fetchone()
    return count > 0


def list_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM user ORDER BY username COLLATE NOCASE").fetchall()
    return [dict(row) for row in rows]


def get_user_by_username(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_user(username: str, password: str, role: str) -> int:
    username = username.strip()
    if not username:
        raise ValueError("Enter a username.")
    if role not in ("admin", "user"):
        raise ValueError("Pick a valid role.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM user WHERE username = ?", (username,)).fetchone():
            raise ValueError(f'"{username}" is already taken.')
        cur = conn.execute(
            "INSERT INTO user (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        )
        return cur.lastrowid


def _active_admin_count(conn, excluding_user_id: int | None = None) -> int:
    if excluding_user_id is None:
        (count,) = conn.execute("SELECT COUNT(*) FROM user WHERE role = 'admin' AND is_active = 1").fetchone()
    else:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM user WHERE role = 'admin' AND is_active = 1 AND id != ?",
            (excluding_user_id,),
        ).fetchone()
    return count


def set_user_active(user_id: int, is_active: bool) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT role, is_active FROM user WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("User not found.")
        if not is_active and row["role"] == "admin" and row["is_active"] and _active_admin_count(conn, user_id) == 0:
            raise ValueError("Can't disable the last active admin.")
        conn.execute("UPDATE user SET is_active = ? WHERE id = ?", (int(is_active), user_id))
    if not is_active:
        delete_all_sessions_for_user(user_id)


def set_user_role(user_id: int, role: str) -> None:
    if role not in ("admin", "user"):
        raise ValueError("Pick a valid role.")
    with get_connection() as conn:
        row = conn.execute("SELECT role, is_active FROM user WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("User not found.")
        if role == "user" and row["role"] == "admin" and row["is_active"] and _active_admin_count(conn, user_id) == 0:
            raise ValueError("Can't demote the last active admin.")
        conn.execute("UPDATE user SET role = ? WHERE id = ?", (role, user_id))


def reset_user_password(user_id: int, new_password: str) -> None:
    """Admin-triggered reset of someone else's password — also signs them out everywhere (RHA-99's
    "sign out everywhere" semantics), same as a tray password reset (see tray/supervisor.py)."""
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM user WHERE id = ?", (user_id,)).fetchone() is None:
            raise ValueError("User not found.")
        conn.execute("UPDATE user SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
    delete_all_sessions_for_user(user_id)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute("INSERT INTO session (token, user_id) VALUES (?, ?)", (token, user_id))
    return token


def get_session_user(token: str) -> dict | None:
    """Looks up the active (is_active=1) user for a session token, bumping last_seen_at. A session
    for a now-disabled user resolves to None without being deleted outright — re-enabling the
    account should not require logging in again."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.* FROM session s JOIN user u ON u.id = s.user_id
               WHERE s.token = ? AND u.is_active = 1""",
            (token,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE session SET last_seen_at = datetime('now') WHERE token = ?", (token,))
    return dict(row)


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM session WHERE token = ?", (token,))


def delete_all_sessions_for_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM session WHERE user_id = ?", (user_id,))


def log_audit(action: str, actor_user_id: int | None = None, username_attempted: str | None = None,
              ip_address: str | None = None, detail: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_log (actor_user_id, username_attempted, ip_address, action, detail)
               VALUES (?, ?, ?, ?, ?)""",
            (actor_user_id, username_attempted, ip_address, action, detail),
        )


def record_login_attempt(username: str, ip_address: str | None, succeeded: bool, user_id: int | None = None) -> None:
    log_audit(
        "login_success" if succeeded else "login_failed",
        actor_user_id=user_id,
        username_attempted=None if succeeded else username,
        ip_address=ip_address,
    )


def is_rate_limited(username: str, ip_address: str | None) -> bool:
    with get_connection() as conn:
        (count,) = conn.execute(
            f"""SELECT COUNT(*) FROM audit_log
                WHERE action = 'login_failed'
                  AND (username_attempted = ? OR ip_address = ?)
                  AND at > datetime('now', '-{_RATE_LIMIT_WINDOW_MINUTES} minutes')""",
            (username, ip_address),
        ).fetchone()
    return count >= _RATE_LIMIT_MAX_ATTEMPTS
