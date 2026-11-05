"""The Backfill Wizard — see CONTEXT.md: Backfill Wizard; ADR 0053.

Reached any time from App Admin's "Backfill Data" button, for the "a brand-new graph is just one
dot" problem: pick a Week or a Month, pick the Animal or Enclosure it's for, pick which of that
Enclosure's Manual Sensors to seed, and web/backfill_queries.py fills the gaps in that window from
each Sensor's own Target Range. Not gated by is_fresh_install() — same "reachable any time" shape
as web/add_pet.py, not the first-run Setup Wizard's.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app_paths import APP_ROOT
from web import admin_queries as q
from web import backfill_queries as bq
from web.wizard_shared import (
    animals_with_enclosure_names as _animals_with_enclosure_names,
    enclosures_with_room_names as _enclosures_with_room_names,
    wizard_redirect as _wizard_redirect,
)

_WEB_DIR = APP_ROOT / "web"
router = APIRouter(prefix="/backfill")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")
# Same cache-busting setup as web/admin.py's own separate Jinja2Templates instance — see its
# identical comment.
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (_WEB_DIR / "static").iterdir() if f.is_file())
))

# Only the two ranges the Backfill Wizard offers (see CONTEXT.md: Backfill Wizard) — a subset of
# view_data_queries.RANGE_OPTIONS, which also has 90 Days/180 Days/Year (Graphs-only ranges that
# don't make sense as a one-shot seed window).
_RANGE_CHOICES = (("week", "Week"), ("month", "Month"))
_DEFAULT_RANGE = "week"


def _clean_range(range_key: str) -> str:
    return range_key if range_key in dict(_RANGE_CHOICES) else _DEFAULT_RANGE


@router.get("/")
def backfill_index(request: Request):
    return templates.TemplateResponse(
        request, "backfill_range.html",
        {"range_choices": _RANGE_CHOICES, "error": request.query_params.get("error")},
    )


@router.get("/scope")
def backfill_scope(request: Request, range: str = _DEFAULT_RANGE):
    range = _clean_range(range)
    return templates.TemplateResponse(
        request, "backfill_scope.html",
        {
            "range": range,
            "animals": _animals_with_enclosure_names(),
            "enclosures": _enclosures_with_room_names(),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/animals/select")
def backfill_animal_select(animal_id: int, range: str = _DEFAULT_RANGE):
    """Resolves straight to the Animal's own Enclosure — Readings are an Enclosure property, not
    an Animal one (see CONTEXT.md: Enclosure), so picking an Animal here is just a lookup shortcut
    into the same sensors step picking its Enclosure directly would reach."""
    animal = q.get_animal(animal_id)
    if animal is None:
        return RedirectResponse(
            url=_wizard_redirect("/backfill/scope", range=range, error="Animal not found."),
            status_code=303,
        )
    return RedirectResponse(
        url=_wizard_redirect(f"/backfill/enclosures/{animal['enclosure_id']}/sensors", range=range),
        status_code=303,
    )


@router.get("/enclosures/select")
def backfill_enclosure_select(enclosure_id: int, range: str = _DEFAULT_RANGE):
    return RedirectResponse(
        url=_wizard_redirect(f"/backfill/enclosures/{enclosure_id}/sensors", range=range),
        status_code=303,
    )


@router.get("/enclosures/{enclosure_id}/sensors")
def backfill_sensors_form(request: Request, enclosure_id: int, range: str = _DEFAULT_RANGE):
    range = _clean_range(range)
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/backfill/", status_code=303)
    return templates.TemplateResponse(
        request, "backfill_sensors.html",
        {
            "enclosure": enclosure, "range": range,
            "range_label": dict(_RANGE_CHOICES)[range],
            "sensors": bq.eligible_sensors_for_enclosure(enclosure),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/enclosures/{enclosure_id}/fill")
async def backfill_run(request: Request, enclosure_id: int, range: str = Form(_DEFAULT_RANGE)):
    range = _clean_range(range)
    form = await request.form()
    sensor_ids = [int(v) for v in form.getlist("sensor_id")]
    if not sensor_ids:
        return RedirectResponse(
            url=_wizard_redirect(
                f"/backfill/enclosures/{enclosure_id}/sensors", range=range,
                error="Pick at least one Sensor to fill.",
            ),
            status_code=303,
        )
    try:
        summary = bq.run_backfill(enclosure_id, sensor_ids, range)
    except ValueError as exc:
        return RedirectResponse(
            url=_wizard_redirect(f"/backfill/enclosures/{enclosure_id}/sensors", range=range, error=str(exc)),
            status_code=303,
        )
    return RedirectResponse(
        url=(
            f"/backfill/enclosures/{enclosure_id}/done"
            f"?range={summary['range_key']}&sensors={summary['sensors_filled']}&points={summary['points_written']}"
        ),
        status_code=303,
    )


@router.get("/enclosures/{enclosure_id}/done")
def backfill_done(request: Request, enclosure_id: int, range: str = _DEFAULT_RANGE, sensors: int = 0, points: int = 0):
    range = _clean_range(range)
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/backfill/", status_code=303)
    return templates.TemplateResponse(
        request, "backfill_done.html",
        {
            "enclosure": enclosure, "range_label": dict(_RANGE_CHOICES)[range], "range": range,
            "sensors_filled": sensors, "points_written": points,
        },
    )
