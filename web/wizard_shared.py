"""Helpers shared by every wizard-style "front door" onto web/admin_queries.py's create
functions — currently the first-run Setup Wizard (web/setup.py; see CONTEXT.md: Setup Wizard, ADR
0031), the Add New Pet wizard (web/add_pet.py; see CONTEXT.md: Add New Pet Wizard, ADR 0051), and
the Backfill Wizard (web/backfill.py; see CONTEXT.md: Backfill Wizard, ADR 0053). Split out once a
second wizard needed the exact same Target Range/Species Profile plumbing, rather than copy it a
second time and risk the two drifting apart.
"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request

from schemas import enclosure_types as et
from web import admin_queries as q

# Purpose (see CONTEXT.md: Purpose) is free text everywhere, not a fixed set — these are just the
# <datalist> suggestions, same ones already offered on the ordinary Add Plug form.
PURPOSE_SUGGESTIONS = ("light", "heat", "cooling", "UVB", "pump")

# Which Target Range metric (see schemas/enclosure_types.py) gets shown expanded-by-default on the
# Sensor step, with the rest of that Enclosure Type's metrics collapsed under "+ more metrics" —
# the one metric every keeper of that type is virtually guaranteed to test for. See ADR 0031.
_PRIMARY_METRIC_BY_TYPE = {"basic": "temperature", "amphibian": "temperature", "freshwater": "ph", "saltwater": "ph"}


def f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


def wizard_redirect(path: str, **params: str) -> str:
    """Builds a wizard redirect URL carrying only the non-empty query params given — used to thread
    the Species Profile pick (see CONTEXT.md: Species Profile) through a wizard's own step-to-step
    redirects without ever persisting it anywhere (same "never stored" rule as the picker itself),
    alongside each wizard's own error-message carry-through."""
    query = {k: v for k, v in params.items() if v}
    return path + (("?" + urlencode(query)) if query else "")


def primary_and_other_metrics(enclosure_type: str) -> tuple[et.TargetRangeMetric, list[et.TargetRangeMetric]]:
    metrics = et.target_range_metrics_for(enclosure_type)
    primary_key = _PRIMARY_METRIC_BY_TYPE.get(enclosure_type, "temperature")
    primary = next(m for m in metrics if m.key == primary_key)
    others = [m for m in metrics if m.key != primary_key]
    return primary, others


def enclosures_with_room_names() -> list[dict]:
    """list_enclosures() rows carry a bare room_id — an "existing Enclosure" picker wants to show
    each one's Room alongside its name, same as the Dashboard already groups them. Shared by the
    Add New Pet wizard and the Backfill Wizard."""
    rooms_by_id = {r["id"]: r["name"] for r in q.list_rooms()}
    enclosures = q.list_enclosures()
    for enclosure in enclosures:
        enclosure["room_name"] = rooms_by_id.get(enclosure["room_id"])
    return enclosures


def animals_with_enclosure_names() -> list[dict]:
    """list_animals() rows already carry enclosure_name (see web/admin_queries.py) — this just
    exists alongside enclosures_with_room_names() above for the Backfill Wizard's "pick an Animal"
    step, which resolves straight to that Animal's Enclosure (see CONTEXT.md: Backfill Wizard)."""
    return q.list_animals()


async def target_ranges_from_form(request: Request, metrics: tuple) -> dict:
    """Generic across however many metrics apply to this Enclosure Type (1 for most, up to 10 for
    Saltwater) — reading request.form() directly instead of one Form(...) parameter per metric
    (admin.py's own pattern) keeps a wizard-only route from needing a ~50-parameter signature for a
    form most of whose fields are left blank."""
    form = await request.form()
    ranges: dict = {}
    for m in metrics:
        raw_min, raw_max = form.get(f"min_{m.key}"), form.get(f"max_{m.key}")
        mn = float(raw_min) if raw_min else None
        mx = float(raw_max) if raw_max else None
        if m.converts_f_c:
            mn, mx = f_to_c(mn), f_to_c(mx)
        ranges[m.key] = (mn, mx)
    return ranges
