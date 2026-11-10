"""RIE JSON API — FastAPI app. `init_db()` creates tables + seeds on import so the app is
ready under both uvicorn and the test client.

Run:  uvicorn server.main:app --reload --port 8020   (from the repo root)
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .admin_service import AdminError
from .rates_service import RateError
from .api import (
    accidents, admin, audit, auth, cases, claims, coding, dashboard, disputes, governance, health,
    leakage, lifecycle, litigation, merits, notifications, offers, parties, payments, rails,
    rates, reasons, reference, remittances, serious_injury, undertakings,
)
from .config import IS_DEV, SECRET_KEY, check_secrets
from .seed import init_db
from .statemachine import GateNotMet, IllegalTransition, WrongActor

check_secrets()                           # refuse default secrets outside dev/test (§9)
init_db()

app = FastAPI(title="RIE — RAF Integrity Engine API", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=8 * 3600, same_site="lax",
                   https_only=not IS_DEV)          # Secure cookie outside dev/test
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(IllegalTransition)
async def _illegal(request: Request, exc: IllegalTransition) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(GateNotMet)
async def _gate(request: Request, exc: GateNotMet) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(WrongActor)
async def _actor(request: Request, exc: WrongActor) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(AdminError)
async def _admin_err(request: Request, exc: AdminError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RateError)
async def _rate_err(request: Request, exc: RateError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


app.include_router(health.router)
for r in (auth.router, claims.router, offers.router, reasons.router, dashboard.router,
          accidents.router, leakage.router, lifecycle.router, merits.router,
          serious_injury.router, undertakings.router, litigation.router, payments.router,
          parties.router, audit.router, cases.router, disputes.router, governance.router,
          admin.router, coding.router, notifications.router, reference.router, rates.router,
          remittances.router):
    app.include_router(r, prefix="/api")

app.include_router(rails.router)          # provider->fund rails: /rails/v1/... (JWS-authenticated)


# Optionally serve the built React SPA (ui/dist) from this same service so the whole app runs on
# one port — real files are served directly, unknown paths fall back to index.html for the SPA's
# client-side router. Registered last so /api and /healthz always win.
_UI_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "dist")
if os.path.isdir(_UI_DIST):
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("rails/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        candidate = os.path.normpath(os.path.join(_UI_DIST, full_path))
        if full_path and candidate.startswith(_UI_DIST) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_UI_DIST, "index.html"))
