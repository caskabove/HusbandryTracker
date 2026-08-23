"""HerpMonitor dashboard — FastAPI app, served by uvicorn on localhost:22255 (see docker-compose.yml).

Phase 2, v1 scope only (see CONTEXT.md decisions): dashboard + logbook, no charts, no auth,
no alerting. Schedule (Plug on-time/duration inference from transition history) isn't built yet —
panels show "no schedule data yet" for now.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db.db import init_db
from web.admin import router as admin_router
from web.queries import CARE_EVENT_KINDS, get_dashboard_enclosures, log_care_event
from web.status import care_interval_status, target_range_status

BASE_DIR = Path(__file__).resolve().parent

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


templates.env.filters["c_to_f"] = _c_to_f


@app.get("/")
def dashboard(request: Request):
    enclosures = get_dashboard_enclosures()
    return templates.TemplateResponse(
        request, "dashboard.html", {"enclosures": enclosures, "care_kinds": CARE_EVENT_KINDS}
    )


@app.post("/enclosures/{enclosure_id}/care-events/{kind}")
def create_care_event(enclosure_id: int, kind: str, note: str = Form(default=None)):
    log_care_event(enclosure_id, kind, note)
    return RedirectResponse(url="/", status_code=303)
