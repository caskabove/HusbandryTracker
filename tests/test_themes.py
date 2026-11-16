"""Color Themes (see CONTEXT.md: Theme; web/theme.py; RHA-118).

Two halves: the stylesheet itself (every Theme defines the same tokens, never touches the fixed
status colors, and meets WCAG AA, computed straight from the CSS rather than trusted from a
comment), and the per-user choice (stored on the account, rendered server-side as data-theme on
<html>, Default when unset).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import auth_queries as q
from web.theme import DEFAULT_LOGO, DEFAULT_SWATCH, THEMES, logo_for_theme

ROOT = Path(__file__).resolve().parent.parent
STYLE = (ROOT / "web" / "static" / "style.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "web" / "templates"

# Tokens every Theme must set, so nothing falls through to Default's ocean blues.
REQUIRED_TOKENS = {
    "bg", "panel-bg", "panel-header-bg", "room-bg", "room-header-bg", "primary", "primary-bright",
    "secondary", "accent", "text", "text-muted", "border", "on-primary", "on-primary-bright",
    "on-accent", "header-divider", "header-image", "header-image-narrow", "drop-target-bg",
    "chart-line", "color-scheme",
}
SURFACES = ("bg", "panel-bg", "panel-header-bg", "room-bg", "room-header-bg")
AA = 4.5


def _block(selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", STYLE, re.S)
    assert match, f"no {selector} block in style.css"
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+|color-scheme)\s*:\s*([^;]+);", body)}


def _theme(slug: str) -> dict[str, str]:
    return {k.removeprefix("--"): v for k, v in _block(f':root[data-theme="{slug}"]').items()}


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("slug", THEMES)
def test_every_theme_sets_every_token(slug):
    assert REQUIRED_TOKENS <= set(_theme(slug))


@pytest.mark.parametrize("slug", THEMES)
def test_no_theme_overrides_a_status_color(slug):
    assert not [name for name in _theme(slug) if name.startswith(("status-", "lineage-flag"))]


@pytest.mark.parametrize("slug", THEMES)
def test_theme_text_meets_wcag_aa(slug):
    t = _theme(slug)
    for surface in SURFACES:
        for ink in ("text", "text-muted", "primary-bright"):
            ratio = _contrast(t[ink], t[surface])
            assert ratio >= AA, f"{slug}: --{ink} on --{surface} is {ratio:.2f}:1"
    for fill, ink in (("primary", "on-primary"), ("accent", "on-accent"), ("primary-bright", "on-primary-bright")):
        ratio = _contrast(t[ink], t[fill])
        assert ratio >= AA, f"{slug}: --{ink} on --{fill} is {ratio:.2f}:1"


@pytest.mark.parametrize("slug", THEMES)
def test_sparkline_line_is_visible_on_every_surface(slug):
    # WCAG 1.4.11 non-text contrast (3:1). graphs.js appends an alpha suffix, so it must be #rrggbb.
    t = _theme(slug)
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", t["chart-line"])
    assert min(_contrast(t["chart-line"], t[s]) for s in ("panel-bg", "panel-header-bg")) >= 3


@pytest.mark.parametrize("slug", THEMES)
def test_settings_swatch_matches_the_stylesheet(slug):
    t = _theme(slug)
    roles = [t["bg"], t["panel-bg"], t["primary"], t["secondary"], t["accent"], t["text"]]
    assert [c.lower() for c in THEMES[slug]["swatch"]] == roles


def test_default_theme_is_the_original_scheme():
    root = _block(":root")
    assert [root["--bg"], root["--panel-bg"], root["--primary"], root["--text"]] == ["#0d161a", "#162226", "#2f566b", "#e8eef0"]
    assert DEFAULT_SWATCH[0] == root["--bg"] and DEFAULT_SWATCH[-1] == root["--text"]


def test_no_hardcoded_colors_outside_the_token_blocks():
    first_rule = STYLE.index("* { box-sizing")
    rules = re.sub(r"/\*.*?\*/", "", STYLE[first_rule:], flags=re.S)
    # The photo lightbox's black scrim/close button sit over a photo, not the UI, so they stay put.
    rules = re.sub(r"\.image-lightbox[^{]*\{[^}]*\}", "", rules)
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rules) == []


def test_every_page_template_carries_the_theme_hook():
    pages = [p for p in TEMPLATES.glob("*.html") if "<html" in p.read_text(encoding="utf-8")]
    assert pages
    assert [p.name for p in pages if '<html lang="en"{{ html_theme_attr() }}>' not in p.read_text(encoding="utf-8")] == []


@pytest.mark.parametrize("slug", [None, *THEMES])
def test_every_theme_has_its_logo_file(slug):
    assert (ROOT / "web" / logo_for_theme(slug).lstrip("/")).is_file()


@pytest.mark.parametrize("slug", THEMES)
def test_every_theme_has_its_header_scenes(slug):
    # RHA-119: a full-width scene plus a simplified one for narrow screens, both on disk.
    t = _theme(slug)
    for token, name in (("header-image", f"header-{slug}.svg"), ("header-image-narrow", f"header-{slug}-narrow.svg")):
        assert t[token] == f'url("/static/images/{name}")'
        assert (ROOT / "web" / "static" / "images" / name).is_file()


def test_default_theme_has_no_header_scene():
    root = _block(":root")
    assert root["--header-image"] == root["--header-image-narrow"] == "none"


def test_header_title_font_is_self_hosted():
    faces = re.findall(r"@font-face\s*\{(.*?)\}", STYLE, re.S)
    assert faces and all("http" not in f for f in faces)
    assert (ROOT / "web" / "static" / "fonts" / "amatic-sc-latin-700-normal.woff2").is_file()
    assert (ROOT / "web" / "static" / "fonts" / "AmaticSC-OFL.txt").is_file()


def test_every_template_cache_busts_the_logo():
    pages = [p for p in TEMPLATES.glob("*.html") if "logo_url()" in p.read_text(encoding="utf-8")]
    assert pages
    assert [p.name for p in pages if 'src="{{ logo_url() }}?v={{ asset_version }}"' not in p.read_text(encoding="utf-8")] == []


def test_no_template_hardcodes_the_logo():
    assert [p.name for p in TEMPLATES.glob("*.html") if "images/logo.png" in p.read_text(encoding="utf-8")] == []


# --- the per-user choice -----------------------------------------------------------------------

def _logged_in_client(role: str = "user") -> TestClient:
    from web.main import app
    q.create_user("admin1", "supersecret1", "admin")
    if role == "user":
        q.create_user("bob", "supersecret2", "user")
    client = TestClient(app, follow_redirects=False)
    username, password = ("bob", "supersecret2") if role == "user" else ("admin1", "supersecret1")
    assert client.post("/login", data={"username": username, "password": password, "next": ""}).status_code == 303
    return client


def test_a_new_user_gets_the_default_theme(temp_db):
    with _logged_in_client() as client:
        html = client.get("/settings").text
    assert '<html lang="en">' in html
    assert f'src="{DEFAULT_LOGO}?v=' in html
    assert re.search(r'<input type="radio" name="theme" value="" checked>', html)


def test_picking_a_theme_applies_it_server_side_and_persists(temp_db):
    with _logged_in_client() as client:
        response = client.post("/settings/theme", data={"theme": "desert"})
        assert response.status_code == 303
        assert "notice=Theme%20set%20to%20Desert" in response.headers["location"]

        for path in ("/settings", "/about", "/help"):
            html = client.get(path).text
            assert '<html lang="en" data-theme="desert">' in html
            assert 'src="/static/images/caskabove-logo-desert.png?v=' in html

    # Stored on the account, not the browser: a brand-new session (another device) gets it too.
    from web.main import app
    with TestClient(app, follow_redirects=False) as other:
        other.post("/login", data={"username": "bob", "password": "supersecret2", "next": ""})
        assert '<html lang="en" data-theme="desert">' in other.get("/settings").text


def test_choosing_default_clears_the_theme(temp_db):
    with _logged_in_client() as client:
        client.post("/settings/theme", data={"theme": "jungle"})
        client.post("/settings/theme", data={"theme": ""})
        assert '<html lang="en">' in client.get("/settings").text
    assert temp_db.execute("SELECT theme FROM user WHERE username = 'bob'").fetchone()[0] is None


def test_an_unknown_theme_is_rejected(temp_db):
    with _logged_in_client() as client:
        response = client.post("/settings/theme", data={"theme": "neon"})
        assert "error=" in response.headers["location"]
    assert temp_db.execute("SELECT theme FROM user WHERE username = 'bob'").fetchone()[0] is None


def test_a_theme_removed_from_code_falls_back_to_default(temp_db):
    with _logged_in_client() as client:
        temp_db.execute("UPDATE user SET theme = 'retired' WHERE username = 'bob'")
        temp_db.commit()
        assert '<html lang="en">' in client.get("/settings").text


def test_themes_are_per_user(temp_db):
    with _logged_in_client() as client:
        client.post("/settings/theme", data={"theme": "forest"})
    from web.main import app
    with TestClient(app, follow_redirects=False) as admin:
        admin.post("/login", data={"username": "admin1", "password": "supersecret1", "next": ""})
        assert '<html lang="en">' in admin.get("/settings").text


def test_login_page_renders_without_a_user(temp_db):
    q.create_user("admin1", "supersecret1", "admin")
    from web.main import app
    with TestClient(app, follow_redirects=False) as client:
        assert '<html lang="en">' in client.get("/login").text


def test_migration_adds_the_theme_column_and_is_idempotent(tmp_path):
    from db.migrations import m0032_user_theme
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("INSERT INTO user (username) VALUES ('alice')")
    m0032_user_theme.migrate(conn)
    m0032_user_theme.migrate(conn)
    assert conn.execute("SELECT theme FROM user").fetchone() == (None,)
    conn.close()
