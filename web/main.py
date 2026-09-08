"""HerpMonitor dashboard — FastAPI app, served by uvicorn on localhost:22255 (see docker-compose.yml).

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

from db.db import get_connection, init_db
from web.govee_refresh import refresh_sensors
from web.admin import router as admin_router
from web.admin_queries import get_settings
from web.queries import CARE_EVENT_KINDS, assign_enclosure_room, get_dashboard_data, log_reading
from web.status import care_interval_status, target_range_status

BASE_DIR = Path(__file__).resolve().parent
USER_GUIDE_PATH = BASE_DIR.parent / "docs" / "USER_GUIDE.md"

app = FastAPI(title="HerpMonitor")
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["target_range_status"] = target_range_status
templates.env.globals["care_interval_status"] = care_interval_status


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
    recorded_at: str = Form(default=""),
):
    try:
        log_reading(sensor_id, _f_to_c(temperature_f), humidity_pct, recorded_at)
    except ValueError as exc:
        return RedirectResponse(url=f"/?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/", status_code=303)
