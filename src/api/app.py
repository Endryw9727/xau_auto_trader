"""
Starlette ASGI app exposing the read-only research pipeline as JSON.

Run it (the research console UI points API_BASE_URL here):

    uvicorn src.api.app:app --host 0.0.0.0 --port 8000

Security:
- Optional bearer token: if the env var RESEARCH_API_TOKEN is set, every request
  must send ``Authorization: Bearer <token>``.
- There is NO endpoint that arms execution; ``/api/health`` reports
  ``live_armed: false``. This service cannot send orders.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.api import research_service as service
from src.api.research_service import _json_safe


_TOKEN_ENV = "RESEARCH_API_TOKEN"
_NUMERIC_OVERRIDES = {"min_trades": int, "oos_fraction": float, "t_stat_threshold": float}


def _authorized(request: Request) -> bool:
    token = os.environ.get(_TOKEN_ENV)
    if not token:
        return True  # auth disabled when no token configured
    header = request.headers.get("authorization", "")
    return header.startswith("Bearer ") and header[len("Bearer "):].strip() == token


async def _call(request: Request, func, *, allow_body: bool = False):
    if not _authorized(request):
        return JSONResponse({"status": "ERROR", "reason": "unauthorized"}, status_code=401)
    overrides = {}
    if allow_body:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - empty/invalid body means no overrides
            payload = {}
        if isinstance(payload, dict):
            for key, caster in _NUMERIC_OVERRIDES.items():
                if payload.get(key) is not None:
                    try:
                        overrides[key] = caster(payload[key])
                    except (TypeError, ValueError):
                        pass
    try:
        result = await run_in_threadpool(lambda: func(**overrides))
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the UI
        return JSONResponse({"status": "ERROR", "reason": str(exc), "live_armed": False}, status_code=500)
    # Strict JSON: NaN/Infinity are not JSON-compliant and Starlette refuses them.
    return JSONResponse(_json_safe(result))


async def health(request: Request):
    return JSONResponse(service.health())


async def instruments(request: Request):
    return await _call(request, service.list_instruments)


async def session_scan(request: Request):
    return await _call(request, service.session_scan, allow_body=True)


async def ny_conditional(request: Request):
    return await _call(request, service.ny_conditional, allow_body=True)


async def overnight(request: Request):
    return await _call(request, service.overnight, allow_body=True)


async def significance_audit(request: Request):
    return await _call(request, service.significance_audit, allow_body=True)


async def overfitting(request: Request):
    return await _call(request, service.overfitting, allow_body=True)


async def rejection_taxonomy(request: Request):
    return await _call(request, service.bot_rejection_taxonomy)


async def market_structure(request: Request):
    return await _call(request, service.bot_market_structure)


async def quality_review(request: Request):
    return await _call(request, service.bot_quality_review)


async def demo_readiness(request: Request):
    return await _call(request, service.bot_demo_readiness)


routes = [
    Route("/api/health", health, methods=["GET"]),
    Route("/api/instruments", instruments, methods=["GET"]),
    Route("/api/edge/session-scan", session_scan, methods=["POST"]),
    Route("/api/edge/ny-conditional", ny_conditional, methods=["POST"]),
    Route("/api/edge/overnight", overnight, methods=["POST"]),
    Route("/api/edge/significance-audit", significance_audit, methods=["POST"]),
    Route("/api/edge/overfitting", overfitting, methods=["POST"]),
    Route("/api/bot/rejection-taxonomy", rejection_taxonomy, methods=["GET"]),
    Route("/api/bot/market-structure", market_structure, methods=["GET"]),
    Route("/api/bot/quality-review", quality_review, methods=["GET"]),
    Route("/api/bot/demo-readiness", demo_readiness, methods=["GET"]),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("RESEARCH_API_CORS", "*").split(","),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
]

def _warm_cache_in_background() -> None:
    # Pre-compute the heavy endpoints so the first UI request is served from
    # cache and does not exceed the client / tunnel timeout.
    threading.Thread(target=service.warm_cache, daemon=True).start()


app = Starlette(routes=routes, middleware=middleware)

# Kick off cache warming at import time. We deliberately avoid Starlette's
# ``on_startup`` hook because newer Starlette releases removed that constructor
# argument (it raised ``TypeError: unexpected keyword argument 'on_startup'``);
# starting the daemon thread here works on every Starlette version.
_warm_cache_in_background()
