"""Admin UI routes — the browser-based counterpart to tools/register_device.py.

Target temps are entered/shown in Fahrenheit here (matching how you actually think about
enclosure temps) and converted to Celsius for storage, since the schema's canonical unit is
Celsius (the Govee sensors' native unit — see collectors/govee_protocol.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from web import admin_queries as q

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def _c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


templates.env.filters["c_to_f"] = _c_to_f


@router.get("/")
def admin_index(request: Request):
    return templates.TemplateResponse(request, "admin_index.html", {"enclosures": q.list_enclosures()})


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
    return templates.TemplateResponse(request, "admin_enclosure.html", {"enclosure": enclosure})


@router.post("/enclosures/{enclosure_id}/update")
def admin_update_enclosure(
    enclosure_id: int,
    name: str = Form(...),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
):
    q.update_enclosure(enclosure_id, name, bioactive, feeding_interval, watering_interval, spot_clean_interval, deep_clean_interval)
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


@router.post("/enclosures/{enclosure_id}/sensors")
def admin_create_sensor(
    enclosure_id: int,
    label: str = Form(...),
    mac_address: str = Form(...),
    temp_min_f: float | None = Form(None),
    temp_max_f: float | None = Form(None),
    humidity_min: float | None = Form(None),
    humidity_max: float | None = Form(None),
):
    q.create_sensor(enclosure_id, label, mac_address, _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/sensors/{sensor_id}/delete")
def admin_delete_sensor(sensor_id: int, enclosure_id: int = Form(...)):
    q.delete_sensor(sensor_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/plugs")
def admin_create_plug(
    enclosure_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    tuya_device_id: str = Form(...),
    tuya_local_key: str = Form(...),
    tuya_ip_address: str = Form(""),
):
    q.create_plug(enclosure_id, label, purpose, tuya_device_id, tuya_local_key, tuya_ip_address)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/plugs/{plug_id}/delete")
def admin_delete_plug(plug_id: int, enclosure_id: int = Form(...)):
    q.delete_plug(plug_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)
