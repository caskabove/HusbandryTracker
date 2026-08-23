"""HerpMonitor dashboard — FastAPI app, served by uvicorn on localhost:22255 (see docker-compose.yml).

Phase 2, v1 scope only (see CONTEXT.md decisions): dashboard + logbook, no charts, no auth,
no alerting. The dashboard is deliberately a glance-only view — Schedules and Care logging live on
the Enclosure's Admin page instead (see web/admin.py), with the dashboard's Care pill linking
straight there. Schedule (Plug on-time/duration inference from transition history) isn't built
yet — the Admin page's Schedules section shows "no schedule data yet" for a Smart Plug until it is.
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

from db.db import init_db
from web.admin import router as admin_router
from web.queries import CARE_EVENT_KINDS, get_dashboard_enclosures, log_reading
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
    enclosures = get_dashboard_enclosures()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"enclosures": enclosures, "care_kinds": CARE_EVENT_KINDS, "error": request.query_params.get("error")}
    )


@app.get("/guide")
def guide(request: Request):
    # Rendered fresh on every request (not cached) — it's a local doc file that can be edited,
    # and page loads here are rare enough that re-parsing markdown each time is a non-issue.
    text = USER_GUIDE_PATH.read_text(encoding="utf-8")
    content_html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    return templates.TemplateResponse(request, "guide.html", {"content_html": content_html})


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
