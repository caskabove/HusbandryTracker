"""The first-run Setup Wizard — see CONTEXT.md: Setup Wizard; ADR 0031.

A guided, plain-language front door onto the same writes web/admin_queries.py already performs for
Room, Enclosure, Animal, Plant, Sensor, and Plug creation — not a parallel implementation. Triggers
automatically from web/main.py's dashboard route when the database has zero Rooms and zero
Enclosures (see q.is_fresh_install()). Deliberately Manual-only for Sensor and Plug this version —
no Tracking Mode choice, no Discover Devices button — and never offers Plug Group creation (see
ADR 0031 for why).
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
from schemas import enclosure_types as et
from web import admin_queries as q

_WEB_DIR = APP_ROOT / "web"
router = APIRouter(prefix="/setup")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")
# Same cache-busting setup as web/admin.py's own separate Jinja2Templates instance — see its
# identical comment.
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (_WEB_DIR / "static").iterdir() if f.is_file())
))

# Purpose (see CONTEXT.md: Purpose) is free text everywhere, not a fixed set — these are just the
# <datalist> suggestions, same ones already offered on the ordinary Add Plug form.
PURPOSE_SUGGESTIONS = ("light", "heat", "cooling", "UVB", "pump")

# Which Target Range metric (see schemas/enclosure_types.py) gets shown expanded-by-default on the
# Sensor step, with the rest of that Enclosure Type's metrics collapsed under "+ more metrics" —
# the one metric every keeper of that type is virtually guaranteed to test for. See ADR 0031.
_PRIMARY_METRIC_BY_TYPE = {"basic": "temperature", "amphibian": "temperature", "freshwater": "ph", "saltwater": "ph"}


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


templates.env.filters["c_to_f"] = lambda c: None if c is None else c * 9 / 5 + 32


def _primary_and_other_metrics(enclosure_type: str) -> tuple[et.TargetRangeMetric, list[et.TargetRangeMetric]]:
    metrics = et.target_range_metrics_for(enclosure_type)
    primary_key = _PRIMARY_METRIC_BY_TYPE.get(enclosure_type, "temperature")
    primary = next(m for m in metrics if m.key == primary_key)
    others = [m for m in metrics if m.key != primary_key]
    return primary, others


async def _target_ranges_from_form(request: Request, metrics: tuple) -> q.TargetRanges:
    """Generic across however many metrics apply to this Enclosure Type (1 for most, up to 10 for
    Saltwater) — reading request.form() directly instead of one Form(...) parameter per metric
    (admin.py's own pattern) keeps this wizard-only route from needing a ~50-parameter signature
    for a form most of whose fields are left blank."""
    form = await request.form()
    ranges: q.TargetRanges = {}
    for m in metrics:
        raw_min, raw_max = form.get(f"min_{m.key}"), form.get(f"max_{m.key}")
        mn = float(raw_min) if raw_min else None
        mx = float(raw_max) if raw_max else None
        if m.converts_f_c:
            mn, mx = _f_to_c(mn), _f_to_c(mx)
        ranges[m.key] = (mn, mx)
    return ranges


@router.get("/")
def setup_index(request: Request):
    return templates.TemplateResponse(request, "setup_room.html", {"error": request.query_params.get("error")})


@router.post("/rooms")
def setup_create_room(name: str = Form(...)):
    name = name.strip()
    if not name:
        return RedirectResponse(url="/setup/?error=" + quote("Enter a name for the room."), status_code=303)
    room_id = q.create_room(name)
    return RedirectResponse(url=f"/setup/rooms/{room_id}", status_code=303)


@router.get("/rooms/{room_id}")
def setup_room_devices(request: Request, room_id: int):
    room = q.get_room(room_id)
    if room is None:
        return RedirectResponse(url="/setup/", status_code=303)
    return templates.TemplateResponse(
        request, "setup_room_devices.html", {"room": room, "error": request.query_params.get("error")}
    )


@router.post("/rooms/{room_id}/sensors")
def setup_create_room_sensor(
    room_id: int,
    label: str = Form(...),
    min_temperature_f: str = Form(""),
    max_temperature_f: str = Form(""),
    min_humidity: str = Form(""),
    max_humidity: str = Form(""),
):
    temp_min = _f_to_c(float(min_temperature_f)) if min_temperature_f else None
    temp_max = _f_to_c(float(max_temperature_f)) if max_temperature_f else None
    hum_min = float(min_humidity) if min_humidity else None
    hum_max = float(max_humidity) if max_humidity else None
    try:
        q.create_room_sensor(room_id, label, "manual", None, temp_min, temp_max, hum_min, hum_max)
    except ValueError as exc:
        return RedirectResponse(url=f"/setup/rooms/{room_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/setup/rooms/{room_id}", status_code=303)


@router.post("/rooms/{room_id}/plugs")
def setup_create_room_plug(
    room_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    target_on_time: str = Form(""),
    target_off_time: str = Form(""),
    always_on: bool = Form(False),
):
    try:
        q.create_plug(
            label, purpose, "manual", None, None, None, "1", target_on_time or None, target_off_time or None,
            room_id=room_id, enclosure_ids=[], controller_kind="none",
            target_temp_c=None, target_humidity_pct=None, always_on=always_on,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/setup/rooms/{room_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/setup/rooms/{room_id}", status_code=303)


@router.get("/enclosure")
def setup_enclosure_form(request: Request, room_id: str = ""):
    room = q.get_room(int(room_id)) if room_id else None
    return templates.TemplateResponse(
        request, "setup_enclosure.html",
        {
            "room": room, "room_id": room_id,
            "enclosure_types": et.ENCLOSURE_TYPES, "enclosure_type_labels": et.ENCLOSURE_TYPE_LABELS,
            "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures")
def setup_create_enclosure(
    name: str = Form(...),
    enclosure_type: str = Form("basic"),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
    room_id: str = Form(""),
):
    try:
        enclosure_id = q.create_enclosure(
            name, enclosure_type, bioactive, feeding_interval, watering_interval,
            spot_clean_interval, deep_clean_interval,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/setup/enclosure?room_id={room_id}&error={quote(str(exc))}", status_code=303
        )
    if room_id:
        q.set_enclosure_room(enclosure_id, int(room_id))
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/animals", status_code=303)


@router.get("/enclosures/{enclosure_id}/animals")
def setup_animals(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/setup/", status_code=303)
    return templates.TemplateResponse(
        request, "setup_animals.html", {"enclosure": enclosure, "error": request.query_params.get("error")}
    )


@router.post("/enclosures/{enclosure_id}/animals")
def setup_create_animal(
    enclosure_id: int, name: str = Form(...), common: str = Form(""), scientific: str = Form(""), dob: str = Form(""),
):
    name = name.strip()
    if not name:
        return RedirectResponse(
            url=f"/setup/enclosures/{enclosure_id}/animals?error={quote('Enter a name for the animal.')}",
            status_code=303,
        )
    q.create_animal(enclosure_id, name, common or None, scientific or None, dob or None)
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/animals", status_code=303)


@router.post("/enclosures/{enclosure_id}/plants")
def setup_create_plant(enclosure_id: int, name: str = Form(...), species: str = Form("")):
    try:
        q.create_plant(enclosure_id, name, species or None)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/setup/enclosures/{enclosure_id}/animals?error={quote(str(exc))}", status_code=303
        )
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/animals", status_code=303)


@router.get("/enclosures/{enclosure_id}/sensor")
def setup_sensor_form(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/setup/", status_code=303)
    primary, others = _primary_and_other_metrics(enclosure["enclosure_type"])
    # Fallback Sensor offer (see CONTEXT.md: Fallback Sensor; ADR 0031) — only when this Enclosure
    # has no Sensor of its own and its Room already has one to borrow.
    room_sensors = []
    if enclosure["room_id"] and not enclosure["sensors"]:
        room = q.get_room(enclosure["room_id"])
        room_sensors = room["sensors"] if room else []
    return templates.TemplateResponse(
        request, "setup_sensor.html",
        {
            "enclosure": enclosure, "primary_metric": primary, "other_metrics": others,
            "room_sensors": room_sensors, "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures/{enclosure_id}/fallback-sensor")
def setup_use_fallback_sensor(enclosure_id: int, fallback_sensor_id: int = Form(...)):
    q.set_enclosure_fallback_sensor(enclosure_id, fallback_sensor_id)
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/sensor", status_code=303)


@router.post("/enclosures/{enclosure_id}/sensors")
async def setup_create_sensor(request: Request, enclosure_id: int, label: str = Form(...)):
    label = label.strip()
    if not label:
        return RedirectResponse(
            url=f"/setup/enclosures/{enclosure_id}/sensor?error={quote('Enter a label for the sensor.')}",
            status_code=303,
        )
    enclosure = q.get_enclosure(enclosure_id)
    metrics = et.target_range_metrics_for(enclosure["enclosure_type"] if enclosure else "basic")
    target_ranges = await _target_ranges_from_form(request, metrics)
    try:
        q.create_sensor(enclosure_id, label, "manual", None, target_ranges, {})
    except ValueError as exc:
        return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/sensor?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/sensor", status_code=303)


@router.get("/enclosures/{enclosure_id}/plug")
def setup_plug_form(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/setup/", status_code=303)
    return templates.TemplateResponse(
        request, "setup_plug.html",
        {
            "enclosure": enclosure, "purpose_suggestions": PURPOSE_SUGGESTIONS,
            "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures/{enclosure_id}/plugs")
def setup_create_plug(
    enclosure_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    target_on_time: str = Form(""),
    target_off_time: str = Form(""),
    always_on: bool = Form(False),
):
    try:
        q.create_plug(
            label, purpose, "manual", None, None, None, "1", target_on_time or None, target_off_time or None,
            room_id=None, enclosure_ids=[enclosure_id], controller_kind="none",
            target_temp_c=None, target_humidity_pct=None, always_on=always_on,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/plug?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/setup/enclosures/{enclosure_id}/plug", status_code=303)


@router.get("/enclosures/{enclosure_id}/done")
def setup_done(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/setup/", status_code=303)
    return templates.TemplateResponse(request, "setup_done.html", {"enclosure": enclosure})
