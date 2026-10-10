"""Admin UI routes — the browser-based counterpart to tools/register_device.py.

Target temps are entered/shown in Fahrenheit here (matching how you actually think about
enclosure temps) and converted to Celsius for storage, since the schema's canonical unit is
Celsius (the Govee sensors' native unit — see plugins/govee_ble/protocol.py).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app_paths import APP_ROOT
from schemas import enclosure_types as et
from web import admin_queries as q
from web import graphs_queries as gq
from web import view_data_queries as vd
from web.govee_refresh import refresh_sensors
from web.plug_probe import probe_plug
from web.queries import ANIMAL_CONDITION_LABELS, ANIMAL_CONDITIONS, CARE_EVENT_KINDS, log_care_event, log_reading
from web.status import acknowledged_drift_status, care_interval_status, schedule_drift_status, target_range_status

_WEB_DIR = APP_ROOT / "web"
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")
templates.env.globals["care_interval_status"] = care_interval_status
templates.env.globals["target_range_status"] = target_range_status
templates.env.globals["schedule_drift_status"] = schedule_drift_status
templates.env.globals["acknowledged_drift_status"] = acknowledged_drift_status
templates.env.globals["ENCLOSURE_TYPES"] = et.ENCLOSURE_TYPES
templates.env.globals["ENCLOSURE_TYPE_LABELS"] = et.ENCLOSURE_TYPE_LABELS
templates.env.globals["target_range_metrics_for"] = et.target_range_metrics_for
templates.env.globals["TARGET_RANGE_METRICS"] = et.TARGET_RANGE_METRICS
# Cache-busting for /static/app.js and /static/style.css (see web/main.py's identical setup and
# comment) — this router has its own separate Jinja2Templates instance, so its own globals need
# this too; missing it here left every admin_*.html page rendering "?v=" (empty) instead of a real
# version, silently defeating the cache-busting these pages' <link>/<script> tags already expect.
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (_WEB_DIR / "static").iterdir() if f.is_file())
))
# See web/main.py's identical filter + comment — Graphs (graphs.html) needs this too.
templates.env.filters["tojson"] = json.dumps


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


def _c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


templates.env.filters["c_to_f"] = _c_to_f


def _clock_12h(hhmm: str | None) -> str | None:
    """Shows a stored 24-hour "HH:MM" time as "8:00 AM" for the Schedules pills. Anything that isn't
    a parseable time (None, empty, a stray value) is returned unchanged so the template can still
    fall back to its "—" placeholder."""
    try:
        when = datetime.strptime(hhmm, "%H:%M")
    except (TypeError, ValueError):
        return hhmm
    return f"{when.hour % 12 or 12}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"


templates.env.filters["clock_12h"] = _clock_12h


def _utc_stamp_as_clock(recorded_at: str | None) -> str | None:
    """A UTC "YYYY-MM-DD HH:MM:SS" stamp (command requests, plug readings — see plugins/common.py and
    web/outbox.py) shown as the local 12-hour time, e.g. "6:05 PM"."""
    if not recorded_at:
        return recorded_at
    return _clock_12h(q.utc_clock_to_local(recorded_at))


templates.env.filters["utc_clock"] = _utc_stamp_as_clock


def _sensor_target_ranges(
    temp_min_f: float | None, temp_max_f: float | None, humidity_min: float | None, humidity_max: float | None,
    uvb_min: float | None, uvb_max: float | None,
    ph_min: float | None, ph_max: float | None, ammonia_min: float | None, ammonia_max: float | None,
    nitrite_min: float | None, nitrite_max: float | None, nitrate_min: float | None, nitrate_max: float | None,
    specific_gravity_min: float | None, specific_gravity_max: float | None,
    salinity_min: float | None, salinity_max: float | None, alkalinity_min: float | None, alkalinity_max: float | None,
    calcium_min: float | None, calcium_max: float | None, magnesium_min: float | None, magnesium_max: float | None,
    phosphate_min: float | None, phosphate_max: float | None,
) -> q.TargetRanges:
    """Assembles the schemas.enclosure_types-shaped target_ranges dict (see schemas/enclosure_types.py)
    from the Sensor form's many individual Form() fields. Only temperature gets a unit conversion
    (stored as Celsius, entered/shown as Fahrenheit) — every other metric is already the stored unit."""
    return {
        "temperature": (_f_to_c(temp_min_f), _f_to_c(temp_max_f)),
        "humidity": (humidity_min, humidity_max),
        "uvb": (uvb_min, uvb_max),
        "ph": (ph_min, ph_max),
        "ammonia": (ammonia_min, ammonia_max),
        "nitrite": (nitrite_min, nitrite_max),
        "nitrate": (nitrate_min, nitrate_max),
        "specific_gravity": (specific_gravity_min, specific_gravity_max),
        "salinity": (salinity_min, salinity_max),
        "alkalinity": (alkalinity_min, alkalinity_max),
        "calcium": (calcium_min, calcium_max),
        "magnesium": (magnesium_min, magnesium_max),
        "phosphate": (phosphate_min, phosphate_max),
    }


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
            "enclosures": enclosures, "rooms": rooms, "sensors": q.list_sensors(), "plugs": q.list_plugs(),
            "plug_groups": q.list_plug_groups(),
            "rooms_by_id": {r["id"]: r["name"] for r in rooms},
            "enclosure_count_by_room": enclosure_count_by_room,
            "settings": q.get_settings(), "error": request.query_params.get("error"),
        }
    )


@router.post("/settings")
def admin_update_settings(
    ble_refresh_timeout_seconds: int = Form(30),
    alert_debounce_minutes: int = Form(10),
    ntfy_server_url: str = Form(""),
    ntfy_topic: str = Form(""),
    schedule_drift_threshold_minutes: int = Form(15),
):
    try:
        q.update_settings(ble_refresh_timeout_seconds, alert_debounce_minutes,
                           ntfy_server_url or None, ntfy_topic or None, schedule_drift_threshold_minutes)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/enclosures")
def admin_enclosures(request: Request):
    """The All Enclosures page — the Enclosures card that used to sit on the Control Panel (see
    admin_index). The same /admin/enclosures path also takes the POST that creates one."""
    rooms = q.list_rooms()
    return templates.TemplateResponse(
        request, "admin_enclosures.html",
        {
            "enclosures": q.list_enclosures(), "rooms_by_id": {r["id"]: r["name"] for r in rooms},
            "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures")
def admin_create_enclosure(
    name: str = Form(...),
    enclosure_type: str = Form("basic"),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
):
    # Care Dashboard-visibility (show_*_on_dashboard) isn't offered on this quick-create form — same
    # "secondary settings happen on the Enclosure's own page after it's created" deferral as Room
    # assignment below — so every kind just starts shown, matching the schema's own default.
    try:
        enclosure_id = q.create_enclosure(name, enclosure_type, bioactive, feeding_interval,
                                           watering_interval, spot_clean_interval, deep_clean_interval)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.get("/enclosures/{enclosure_id}")
def admin_enclosure_detail(request: Request, enclosure_id: int):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/admin/enclosures", status_code=303)
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
            "room_sensors": room_sensors,
            "schedule_drift_threshold_minutes": q.get_settings()["schedule_drift_threshold_minutes"],
            "error": request.query_params.get("error"),
        }
    )


@router.post("/enclosures/{enclosure_id}/care-events/{kind}")
def admin_create_care_event(
    enclosure_id: int, kind: str, note: str = Form(default=None), occurred_at: str = Form(default=""),
    days_ago: str = Form(default=""), animal_id: str = Form(default=""),
):
    # A quick-log button (Today/Yesterday/2 days ago) wins over the Advanced datetime picker if
    # both are somehow present — the three buttons are the common case this exists to simplify.
    if days_ago:
        occurred_at = (datetime.now() - timedelta(days=int(days_ago))).strftime("%Y-%m-%dT%H:%M")
    try:
        log_care_event(enclosure_id, kind, note, occurred_at, int(animal_id) if animal_id else None)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}#care-{kind}", status_code=303
        )
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}#care-{kind}", status_code=303)


@router.post("/enclosures/{enclosure_id}/update")
def admin_update_enclosure(
    enclosure_id: int,
    name: str = Form(...),
    enclosure_type: str = Form("basic"),
    bioactive: bool = Form(False),
    feeding_interval: int = Form(7),
    watering_interval: int = Form(3),
    spot_clean_interval: int = Form(7),
    deep_clean_interval: int = Form(30),
    room_id: str = Form(""),
    fallback_sensor_id: str = Form(""),
    show_feeding_on_dashboard: bool = Form(False),
    show_watering_on_dashboard: bool = Form(False),
    show_spot_clean_on_dashboard: bool = Form(False),
    show_deep_clean_on_dashboard: bool = Form(False),
):
    try:
        q.update_enclosure(
            enclosure_id, name, enclosure_type, bioactive, feeding_interval, watering_interval,
            spot_clean_interval, deep_clean_interval,
            int(room_id) if room_id else None, int(fallback_sensor_id) if fallback_sensor_id else None,
            show_feeding_on_dashboard, show_watering_on_dashboard,
            show_spot_clean_on_dashboard, show_deep_clean_on_dashboard,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/delete")
def admin_delete_enclosure(enclosure_id: int):
    q.delete_enclosure(enclosure_id)
    return RedirectResponse(url="/admin/enclosures", status_code=303)


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


@router.post("/animals/{animal_id}/dashboard-visibility")
def admin_set_animal_dashboard_visibility(
    animal_id: int, enclosure_id: int = Form(...), show_on_dashboard: bool = Form(False),
):
    q.set_animal_dashboard_visibility(animal_id, show_on_dashboard)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/plants")
def admin_create_plant(enclosure_id: int, name: str = Form(...), species: str = Form("")):
    try:
        q.create_plant(enclosure_id, name, species or None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/plants/{plant_id}/delete")
def admin_delete_plant(plant_id: int, enclosure_id: int = Form(...)):
    q.delete_plant(plant_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/enclosures/{enclosure_id}/plant-health")
def admin_log_plant_health(
    enclosure_id: int, note: str = Form(...), plant_id: str = Form(""), occurred_at: str = Form(""),
):
    try:
        q.log_plant_health(enclosure_id, note, int(plant_id) if plant_id else None, occurred_at)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}#plant-health", status_code=303
        )
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}#plant-health", status_code=303)


@router.get("/animals/{animal_id}/edit")
def admin_edit_animal(request: Request, animal_id: int):
    animal = q.get_animal(animal_id)
    if animal is None:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin_animal_edit.html",
        {
            "animal": animal, "enclosures": q.list_enclosures(),
            "logs": q.list_animal_logs(animal_id),
            "animal_conditions": ANIMAL_CONDITIONS, "animal_condition_labels": ANIMAL_CONDITION_LABELS,
            "error": request.query_params.get("error"),
        }
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


@router.post("/animals/{animal_id}/log-weight")
def admin_log_animal_weight(animal_id: int, weight_g: float = Form(...), occurred_at: str = Form("")):
    try:
        q.log_animal_weight(animal_id, weight_g, occurred_at)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/animals/{animal_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/animals/{animal_id}/edit", status_code=303)


@router.post("/animals/{animal_id}/log-length")
def admin_log_animal_length(animal_id: int, length_cm: float = Form(...), occurred_at: str = Form("")):
    try:
        q.log_animal_length(animal_id, length_cm, occurred_at)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/animals/{animal_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/animals/{animal_id}/edit", status_code=303)


@router.post("/animals/{animal_id}/log-count")
def admin_log_animal_count(animal_id: int, count: int = Form(...), occurred_at: str = Form("")):
    try:
        q.log_animal_count(animal_id, count, occurred_at)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/animals/{animal_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/animals/{animal_id}/edit", status_code=303)


@router.post("/animals/{animal_id}/log-condition")
def admin_log_animal_condition(
    animal_id: int, condition: str = Form(...), note: str = Form(""), occurred_at: str = Form(""),
):
    try:
        q.log_animal_condition(animal_id, condition, note, occurred_at)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/animals/{animal_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/animals/{animal_id}/edit", status_code=303)


@router.post("/sensors")
def admin_create_sensor_global(
    label: str = Form(...),
    mac_address: str = Form(""),
    parent_type: str = Form("enclosure"),
    enclosure_id: str = Form(""),
    room_id: str = Form(""),
):
    """The top-level Sensors section's own Add form (see admin_index.html) — Smart only. A Manual
    Sensor needs a complete Target Range (min+max) at creation (_validate_sensor), which depends on
    the parent's Enclosure Type and isn't known generically here; adding one still goes through the
    existing per-Enclosure/Room Add Sensor form, which already offers the right fields for that
    parent."""
    try:
        if parent_type == "room":
            if not room_id:
                raise ValueError("Pick a Room.")
            q.create_room_sensor(int(room_id), label, "smart", mac_address or None, None, None, None, None)
        else:
            if not enclosure_id:
                raise ValueError("Pick an Enclosure.")
            q.create_sensor(int(enclosure_id), label, "smart", mac_address or None, {})
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


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
    uvb_min: float | None = Form(None),
    uvb_max: float | None = Form(None),
    ph_min: float | None = Form(None),
    ph_max: float | None = Form(None),
    ammonia_min: float | None = Form(None),
    ammonia_max: float | None = Form(None),
    nitrite_min: float | None = Form(None),
    nitrite_max: float | None = Form(None),
    nitrate_min: float | None = Form(None),
    nitrate_max: float | None = Form(None),
    specific_gravity_min: float | None = Form(None),
    specific_gravity_max: float | None = Form(None),
    salinity_min: float | None = Form(None),
    salinity_max: float | None = Form(None),
    alkalinity_min: float | None = Form(None),
    alkalinity_max: float | None = Form(None),
    calcium_min: float | None = Form(None),
    calcium_max: float | None = Form(None),
    magnesium_min: float | None = Form(None),
    magnesium_max: float | None = Form(None),
    phosphate_min: float | None = Form(None),
    phosphate_max: float | None = Form(None),
):
    target_ranges = _sensor_target_ranges(
        temp_min_f, temp_max_f, humidity_min, humidity_max, uvb_min, uvb_max, ph_min, ph_max, ammonia_min, ammonia_max,
        nitrite_min, nitrite_max, nitrate_min, nitrate_max, specific_gravity_min, specific_gravity_max,
        salinity_min, salinity_max,
        alkalinity_min, alkalinity_max, calcium_min, calcium_max, magnesium_min, magnesium_max,
        phosphate_min, phosphate_max,
    )
    try:
        q.create_sensor(enclosure_id, label, tracking_mode, mac_address or None, target_ranges)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/sensors/{sensor_id}/delete")
def admin_delete_sensor(sensor_id: int, enclosure_id: int = Form(...)):
    q.delete_sensor(sensor_id)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/sensors/{sensor_id}/dashboard-visibility")
def admin_set_sensor_dashboard_visibility(
    sensor_id: int, enclosure_id: int = Form(...), show_on_dashboard: bool = Form(False),
):
    q.set_sensor_dashboard_visibility(sensor_id, show_on_dashboard)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/sensors/{sensor_id}/readings")
def admin_create_reading(
    sensor_id: int,
    enclosure_id: int = Form(...),
    temperature_f: float | None = Form(default=None),
    humidity_pct: float | None = Form(default=None),
    uvb_index: float | None = Form(default=None),
    ph: float | None = Form(default=None),
    ammonia_ppm: float | None = Form(default=None),
    nitrite_ppm: float | None = Form(default=None),
    nitrate_ppm: float | None = Form(default=None),
    specific_gravity: float | None = Form(default=None),
    salinity_ppm: float | None = Form(default=None),
    alkalinity_dkh: float | None = Form(default=None),
    calcium_ppm: float | None = Form(default=None),
    magnesium_ppm: float | None = Form(default=None),
    phosphate_ppm: float | None = Form(default=None),
    recorded_at: str = Form(default=""),
):
    # Same hand-logged Reading as the dashboard's Log form (web/main.py's create_reading) — posted
    # from the Enclosure's own Sensors section instead, so it lands back on that page. Field names and
    # the Fahrenheit->Celsius conversion match main.py exactly; see schemas/enclosure_types.py.
    values = {
        "temperature_c": _f_to_c(temperature_f),
        "humidity_pct": humidity_pct,
        "uvb_index": uvb_index,
        "ph": ph,
        "ammonia_ppm": ammonia_ppm,
        "nitrite_ppm": nitrite_ppm,
        "nitrate_ppm": nitrate_ppm,
        "specific_gravity": specific_gravity,
        "salinity_ppm": salinity_ppm,
        "alkalinity_dkh": alkalinity_dkh,
        "calcium_ppm": calcium_ppm,
        "magnesium_ppm": magnesium_ppm,
        "phosphate_ppm": phosphate_ppm,
    }
    try:
        log_reading(sensor_id, values, recorded_at)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/enclosures/{enclosure_id}?error={quote(str(exc))}#sensors", status_code=303
        )
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}#sensors", status_code=303)


async def _refresh_one_sensor(sensor_id: int) -> str | None:
    """Live BLE listen for exactly one Sensor's own MAC — the Edit Sensor page's "test this Sensor"
    Refresh button (see admin_sensor_edit.html/admin_room_sensor_edit.html), same mechanism as
    web/main.py's Enclosure/Room-level Refresh (_refresh_smart_sensors), just scoped to a single
    device instead of every Smart Sensor a parent owns — the point here is testing one Sensor in
    isolation, e.g. right after entering its MAC address. Returns a friendly error message on
    timeout/misconfiguration, else None; a successful reading is already written to sensor_reading
    by refresh_sensors() itself."""
    sensor = q.get_sensor(sensor_id)
    if sensor is None or sensor["tracking_mode"] != "smart" or not sensor["mac_address"]:
        return "Refresh needs a Smart Sensor with a MAC address set."
    timeout = q.get_settings()["ble_refresh_timeout_seconds"]
    mac = sensor["mac_address"].upper()
    results = await refresh_sensors({mac: sensor_id}, timeout)
    if mac not in results:
        return f"No fresh reading within {timeout}s — check the Sensor is powered and in range."
    return None


@router.post("/sensors/{sensor_id}/refresh")
async def admin_refresh_sensor(sensor_id: int):
    error = await _refresh_one_sensor(sensor_id)
    url = f"/admin/sensors/{sensor_id}/edit"
    return RedirectResponse(url=f"{url}?error={quote(error)}" if error else url, status_code=303)


@router.get("/sensors/{sensor_id}/edit")
def admin_edit_sensor(request: Request, sensor_id: int):
    sensor = q.get_sensor(sensor_id)
    if sensor is None:
        return RedirectResponse(url="/admin", status_code=303)
    sensor["target_temp_min_f"] = _c_to_f(sensor["target_temp_min_c"])
    sensor["target_temp_max_f"] = _c_to_f(sensor["target_temp_max_c"])
    # Which metric fields render depends on the Sensor's *current* Enclosure's Type — see
    # CONTEXT.md: Enclosure Type. If reassigned to a different-type Enclosure in the same submit,
    # a now-inapplicable value is still caught server-side (ValueError) rather than silently saved;
    # this page just doesn't live-update field visibility as the Enclosure dropdown changes.
    enclosure = q.get_enclosure(sensor["enclosure_id"]) if sensor["enclosure_id"] else None
    return templates.TemplateResponse(
        request, "admin_sensor_edit.html",
        {
            "sensor": sensor, "enclosures": q.list_enclosures(),
            "sensor_enclosure_type": enclosure["enclosure_type"] if enclosure else "basic",
            "error": request.query_params.get("error"),
        }
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
    uvb_min: float | None = Form(None),
    uvb_max: float | None = Form(None),
    ph_min: float | None = Form(None),
    ph_max: float | None = Form(None),
    ammonia_min: float | None = Form(None),
    ammonia_max: float | None = Form(None),
    nitrite_min: float | None = Form(None),
    nitrite_max: float | None = Form(None),
    nitrate_min: float | None = Form(None),
    nitrate_max: float | None = Form(None),
    specific_gravity_min: float | None = Form(None),
    specific_gravity_max: float | None = Form(None),
    salinity_min: float | None = Form(None),
    salinity_max: float | None = Form(None),
    alkalinity_min: float | None = Form(None),
    alkalinity_max: float | None = Form(None),
    calcium_min: float | None = Form(None),
    calcium_max: float | None = Form(None),
    magnesium_min: float | None = Form(None),
    magnesium_max: float | None = Form(None),
    phosphate_min: float | None = Form(None),
    phosphate_max: float | None = Form(None),
    auto_update_enabled: bool = Form(False),
):
    target_ranges = _sensor_target_ranges(
        temp_min_f, temp_max_f, humidity_min, humidity_max, uvb_min, uvb_max, ph_min, ph_max, ammonia_min, ammonia_max,
        nitrite_min, nitrite_max, nitrate_min, nitrate_max, specific_gravity_min, specific_gravity_max,
        salinity_min, salinity_max,
        alkalinity_min, alkalinity_max, calcium_min, calcium_max, magnesium_min, magnesium_max,
        phosphate_min, phosphate_max,
    )
    try:
        q.update_sensor(sensor_id, enclosure_id, label, tracking_mode, mac_address or None, target_ranges,
                         auto_update_enabled)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/sensors/{sensor_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)


@router.post("/plugs")
def admin_create_plug(
    label: str = Form(...),
    purpose: str = Form(...),
    tracking_mode: str = Form("smart"),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
    switch_dps_key: str = Form("1"),
    target_on_time: str = Form(""),
    target_off_time: str = Form(""),
    always_on: bool = Form(False),
    room_id: str = Form(""),
    enclosure_ids: list[int] = Form(default=[]),
    controller_kind: str = Form("none"),
    target_temp_f: float | None = Form(None),
    target_humidity_pct: float | None = Form(None),
    plug_group_id: str = Form(""),
):
    try:
        if plug_group_id:
            # Belongs-to and Tuya credential fields are ignored here in favor of the Group's own —
            # see CONTEXT.md: Plug Group; ADR 0017. add_plug_to_group() inherits both.
            q.add_plug_to_group(int(plug_group_id), label, purpose, tracking_mode, switch_dps_key)
        else:
            q.create_plug(label, purpose, tracking_mode, tuya_device_id or None, tuya_local_key or None,
                           tuya_ip_address, switch_dps_key, target_on_time or None, target_off_time or None,
                           int(room_id) if room_id else None, enclosure_ids,
                           controller_kind, _f_to_c(target_temp_f), target_humidity_pct, always_on)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plugs/{plug_id}/delete")
def admin_delete_plug(plug_id: int):
    q.delete_plug(plug_id)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plugs/{plug_id}/group")
def admin_set_plug_group(plug_id: int, plug_group_id: str = Form("")):
    """Attaches/detaches an existing standalone Plug to/from a Plug Group — see CONTEXT.md: Plug
    Group; ADR 0017. Separate from the main update form for the same reason
    dashboard-visibility is: a one-field, dropdown-driven action, not part of the full edit form."""
    try:
        q.set_plug_group(plug_id, int(plug_group_id) if plug_group_id else None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/plugs/{plug_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/plugs/{plug_id}/edit", status_code=303)


@router.post("/plugs/{plug_id}/clear-timer-warning")
def admin_clear_timer_warning(plug_id: int):
    """Called from the Timer Warning's "Clear warning" button on the Plug's Edit page (see
    CONTEXT.md: Timer Warning). Sent as a formaction of that page's own form, so only this route's
    side effect runs — the rest of the form's fields are ignored here."""
    q.clear_timer_warning(plug_id)
    return RedirectResponse(url=f"/admin/plugs/{plug_id}/edit", status_code=303)


@router.post("/plugs/{plug_id}/dashboard-visibility")
def admin_set_plug_dashboard_visibility(
    plug_id: int, show_on_dashboard: bool = Form(False),
    enclosure_id: str = Form(""), room_id: str = Form(""),
):
    """A Plug's parent isn't a single fixed page the way an Animal's or Sensor's is — it's either
    one Room or one-or-more Enclosures (see CONTEXT.md: Plug) — so this one route (unlike Sensor's
    forked /sensors/ vs /room-sensors/ pair) takes whichever hidden id the calling page's form set
    and redirects back there, falling back to the main Admin page same as every other Plug route."""
    q.set_plug_dashboard_visibility(plug_id, show_on_dashboard)
    if enclosure_id:
        return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}", status_code=303)
    if room_id:
        return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plugs/{plug_id}/command")
def admin_send_plug_command(
    plug_id: int,
    is_on: bool = Form(...),
    note: str = Form(""),
    return_to: str = Form(""),
):
    """The on/off control on a Plug's edit page — see CONTEXT.md: Command, Interruption; ADR 0014. No
    confirmation dialog by design (see ADR 0014's Considered Options) — the driving use case is
    reacting quickly to an Alert, which a confirm dialog would work directly against. return_to is
    a fixed choice rather than a URL, so this route can't be used to redirect anywhere else."""
    back = f"/admin/plugs/{plug_id}/edit" if return_to == "plug" else "/admin/"
    try:
        q.send_plug_command(plug_id, is_on, note or None)
    except ValueError as exc:
        return RedirectResponse(url=f"{back}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=back, status_code=303)


def _render_plug_edit(request: Request, plug_id: int, error: str | None = None,
                       probe_result: dict | None = None):
    """Shared by the GET edit page and the POST /probe route (see CONTEXT.md: Probe, ADR 0016) —
    Probe renders this same page directly instead of redirecting, since its raw dps result doesn't
    fit cleanly through a redirect's query string the way a plain `error` message does."""
    plug = q.get_plug(plug_id)
    if plug is None:
        return None
    plug["target_temp_f"] = _c_to_f(plug["target_temp_c"])
    # target_humidity_pct needs no unit conversion (already %, see CONTEXT.md: Hydrostat-Controlled)
    # — q.get_plug's row already carries it through as-is.
    return templates.TemplateResponse(
        request, "admin_plug_edit.html",
        {
            "plug": plug, "enclosures": q.list_enclosures(), "rooms": q.list_rooms(),
            "plug_groups": q.list_plug_groups(),
            "schedule_drift_threshold_minutes": q.get_settings()["schedule_drift_threshold_minutes"],
            "error": error,
            "probe_result": probe_result,
        }
    )


@router.get("/plugs/{plug_id}/edit")
def admin_edit_plug(request: Request, plug_id: int):
    response = _render_plug_edit(request, plug_id, error=request.query_params.get("error"))
    if response is None:
        return RedirectResponse(url="/admin", status_code=303)
    return response


@router.post("/plugs/{plug_id}/probe")
def admin_probe_plug(
    request: Request,
    plug_id: int,
    tracking_mode: str = Form("smart"),
    switch_dps_key: str = Form("1"),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
):
    """Diagnostic, read-only — see CONTEXT.md: Probe, ADR 0016. Uses whatever's currently in the
    edit form (formnovalidate, same <form> as Save — see admin_plug_edit.html), even if unsaved, so
    new credentials can be tested before committing them. Never writes to the database; nothing
    here is persisted. Renders the edit page directly rather than redirecting."""
    error = None
    probe_result = None
    if tracking_mode != "smart" or not tuya_device_id or not tuya_local_key:
        error = "Probe needs a Smart Plug with a Tuya device_id and local_key filled in."
    else:
        try:
            probe_result = probe_plug(tuya_device_id, tuya_local_key, tuya_ip_address or None, switch_dps_key)
        except RuntimeError as exc:
            error = f"Probe failed — could not reach device: {exc}"
    response = _render_plug_edit(request, plug_id, error=error, probe_result=probe_result)
    if response is None:
        return RedirectResponse(url="/admin", status_code=303)
    return response


@router.post("/plugs/{plug_id}/update")
def admin_update_plug(
    plug_id: int,
    label: str = Form(...),
    purpose: str = Form(...),
    tracking_mode: str = Form("smart"),
    switch_dps_key: str = Form("1"),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
    target_on_time: str = Form(""),
    target_off_time: str = Form(""),
    always_on: bool = Form(False),
    room_id: str = Form(""),
    enclosure_ids: list[int] = Form(default=[]),
    controller_kind: str = Form("none"),
    target_temp_f: float | None = Form(None),
    target_humidity_pct: float | None = Form(None),
    auto_update_enabled: bool = Form(False),
):
    try:
        q.update_plug(plug_id, label, purpose, tracking_mode, switch_dps_key,
                       tuya_device_id or None, tuya_local_key or None, tuya_ip_address,
                       target_on_time or None, target_off_time or None,
                       int(room_id) if room_id else None, enclosure_ids,
                       controller_kind, _f_to_c(target_temp_f), target_humidity_pct, auto_update_enabled,
                       always_on)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/plugs/{plug_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plug-groups")
def admin_create_plug_group(
    name: str = Form(...),
    room_id: str = Form(""),
    enclosure_ids: list[int] = Form(default=[]),
    tuya_device_id: str = Form(""),
    tuya_local_key: str = Form(""),
    tuya_ip_address: str = Form(""),
    relay1_label: str = Form("Outlet 1"),
    relay1_purpose: str = Form(...),
    relay1_dps: str = Form("1"),
    relay2_label: str = Form("Outlet 2"),
    relay2_purpose: str = Form(...),
    relay2_dps: str = Form("2"),
    relay3_label: str = Form("Outlet 3"),
    relay3_purpose: str = Form(...),
    relay3_dps: str = Form("3"),
    usb_label: str = Form("USB"),
    usb_purpose: str = Form(...),
    usb_dps: str = Form("7"),
    ao1_label: str = Form("Always-On 1"),
    ao1_purpose: str = Form(...),
    ao2_label: str = Form("Always-On 2"),
    ao2_purpose: str = Form(...),
    ao3_label: str = Form("Always-On 3"),
    ao3_purpose: str = Form(...),
):
    """Creates a Plug Group from the "3 relays + USB + 3 Always-On" Plug Group Template — see
    CONTEXT.md: Plug Group, Plug Group Template; ADR 0017. Only template offered today; a device
    that doesn't match this shape still gets added one outlet at a time via the plain Add Plug
    form above."""
    smart_members = [
        {"label": relay1_label, "purpose": relay1_purpose, "switch_dps_key": relay1_dps},
        {"label": relay2_label, "purpose": relay2_purpose, "switch_dps_key": relay2_dps},
        {"label": relay3_label, "purpose": relay3_purpose, "switch_dps_key": relay3_dps},
        {"label": usb_label, "purpose": usb_purpose, "switch_dps_key": usb_dps},
    ]
    manual_members = [
        {"label": ao1_label, "purpose": ao1_purpose},
        {"label": ao2_label, "purpose": ao2_purpose},
        {"label": ao3_label, "purpose": ao3_purpose},
    ]
    try:
        q.create_plug_group(
            name, int(room_id) if room_id else None, enclosure_ids,
            tuya_device_id or None, tuya_local_key or None, tuya_ip_address or None,
            smart_members, manual_members,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plug-groups/{plug_group_id}/delete")
def admin_delete_plug_group(plug_group_id: int):
    """Ungroups member Plugs rather than deleting them — see CONTEXT.md: Plug Group; ADR 0017."""
    q.delete_plug_group(plug_group_id)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/plug-groups/{plug_group_id}/command")
def admin_send_plug_group_command(plug_group_id: int, is_on: bool = Form(...)):
    """All On/All Off — see CONTEXT.md: All On / All Off; ADR 0017. Fans out to the Group's Smart
    members only; Always-On Outlets have no relay to command."""
    q.send_plug_group_command(plug_group_id, is_on)
    return RedirectResponse(url="/admin/", status_code=303)


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
        request, "admin_room.html",
        {
            "room": room,
            "schedule_drift_threshold_minutes": q.get_settings()["schedule_drift_threshold_minutes"],
            "error": request.query_params.get("error"),
        }
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


@router.post("/room-sensors/{sensor_id}/dashboard-visibility")
def admin_set_room_sensor_dashboard_visibility(
    sensor_id: int, room_id: int = Form(...), show_on_dashboard: bool = Form(False),
):
    q.set_sensor_dashboard_visibility(sensor_id, show_on_dashboard)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


@router.post("/room-sensors/{sensor_id}/refresh")
async def admin_refresh_room_sensor(sensor_id: int):
    error = await _refresh_one_sensor(sensor_id)
    url = f"/admin/room-sensors/{sensor_id}/edit"
    return RedirectResponse(url=f"{url}?error={quote(error)}" if error else url, status_code=303)


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
    auto_update_enabled: bool = Form(False),
):
    try:
        q.update_room_sensor(sensor_id, room_id, label, tracking_mode, mac_address or None,
                              _f_to_c(temp_min_f), _f_to_c(temp_max_f), humidity_min, humidity_max,
                              auto_update_enabled)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/room-sensors/{sensor_id}/edit?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/admin/rooms/{room_id}", status_code=303)


def _view_data_window(range: str, end: str) -> dict:
    """Shared GET-side window/navigation bits for View Data (see CONTEXT.md: View Data; ADR 0021) —
    identical between the Room and Enclosure pages, only the rows shown differ."""
    start, end_date, days = vd.compute_window(range, end)
    today = datetime.now().date()
    next_end = end_date + timedelta(days=days)
    return {
        "dates": vd.date_list(start, end_date),
        "range": range if range in {key for key, _, _ in vd.RANGE_OPTIONS} else vd.DEFAULT_RANGE_KEY,
        "end": end_date.isoformat(),
        "range_options": vd.RANGE_OPTIONS,
        "prev_end": (start - timedelta(days=1)).isoformat(),
        "next_end": None if end_date >= today else min(next_end, today).isoformat(),
    }


@router.get("/rooms/{room_id}/data")
def admin_room_data(request: Request, room_id: int, range: str = "month", end: str = ""):
    room = q.get_room(room_id)
    if room is None:
        return RedirectResponse(url="/admin", status_code=303)
    window = _view_data_window(range, end)
    return templates.TemplateResponse(
        request, "view_data.html",
        {
            "owner_label": room["name"],
            "owner_kind": "room",
            "back_url": f"/admin/rooms/{room_id}",
            "sections": vd.build_room_sections(room_id, window["dates"]),
            "animals": [],
            "error": request.query_params.get("error"),
            **window,
        }
    )


@router.get("/enclosures/{enclosure_id}/data")
def admin_enclosure_data(request: Request, enclosure_id: int, range: str = "month", end: str = ""):
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/admin/enclosures", status_code=303)
    window = _view_data_window(range, end)
    return templates.TemplateResponse(
        request, "view_data.html",
        {
            "owner_label": enclosure["name"],
            "owner_kind": "enclosure",
            "back_url": f"/admin/enclosures/{enclosure_id}",
            "sections": vd.build_enclosure_sections(enclosure_id, window["dates"]),
            "animals": enclosure["animals"],
            "animal_conditions": ANIMAL_CONDITIONS,
            "animal_condition_labels": ANIMAL_CONDITION_LABELS,
            "error": request.query_params.get("error"),
            **window,
        }
    )


@router.get("/rooms/{room_id}/graphs")
def admin_room_graphs(request: Request, room_id: int, range: str = "month", end: str = ""):
    """Graphs (see CONTEXT.md: Graphs, Overlay; ADR 0022) — same rows as View Data, charted instead
    of tabled. Strictly read-only: no POST route exists here, unlike View Data's cell-edit routes."""
    room = q.get_room(room_id)
    if room is None:
        return RedirectResponse(url="/admin", status_code=303)
    window = _view_data_window(range, end)
    dates = window["dates"]
    sections = gq.build_room_graph_sections(room_id, dates[0], dates[-1], len(dates))
    selected = request.query_params.getlist("rows")
    return templates.TemplateResponse(
        request, "graphs.html",
        {
            "owner_label": room["name"],
            "owner_kind": "room",
            "back_url": f"/admin/rooms/{room_id}",
            "sections": sections,
            "overlay_rows": gq.rows_by_key(sections, selected),
            "selected_keys": set(selected),
            "error": request.query_params.get("error"),
            **window,
        }
    )


@router.get("/enclosures/{enclosure_id}/graphs")
def admin_enclosure_graphs(request: Request, enclosure_id: int, range: str = "month", end: str = ""):
    """Graphs for an Enclosure — see admin_room_graphs above (same shape, different row set, same
    as View Data's own Room/Enclosure split)."""
    enclosure = q.get_enclosure(enclosure_id)
    if enclosure is None:
        return RedirectResponse(url="/admin/enclosures", status_code=303)
    window = _view_data_window(range, end)
    dates = window["dates"]
    sections = gq.build_enclosure_graph_sections(enclosure_id, dates[0], dates[-1], len(dates))
    selected = request.query_params.getlist("rows")
    return templates.TemplateResponse(
        request, "graphs.html",
        {
            "owner_label": enclosure["name"],
            "owner_kind": "enclosure",
            "back_url": f"/admin/enclosures/{enclosure_id}",
            "sections": sections,
            "overlay_rows": gq.rows_by_key(sections, selected),
            "selected_keys": set(selected),
            "error": request.query_params.get("error"),
            **window,
        }
    )


@router.post("/sensors/{sensor_id}/readings/cell")
def admin_set_reading_cell(
    sensor_id: int,
    metric_key: str = Form(...),
    date: str = Form(...),
    action: str = Form("save"),
    value: str = Form(""),
    range: str = Form("month"),
    end: str = Form(""),
):
    """One cell of View Data's Sensor Readings section (see CONTEXT.md: View Data; ADR 0021) — only
    ever reachable for a Manual Sensor; set_reading_cell() itself rejects a Smart one."""
    sensor = q.get_sensor(sensor_id)
    error = None
    if sensor is None:
        error = "Sensor not found."
    else:
        try:
            if action == "clear":
                vd.set_reading_cell(sensor_id, metric_key, date, None)
            else:
                metric = et.metric_by_key(metric_key)
                try:
                    parsed = float(value) if value.strip() else None
                except ValueError:
                    raise ValueError(f"{value!r} isn't a valid number.")
                if parsed is not None and metric.converts_f_c:
                    parsed = _f_to_c(parsed)
                vd.set_reading_cell(sensor_id, metric_key, date, parsed)
        except ValueError as exc:
            error = str(exc)
    owner_path = (
        f"/admin/rooms/{sensor['room_id']}/data" if sensor and sensor["room_id"]
        else f"/admin/enclosures/{sensor['enclosure_id']}/data" if sensor
        else "/admin"
    )
    qs = f"?range={range}&end={end}" + (f"&error={quote(error)}" if error else "")
    anchor = "" if error else f"#row-reading-{sensor_id}-{metric_key}"
    return RedirectResponse(url=f"{owner_path}{qs}{anchor}", status_code=303)


@router.post("/enclosures/{enclosure_id}/care-events/{kind}/cell")
def admin_set_care_event_cell(
    enclosure_id: int,
    kind: str,
    date: str = Form(...),
    action: str = Form("save"),
    time: str = Form(""),
    note: str = Form(""),
    animal_id: str = Form(""),
    range: str = Form("month"),
    end: str = Form(""),
):
    """One cell of View Data's Care Events section (see CONTEXT.md: View Data; ADR 0021)."""
    error = None
    try:
        if action == "clear":
            vd.delete_care_event_cell(enclosure_id, kind, date)
        else:
            vd.set_care_event_cell(enclosure_id, kind, date, time or None, note or None,
                                    int(animal_id) if animal_id else None)
    except ValueError as exc:
        error = str(exc)
    qs = f"?range={range}&end={end}" + (f"&error={quote(error)}" if error else "")
    anchor = "" if error else f"#row-care-{enclosure_id}-{kind}"
    return RedirectResponse(url=f"/admin/enclosures/{enclosure_id}/data{qs}{anchor}", status_code=303)


@router.post("/animals/{animal_id}/log/cell")
def admin_set_animal_metric_cell(
    animal_id: int,
    field: str = Form(...),
    date: str = Form(...),
    action: str = Form("save"),
    value: str = Form(""),
    range: str = Form("month"),
    end: str = Form(""),
):
    """One Weight/Length/Count cell of View Data's Animal Log section (see CONTEXT.md: Animal Log,
    View Data; ADR 0021)."""
    animal = q.get_animal(animal_id)
    error = None
    if animal is None:
        error = "Animal not found."
    else:
        try:
            if action == "clear":
                vd.set_animal_metric_cell(animal_id, field, date, None)
            else:
                try:
                    parsed = (int(value) if field == "count" else float(value)) if value.strip() else None
                except ValueError:
                    raise ValueError(f"{value!r} isn't a valid number.")
                vd.set_animal_metric_cell(animal_id, field, date, parsed)
        except ValueError as exc:
            error = str(exc)
    owner_path = f"/admin/enclosures/{animal['enclosure_id']}/data" if animal else "/admin"
    qs = f"?range={range}&end={end}" + (f"&error={quote(error)}" if error else "")
    anchor = "" if error else f"#row-animal-{animal_id}-{field}"
    return RedirectResponse(url=f"{owner_path}{qs}{anchor}", status_code=303)


@router.post("/animals/{animal_id}/log/condition/cell")
def admin_set_animal_condition_cell(
    animal_id: int,
    date: str = Form(...),
    action: str = Form("save"),
    condition: str = Form(""),
    note: str = Form(""),
    range: str = Form("month"),
    end: str = Form(""),
):
    """One Condition cell of View Data's Animal Log section — picking the blank option acts as a
    clear, same as leaving the cell empty (see CONTEXT.md: Animal Log, View Data; ADR 0021)."""
    animal = q.get_animal(animal_id)
    error = None
    if animal is None:
        error = "Animal not found."
    else:
        try:
            if action == "clear" or not condition:
                vd.delete_animal_condition_cell(animal_id, date)
            else:
                vd.set_animal_condition_cell(animal_id, date, condition, note or None)
        except ValueError as exc:
            error = str(exc)
    owner_path = f"/admin/enclosures/{animal['enclosure_id']}/data" if animal else "/admin"
    qs = f"?range={range}&end={end}" + (f"&error={quote(error)}" if error else "")
    anchor = "" if error else f"#row-animal-{animal_id}-condition"
    return RedirectResponse(url=f"{owner_path}{qs}{anchor}", status_code=303)
