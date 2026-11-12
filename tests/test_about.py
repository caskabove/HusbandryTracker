"""About page: shows which version is installed (see version.py)."""
from __future__ import annotations

from starlette.requests import Request

import version
from web import main as main_routes


def _request(path: str) -> Request:
    from web.main import app
    scope = {"type": "http", "method": "GET", "path": path, "query_string": b"",
             "headers": [], "app": app, "root_path": ""}
    return Request(scope)


def test_about_page_shows_the_app_version_and_is_marked_current(temp_db, monkeypatch):
    monkeypatch.setattr(main_routes, "APP_VERSION", "1.2.3")

    html = main_routes.about(_request("/about")).body.decode("utf-8")

    assert '<strong class="app-version">1.2.3</strong>' in html
    assert '<a href="/about" aria-current="page">About</a>' in html


def test_version_comes_from_the_bundled_version_file(tmp_path, monkeypatch):
    (tmp_path / "VERSION").write_text("1.0.8-beta1\n", encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "VERSION")

    assert version._read_version() == "1.0.8-beta1"


def test_without_a_version_file_it_reports_a_development_build(tmp_path, monkeypatch):
    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "VERSION")

    assert version._read_version().startswith(version.DEV_VERSION)
