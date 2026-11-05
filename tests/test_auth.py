"""Login, roles, and sessions (see CONTEXT.md: User Account, Role, Session, Audit Log; ADR 0058;
RHA-99 Phase 1). Uses starlette's TestClient — the first endpoint-level (real ASGI dispatch,
middleware included) test in this repo; every earlier test either calls a route function directly
with a hand-built Request (tests/test_nav_pages.py — which never goes through AuthMiddleware) or
exercises pure query functions against the temp_db fixture. Needed here because AuthMiddleware
only exists in the real request pipeline.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from web import auth_queries as q


def _make_client() -> TestClient:
    from web.main import app
    return TestClient(app, follow_redirects=False)


def test_fresh_install_redirects_to_setup_admin(temp_db):
    with _make_client() as client:
        response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/setup-admin"


def test_setup_admin_creates_first_admin_and_logs_in(temp_db):
    with _make_client() as client:
        response = client.post(
            "/setup-admin",
            data={"username": "alice", "password": "supersecret1", "confirm_password": "supersecret1"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"

        # Session cookie from setup-admin carries forward — no longer bounced to /setup-admin or /login.
        response = client.get("/")
        assert response.status_code in (200, 303)
        if response.status_code == 303:
            assert response.headers["location"] == "/setup/"  # the existing, unrelated first-run Room/Enclosure wizard


def test_wrong_password_fails_with_generic_message_and_then_rate_limits(temp_db):
    q.create_user("alice", "supersecret1", "admin")
    with _make_client() as client:
        for _ in range(5):
            response = client.post("/login", data={"username": "alice", "password": "wrong", "next": ""})
            assert response.status_code == 303
            assert "error=Incorrect" in response.headers["location"]

        # 6th attempt within the window trips the rate limit instead of checking the password again.
        response = client.post("/login", data={"username": "alice", "password": "wrong", "next": ""})
        assert "Too+many+attempts" in response.headers["location"] or "Too%20many%20attempts" in response.headers["location"]


def test_successful_login_and_logout(temp_db):
    q.create_user("alice", "supersecret1", "admin")
    with _make_client() as client:
        response = client.post("/login", data={"username": "alice", "password": "supersecret1", "next": ""})
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session" in client.cookies

        response = client.get("/admin/app")
        assert response.status_code == 200

        response = client.post("/logout")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

        response = client.get("/admin/app")
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")


def test_user_role_is_forbidden_from_admin_only_pages(temp_db):
    q.create_user("alice", "supersecret1", "admin")
    q.create_user("bob", "supersecret2", "user")
    with _make_client() as client:
        client.post("/login", data={"username": "bob", "password": "supersecret2", "next": ""})
        assert client.get("/admin/app").status_code == 403
        assert client.get("/admin/").status_code == 403
        # Not gated in Phase 1 — ownership filtering is a later phase, not this one.
        assert client.get("/").status_code in (200, 303)


def test_cannot_disable_or_demote_the_last_active_admin(temp_db):
    user_id = q.create_user("alice", "supersecret1", "admin")
    with pytest.raises(ValueError):
        q.set_user_active(user_id, False)
    with pytest.raises(ValueError):
        q.set_user_role(user_id, "user")
