"""RIE JSON API — FastAPI app. `init_db()` creates tables + seeds on import so the app is
ready under both uvicorn and the test client.

Run:  uvicorn server.main:app --reload --port 8020   (from the repo root)
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .api import (
    accidents, auth, claims, dashboard, health, leakage, lifecycle, litigation, merits, offers,
    reasons, serious_injury, undertakings,
)
from .config import SECRET_KEY
from .seed import init_db
from .statemachine import GateNotMet, IllegalTransition, WrongActor

init_db()

app = FastAPI(title="RIE — RAF Integrity Engine API", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=8 * 3600, same_site="lax")
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


app.include_router(health.router)
for r in (auth.router, claims.router, offers.router, reasons.router, dashboard.router,
          accidents.router, leakage.router, lifecycle.router, merits.router,
          serious_injury.router, undertakings.router, litigation.router):
    app.include_router(r, prefix="/api")
