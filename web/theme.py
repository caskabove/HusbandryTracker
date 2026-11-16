"""Color Themes (see CONTEXT.md: Theme; RHA-118).

A Theme is a named set of CSS custom properties in web/static/style.css (`:root[data-theme="<slug>"]`).
Each User Account picks one on the Settings page; it's stored on `user.theme` (NULL = Default,
the original ocean-blue scheme, which lives in the plain `:root` block). The choice is rendered
server-side as a `data-theme` attribute on every page's <html> element via `html_theme_attr`
below. That way the page arrives already themed, with no flash of the Default theme first, which
a client-side (localStorage + script) approach can't guarantee.

Status colors (--status-*) are deliberately NOT part of any Theme: they live only in `:root`,
so an out-of-range reading or an error looks the same whichever Theme is picked.
"""
from __future__ import annotations

from markupsafe import Markup
from jinja2 import pass_context

# slug -> label + the six palette roles from the ticket. The roles here only feed the swatch
# preview on the Settings page; the real tokens (including derived ones like borders and muted
# text) live in style.css. tests/test_themes.py checks the two stay in step.
THEMES: dict[str, dict] = {
    "forest": {
        "label": "Forest",
        "description": "Temperate and muted: moss, bark, amber light.",
        "swatch": ["#1B2420", "#26332C", "#5E8C61", "#8A6F4E", "#D9A441", "#E8EDE4"],
    },
    "ocean-reef": {
        "label": "Ocean Reef",
        "description": "Deep navy water, turquoise, coral accent.",
        "swatch": ["#0B1E2D", "#12303F", "#1FB5B0", "#3A7CA5", "#FF6F61", "#E6F4F1"],
    },
    "planted-tank": {
        "label": "Planted Tank",
        "description": "Near-black substrate, bright plant green, red stem-plant accent.",
        "swatch": ["#14191A", "#1F2A28", "#7BC74D", "#2E9E8F", "#C8445A", "#EAF2E6"],
    },
    "desert": {
        "label": "Desert",
        "description": "The light theme: sand, terracotta, sage, dusk purple.",
        "swatch": ["#F4E9D8", "#FBF5EA", "#C2643B", "#8A9A6B", "#5B4A7A", "#3B2A20"],
    },
    "jungle": {
        "label": "Jungle",
        "description": "Saturated tropical greens with an orchid-magenta accent.",
        "swatch": ["#0E1F17", "#163024", "#18A558", "#0F7B6C", "#E0368C", "#F0F7EC"],
    },
}

# The Default theme's swatch (the plain :root block in style.css), for the Settings page preview.
DEFAULT_SWATCH = ["#0d161a", "#162226", "#2f566b", "#007f7f", "#4f829d", "#e8eef0"]


def is_valid_theme(slug: str | None) -> bool:
    """None/"" means Default."""
    return not slug or slug in THEMES


def theme_for_request(request) -> str | None:
    """The logged-in user's Theme slug, or None (Default) when there's no user (login page,
    first-admin setup) or they never picked one. An unknown slug, e.g. a Theme since removed,
    also falls back to Default instead of rendering a page with no colors defined."""
    user = getattr(request.state, "user", None) if request is not None else None
    slug = user.get("theme") if user else None
    return slug if slug in THEMES else None


@pass_context
def html_theme_attr(context) -> Markup:
    """` data-theme="<slug>"` for the <html> tag, or nothing for Default."""
    slug = theme_for_request(context.get("request"))
    return Markup(f' data-theme="{slug}"') if slug else Markup("")


def install(templates) -> None:
    """Every router has its own Jinja2Templates instance, so each one calls this."""
    templates.env.globals["html_theme_attr"] = html_theme_attr
