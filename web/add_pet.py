"""The Add New Pet wizard — see CONTEXT.md: Add New Pet Wizard; ADR 0051.

A second guided front door onto the same web/admin_queries.py writes the first-run Setup Wizard
(web/setup.py; ADR 0031) already uses for Room, Enclosure, Animal, Plant, Sensor, and Plug creation
— not a parallel implementation, and not gated by is_fresh_install(). Reached any time from App
Admin's "Add New Pet" button, for the ongoing case the Setup Wizard deliberately doesn't cover:
an existing install getting one more animal. Room and Enclosure each offer picking something that
already exists, alongside the Setup Wizard's own "create a new one" forms, since an established
install usually already has both; a new pet dropped into an already-set-up Enclosure skips
straight to the Animal step. Deliberately Manual-only for Sensor and Plug, same as the Setup
Wizard and for the same reasons (ADR 0031) — no Room-level Sensor/Plug step here, since those are a
Room concern, not a new pet's.
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
from web import species_kb_queries as skq
from web.wizard_shared import (
    PURPOSE_SUGGESTIONS,
    enclosures_with_room_names as _enclosures_with_room_names,
    f_to_c as _f_to_c,
    primary_and_other_metrics as _primary_and_other_metrics,
    target_ranges_from_form as _target_ranges_from_form,
    wizard_redirect as _wizard_redirect,
)

_WEB_DIR = APP_ROOT / "web"
router = APIRouter(prefix="/add-pet")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")
# Same cache-busting setup as web/admin.py's own separate Jinja2Templates instance — see its
# identical comment.
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (_WEB_DIR / "static").iterdir() if f.is_file())
))

templates.env.filters["c_to_f"] = lambda c: None if c is None else c * 9 / 5 + 32


@router.get("/")
def add_pet_index(request: Request):
    return templates.TemplateResponse(
        request, "add_pet_room.html", {"rooms": q.list_rooms(), "error": request.query_params.get("error")}
    )


@router.post("/rooms")
def add_pet_create_room(name: str = Form(...)):
    name = name.strip()
    if not name:
        return RedirectResponse(url="/add-pet/?error=" + quote("Enter a name for the room."), status_code=303)
    room_id = q.create_room(name)
    return RedirectResponse(url=f"/add-pet/enclosure?room_id={room_id}", status_code=303)


@router.get("/enclosure")
def add_pet_enclosure_form(request: Request, room_id: str = ""):
    room = q.get_room(int(room_id)) if room_id else None
    context = {
        "room": room, "room_id": room_id, "enclosures": _enclosures_with_room_names(),
        "enclosure_types": et.ENCLOSURE_TYPES, "enclosure_type_labels": et.ENCLOSURE_TYPE_LABELS,
        "error": request.query_params.get("error"),
    }
    context.update(skq.species_profile_js_context())
    return templates.TemplateResponse(request, "add_pet_enclosure.html", context)


@router.get("/enclosures/select")
def add_pet_enclosure_select(enclosure_id: int):
    """The "use an existing Enclosure" picker — a plain GET so no extra confirm/unsaved-data
    machinery is needed, since nothing on this step was typed in, just chosen."""
    return RedirectResponse(url=f"/add-pet/enclosures/{enclosure_id}/animals", status_code=303)


@router.post("/enclosures")
def add_pet_create_enclosure(
    name: str = Form(...),
    enclosure_type: str = Form("basic"),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
    room_id: str = Form(""),
    species_profile: str = Form(""),
    life_stage: str = Form("adult"),
):
    try:
        enclosure_id = q.create_enclosure(
            name, enclosure_type, bioactive, feeding_interval, watering_interval,
            spot_clean_interval, deep_clean_interval,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/add-pet/enclosure?room_id={room_id}&error={quote(str(exc))}", status_code=303
        )
    if room_id:
        q.set_enclosure_room(enclosure_id, int(room_id))
    return RedirectResponse(
        url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/animals",
                              species_profile=species_profile, life_stage=life_stage),
        status_code=303,
    )


@router.get("/enclosures/{enclosure_id}/animals")
def add_pet_animals(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/add-pet/", status_code=303)
    species_profile = request.query_params.get("species_profile", "")
    life_stage = request.query_params.get("life_stage", "adult")
    context = {
        "enclosure": enclosure, "error": request.query_params.get("error"),
        "species_profile": species_profile, "life_stage": life_stage,
        "carry_params": _wizard_redirect("", species_profile=species_profile, life_stage=life_stage),
    }
    context.update(skq.species_profile_js_context())
    return templates.TemplateResponse(request, "add_pet_animals.html", context)


@router.post("/enclosures/{enclosure_id}/animals")
def add_pet_create_animal(
    enclosure_id: int, name: str = Form(...), common: str = Form(""), scientific: str = Form(""), dob: str = Form(""),
    sex: str = Form("unknown"), species_profile: str = Form(""), life_stage: str = Form("adult"),
):
    name = name.strip()
    if not name:
        return RedirectResponse(
            url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/animals",
                                  error="Enter a name for the animal.",
                                  species_profile=species_profile, life_stage=life_stage),
            status_code=303,
        )
    q.create_animal(enclosure_id, name, common or None, scientific or None, dob or None, species_profile or None, sex=sex)
    return RedirectResponse(
        url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/animals",
                              species_profile=species_profile, life_stage=life_stage),
        status_code=303,
    )


@router.post("/enclosures/{enclosure_id}/plants")
def add_pet_create_plant(
    enclosure_id: int, name: str = Form(...), species: str = Form(""),
    species_profile: str = Form(""), life_stage: str = Form("adult"),
):
    try:
        q.create_plant(enclosure_id, name, species or None)
    except ValueError as exc:
        return RedirectResponse(
            url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/animals", error=str(exc),
                                  species_profile=species_profile, life_stage=life_stage),
            status_code=303,
        )
    return RedirectResponse(
        url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/animals",
                              species_profile=species_profile, life_stage=life_stage),
        status_code=303,
    )


@router.get("/enclosures/{enclosure_id}/sensor")
def add_pet_sensor_form(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/add-pet/", status_code=303)
    primary, others = _primary_and_other_metrics(enclosure["enclosure_type"])
    # Fallback Sensor offer (see CONTEXT.md: Fallback Sensor; ADR 0031) — only when this Enclosure
    # has no Sensor of its own and its Room already has one to borrow.
    room_sensors = []
    if enclosure["room_id"] and not enclosure["sensors"]:
        room = q.get_room(enclosure["room_id"])
        room_sensors = room["sensors"] if room else []
    context = {
        "enclosure": enclosure, "primary_metric": primary, "other_metrics": others,
        "room_sensors": room_sensors, "error": request.query_params.get("error"),
        "species_profile": request.query_params.get("species_profile", ""),
    }
    context.update(skq.species_profile_js_context())
    return templates.TemplateResponse(request, "add_pet_sensor.html", context)


@router.post("/enclosures/{enclosure_id}/fallback-sensor")
def add_pet_use_fallback_sensor(enclosure_id: int, fallback_sensor_id: int = Form(...)):
    q.set_enclosure_fallback_sensor(enclosure_id, fallback_sensor_id)
    return RedirectResponse(url=f"/add-pet/enclosures/{enclosure_id}/sensor", status_code=303)


@router.post("/enclosures/{enclosure_id}/sensors")
async def add_pet_create_sensor(request: Request, enclosure_id: int, label: str = Form(...)):
    label = label.strip()
    form = await request.form()
    species_profile = form.get("species_profile", "")
    if not label:
        return RedirectResponse(
            url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/sensor",
                                  error="Enter a label for the sensor.", species_profile=species_profile),
            status_code=303,
        )
    enclosure = q.get_enclosure(enclosure_id)
    metrics = et.target_range_metrics_for(enclosure["enclosure_type"] if enclosure else "basic")
    target_ranges = await _target_ranges_from_form(request, metrics)
    try:
        q.create_sensor(enclosure_id, label, "manual", None, target_ranges, {})
    except ValueError as exc:
        return RedirectResponse(
            url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/sensor",
                                  error=str(exc), species_profile=species_profile),
            status_code=303,
        )
    return RedirectResponse(
        url=_wizard_redirect(f"/add-pet/enclosures/{enclosure_id}/sensor", species_profile=species_profile),
        status_code=303,
    )


@router.get("/enclosures/{enclosure_id}/plug")
def add_pet_plug_form(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/add-pet/", status_code=303)
    return templates.TemplateResponse(
        request, "add_pet_plug.html",
        {
            "enclosure": enclosure, "purpose_suggestions": PURPOSE_SUGGESTIONS,
            "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures/{enclosure_id}/plugs")
def add_pet_create_plug(
    enclosure_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    target_on_time: str = Form(""),
    target_off_time: str = Form(""),
    target_on_time_2: str = Form(""),
    target_off_time_2: str = Form(""),
    target_on_time_3: str = Form(""),
    target_off_time_3: str = Form(""),
    always_on: bool = Form(False),
    controller_kind: str = Form("none"),
    target_temp_f: float | None = Form(None),
    target_humidity_pct: float | None = Form(None),
):
    try:
        q.create_plug(
            label, purpose, "manual", None, None, None, "1", target_on_time or None, target_off_time or None,
            room_id=None, enclosure_ids=[enclosure_id], controller_kind=controller_kind,
            target_temp_c=_f_to_c(target_temp_f), target_humidity_pct=target_humidity_pct, always_on=always_on,
            target_on_time_2=target_on_time_2 or None, target_off_time_2=target_off_time_2 or None,
            target_on_time_3=target_on_time_3 or None, target_off_time_3=target_off_time_3 or None,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/add-pet/enclosures/{enclosure_id}/plug?error={quote(str(exc))}", status_code=303
        )
    return RedirectResponse(url=f"/add-pet/enclosures/{enclosure_id}/plug", status_code=303)


@router.get("/enclosures/{enclosure_id}/done")
def add_pet_done(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/add-pet/", status_code=303)
    return templates.TemplateResponse(request, "add_pet_done.html", {"enclosure": enclosure})
