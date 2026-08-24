"""Admin UI routes — the browser-based counterpart to tools/register_device.py.

Target temps are entered/shown in Fahrenheit here (matching how you actually think about
enclosure temps) and converted to Celsius for storage, since the schema's canonical unit is
Celsius (the Govee sensors' native unit — see collectors/govee_protocol.py).
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from web import admin_queries as q
from web.queries import CARE_EVENT_KINDS, log_care_event
from web.status import care_interval_status, target_range_status

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.globals["care_interval_status"] = care_interval_status
templates.env.globals["target_range_status"] = target_range_status


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def _c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


templates.env.filters["c_to_f"] = _c_to_f


@router.get("/")
def admin_index(request: Request):
    enclosures = q.list_enclosures()
    rooms = q.list_rooms()
    enclosure_count_by_room: dict[int, int] = {}
    for e in enclosures:
        if e["room_id"]:
            enclosure_count_by_room[e["room_id"]] = enclosure_count_by_room.get(e["room_id"], 0) + 1
    return templates.TemplateResponse(
        request, "admin_index.html",
        {
            "enclosures": enclosures, "rooms": rooms,
            "rooms_by_id": {r["id"]: r["name"] for r in rooms},
            "enclosure_count_by_room": enclosure_count_by_room,
            "settings": q.get_settings(), "error": request.query_params.get("error"),
        }
    )


@router.post("/settings")
def admin_update_settings(ble_refresh_timeout_seconds: int = Form(30)):
    try:
        q.update_settings(ble_refresh_timeout_seconds)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/enclosures")
def admin_create_enclosure(
    name: str = Form(...),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
):
    enclosure_id = q.create_enclosure(name, bioactive, feeding_interval, watering_interval, spot_clean_interval, deep_clean_interval)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.get("/enclosures/{enclosure_id}")
def admin_enclosure_detail(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/admin", status_code=303)
    # Fallback Sensor dropdown is scoped to the Enclosure's *current* Room's Sensors, and only
    # matters when it has none of its own — see CONTEXT.md: Fallback Sensor.
    room_sensors = []
    if enclosure["room_id"] and not enclosure["sensors"]:
        room = q.get_room(enclosure["room_id"])
        room_sensors = room["sensors"] if room else []
    return templates.TemplateResponse(
        request, "admin_enclosure.html",
        {
            "enclosure": enclosure, "care_kinds": CARE_EVENT_KINDS, "rooms": q.list_rooms(),
            "room_sensors": room_sensors, "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures/{enclosure_id}/care-events/{kind}")
def admin_create_care_event(
    enclosure_id: int, kind: str, note: str = Form(default=None), occurred_at: str = Form(default="")
):
    try:
        log_care_event(enclosure_id, kind, note, occurred_at)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}#care-{kind}", status_code=303
        )
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}#care-{kind}", status_code=303)


@router.post("/enclosures/{enclosure_id}/update")
def admin_update_enclosure(
    enclosure_id: int,
    name: str = Form(...),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
    room_id: str = Form(""),
    fallback_sensor_id: str = Form(""),
):
    q.update_enclosure(
        enclosure_id, name, bioactive, feeding_interval, watering_interval, spot_clean_interval, deep_clean_interval,
        int(room_id) if room_id else None, int(fallback_sensor_id) if fallback_sensor_id else None,
    )
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/delete")
def admin_delete_enclosure(enclosure_id: int):
    q.delete_enclosure(enclosure_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/enclosures/{enclosure_id}/animals")
def admin_create_animal(
    enclosure_id: int,
    name: str = Form(...),
    common: str = Form(""),
    scientific: str = Form(""),
    dob: str = Form(""),
):
    q.create_animal(enclosure_id, name, common, scientific, dob)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/animals/{animal_id}/delete")
def admin_delete_animal(animal_id: int, enclosure_id: int = Form(...)):
    q.delete_animal(animal_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.get("/animals/{animal_id}/edit")
def admin_edit_animal(request: Request, animal_id: int):
    animal = q.get_animal(animal_id)
    if animal is None:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin_animal_edit.html", {"animal": animal, "enclosures": q.list_enclosures()}
    )


@router.post("/animals/{animal_id}/update")
def admin_update_animal(
    animal_id: int,
    enclosure_id: int = Form(...),
    name: str = Form(...),
    common: str = Form(""),
    scientific: str = Form(""),
    dob: str = Form(""),
):
    q.update_animal(animal_id, enclosure_id, name, common, scientific, dob)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/sensors")
def admin_create_sensor(
    enclosure_id: int,
    label: str = Form(...),
    tracking_mode: str = Form("smart"),
    mac_address: str = Form(""),
    temp_min_f: float | None = Form(None),
    temp_max_f: float | None = Form(None),
    humidity_min: float | None = Form(None),
    humidity_max: float | None = Form(None),
):
    try:
        q.create_sensor(enclosure_id, label, tracking_mode, mac_address or None,
                         _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/sensors/{sensor_id}/delete")
def admin_delete_sensor(sensor_id: int, enclosure_id: int = Form(...)):
    q.delete_sensor(sensor_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.get("/sensors/{sensor_id}/edit")
def admin_edit_sensor(request: Request, sensor_id: int):
    sensor = q.get_sensor(sensor_id)
    if sensor is None:
        return RedirectResponse(url="/admin", status_code=303)
    sensor["target_temp_min_f"] = _c_to_f(sensor["target_temp_min_c"])
    sensor["target_temp_max_f"] = _c_to_f(sensor["target_temp_max_c"])
    return templates.TemplateResponse(
        request, "admin_sensor_edit.html",
        {"sensor": sensor, "enclosures": q.list_enclosures(), "error": request.query_params.get("error")}
    )


@router.post("/sensors/{sensor_id}/update")
def admin_update_sensor(
    sensor_id: int,
    enclosure_id: int = Form(...),
    label: str = Form(...),
    tracking_mode: str = Form("smart"),
    mac_address: str = Form(""),
    temp_min_f: float | None = Form(None),
    temp_max_f: float | None = Form(None),
    humidity_min: float | None = Form(None),
    humidity_max: float | None = Form(None),
):
    try:
        q.update_sensor(sensor_id, enclosure_id, label, tracking_mode, mac_address or None,
                         _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/sensors/{sensor_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/plugs")
def admin_create_plug(
    enclosure_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    tracking_mode: str = Form("smart"),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
    switch_dps_key: str = Form("1"),
    declared_on_time: str = Form(""),
    declared_off_time: str = Form(""),
):
    try:
        q.create_plug(enclosure_id, label, purpose, tracking_mode, tuya_device_id or None, tuya_local_key or None,
                       tuya_ip_address, switch_dps_key, declared_on_time or None, declared_off_time or None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/plugs/{plug_id}/delete")
def admin_delete_plug(plug_id: int, enclosure_id: int = Form(...)):
    q.delete_plug(plug_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.get("/plugs/{plug_id}/edit")
def admin_edit_plug(request: Request, plug_id: int):
    plug = q.get_plug(plug_id)
    if plug is None:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin_plug_edit.html",
        {"plug": plug, "enclosures": q.list_enclosures(), "error": request.query_params.get("error")}
    )


@router.post("/plugs/{plug_id}/update")
def admin_update_plug(
    plug_id: int,
    enclosure_id: int = Form(...),
    label: str = Form(...),
    purpose: str = Form(...),
    tracking_mode: str = Form("smart"),
    switch_dps_key: str = Form("1"),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
    declared_on_time: str = Form(""),
    declared_off_time: str = Form(""),
):
    try:
        q.update_plug(plug_id, enclosure_id, label, purpose, tracking_mode, switch_dps_key,
                       tuya_device_id or None, tuya_local_key or None, tuya_ip_address,
                       declared_on_time or None, declared_off_time or None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/plugs/{plug_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/rooms")
def admin_create_room(name: str = Form(...)):
    room_id = q.create_room(name)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


@router.get("/rooms/{room_id}")
def admin_room_detail(request: Request, room_id: int):
    room = q.get_room(room_id)
    if room is None:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin_room.html", {"room": room, "error": request.query_params.get("error")}
    )


@router.post("/rooms/{room_id}/update")
def admin_update_room(
    room_id: int,
    name: str = Form(...),
    light_on_time: str = Form(""),
    light_off_time: str = Form(""),
    light_notes: str = Form(""),
):
    try:
        q.update_room(room_id, name, light_on_time or None, light_off_time or None, light_notes or None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/rooms/{room_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


@router.post("/rooms/{room_id}/delete")
def admin_delete_room(room_id: int):
    q.delete_room(room_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/rooms/{room_id}/sensors")
def admin_create_room_sensor(
    room_id: int,
    label: str = Form(...),
    tracking_mode: str = Form("smart"),
    mac_address: str = Form(""),
    temp_min_f: float | None = Form(None),
    temp_max_f: float | None = Form(None),
    humidity_min: float | None = Form(None),
    humidity_max: float | None = Form(None),
):
    try:
        q.create_room_sensor(room_id, label, tracking_mode, mac_address or None,
                              _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/rooms/{room_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


@router.post("/room-sensors/{sensor_id}/delete")
def admin_delete_room_sensor(sensor_id: int, room_id: int = Form(...)):
    q.delete_sensor(sensor_id)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


@router.get("/room-sensors/{sensor_id}/edit")
def admin_edit_room_sensor(request: Request, sensor_id: int):
    sensor = q.get_sensor(sensor_id)
    if sensor is None:
        return RedirectResponse(url="/admin", status_code=303)
    sensor["target_temp_min_f"] = _c_to_f(sensor["target_temp_min_c"])
    sensor["target_temp_max_f"] = _c_to_f(sensor["target_temp_max_c"])
    return templates.TemplateResponse(
        request, "admin_room_sensor_edit.html",
        {"sensor": sensor, "rooms": q.list_rooms(), "error": request.query_params.get("error")}
    )


@router.post("/room-sensors/{sensor_id}/update")
def admin_update_room_sensor(
    sensor_id: int,
    room_id: int = Form(...),
    label: str = Form(...),
    tracking_mode: str = Form("smart"),
    mac_address: str = Form(""),
    temp_min_f: float | None = Form(None),
    temp_max_f: float | None = Form(None),
    humidity_min: float | None = Form(None),
    humidity_max: float | None = Form(None),
):
    try:
        q.update_room_sensor(sensor_id, room_id, label, tracking_mode, mac_address or None,
                              _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/room-sensors/{sensor_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)
