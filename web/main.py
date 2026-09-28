"""Husbandry Tracker dashboard — FastAPI app, served by uvicorn on localhost:22255 (see docker-compose.yml).

Phase 2, v1 scope only (see CONTEXT.md decisions): dashboard + logbook, no charts, no auth,
no alerting. The dashboard is mostly a glance-only view — Schedules and Care logging live on the
Enclosure's Admin page instead (see web/admin.py), with the dashboard's Care pill linking straight
there. Three actions do live here directly rather than redirecting to Admin, because they're
tightly bound to what's already on screen: Refresh (a live BLE read), a Manual Sensor's Log Reading
form, and dragging an Enclosure panel onto a Room to reassign it (see CONTEXT.md: Room) — the drop
handlers are in web/static/app.js, persisted via assign_enclosure_room below.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import markdown
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app_paths import APP_ROOT
from db.db import get_connection, init_db
from schemas import enclosure_types as et
from web.govee_refresh import refresh_sensors
from web.admin import router as admin_router
from web.admin_queries import get_settings
from web.queries import CARE_EVENT_KINDS, assign_enclosure_room, get_dashboard_data, log_reading
from web.status import care_interval_status, target_range_status

BASE_DIR = APP_ROOT / "web"
USER_GUIDE_PATH = APP_ROOT / "docs" / "USER_GUIDE.md"

app = FastAPI(title="Husbandry Tracker")
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["target_range_status"] = target_range_status
templates.env.globals["care_interval_status"] = care_interval_status
# Lets dashboard.html's reading_row()/reading_log_form() macros loop over every possible Target
# Range metric (not just temperature/humidity) generically — see CONTEXT.md: Reading, Target Range.
templates.env.globals["TARGET_RANGE_METRICS"] = et.TARGET_RANGE_METRICS

# Cache-busting query string for /static/app.js and /static/style.css (every template appends
# ?v={{ asset_version }} to both) — browsers cache static JS/CSS aggressively, sometimes surviving
# an ordinary page refresh, so an edit to either file could otherwise run stale in an already-open
# tab even after the Website process itself has been restarted. The newest mtime across web/static/
# changes this value on any edit, forcing a fresh fetch; computed once at startup since a running
# process's own static files don't change underneath it (a genuine edit requires a restart anyway).
templates.env.globals["asset_version"] = str(int(
    max(f.stat().st_mtime for f in (BASE_DIR / "static").iterdir() if f.is_file())
))


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _c_to_f(celsius: float | None) -> float | None:
    return None if celsius is None else celsius * 9 / 5 + 32


def _f_to_c(fahrenheit: float | None) -> float | None:
    return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9


templates.env.filters["c_to_f"] = _c_to_f


@app.get("/")
def dashboard(request: Request):
    data = get_dashboard_data()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"rooms": data["rooms"], "ungrouped": data["ungrouped"], "care_kinds": CARE_EVENT_KINDS,
         "error": request.query_params.get("error")}
    )


@app.get("/guide")
def guide(request: Request):
    # Rendered fresh on every request (not cached) — it's a local doc file that can be edited,
    # and page loads here are rare enough that re-parsing markdown each time is a non-issue.
    text = USER_GUIDE_PATH.read_text(encoding="utf-8")
    content_html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    return templates.TemplateResponse(request, "guide.html", {"content_html": content_html})


async def _refresh_smart_sensors(column: str, entity_id: int) -> str | None:
    """Runs a live BLE Refresh for every Smart Sensor owned by the given Enclosure or Room — never
    anything it merely borrows (a Fallback Sensor) or a sibling entity's own Sensors (see
    CONTEXT.md: Refresh). Returns a friendly error message if any Sensor didn't report in time
    within the configured Refresh Timeout, else None."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, label, external_id FROM sensor WHERE {column} = ? AND tracking_mode = 'smart' "
            f"AND plugin = 'govee_ble'",
            (entity_id,),
        ).fetchall()
    if not rows:
        return None

    sensors_by_mac = {row["external_id"].upper(): (row["id"], row["label"]) for row in rows}
    sensor_ids_by_mac = {mac: sensor_id for mac, (sensor_id, _label) in sensors_by_mac.items()}
    timeout = get_settings()["ble_refresh_timeout_seconds"]
    results = await refresh_sensors(sensor_ids_by_mac, timeout)

    missing = [label for mac, (_id, label) in sensors_by_mac.items() if mac not in results]
    if missing:
        return f"No fresh reading within {timeout}s from: {', '.join(missing)}."
    return None


@app.post("/enclosures/{enclosure_id}/refresh")
async def refresh_enclosure(enclosure_id: int):
    error = await _refresh_smart_sensors("enclosure_id", enclosure_id)
    if error:
        return RedirectResponse(url=f"/?error={quote(error)}", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@app.post("/enclosures/{enclosure_id}/assign-room")
def assign_room(enclosure_id: int, room_id: str = Form(default="")):
    """Dashboard drag-and-drop target (see CONTEXT.md: Room; web/static/app.js's onRoomDrop) —
    room_id "" (dropped on Ungrouped) means None."""
    assign_enclosure_room(enclosure_id, int(room_id) if room_id else None)
    return RedirectResponse(url="/", status_code=303)


@app.post("/rooms/{room_id}/refresh")
async def refresh_room(room_id: int):
    error = await _refresh_smart_sensors("room_id", room_id)
    if error:
        return RedirectResponse(url=f"/?error={quote(error)}", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@app.post("/sensors/{sensor_id}/readings")
def create_reading(
    sensor_id: int,
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
    # One Form field per schemas.enclosure_types.TARGET_RANGE_METRICS entry (see
    # dashboard.html's reading_log_form() macro, which only ever renders the ones this particular
    # Sensor tracks) — keyed here by sensor_reading column name; temperature is the one metric
    # needing a unit conversion (Fahrenheit entry -> Celsius storage), every other value is already
    # in its storage unit.
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
        return RedirectResponse(url=f"/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/", status_code=303)
