import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from db import db

router = APIRouter(prefix="/api", tags=["analysis"])

API_BASE_URL = os.environ.get("API_BASE_URL", "").strip()
OFFLINE_DETAIL = "API OFFLINE — nessun dato"
GET_TIMEOUT = 20.0
EDGE_TIMEOUT = 45.0  # edge computations on the external engine can be slow


async def proxy(method: str, path: str, json=None, params=None, timeout: float = GET_TIMEOUT):
    """Forward to the external research API. Returns None ONLY when it is unreachable
    or errors — NO synthetic/mock fallback is ever produced."""
    if not API_BASE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.request(method, API_BASE_URL.rstrip("/") + path, json=json, params=params)
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


def _require(data):
    if data is None:
        raise HTTPException(status_code=503, detail=OFFLINE_DETAIL)
    return data


async def persist_run(run_type: str, params: dict, result: dict, user_email: str) -> str:
    run_id = str(uuid.uuid4())
    await db.runs.insert_one({
        "id": run_id,
        "run_type": run_type,
        "params": params,
        "result": result,
        "user_email": user_email,
        "source": "external",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return run_id


class SymbolsIn(BaseModel):
    symbols: list[str] = ["XAUUSD"]


# ---------- health / safety ----------
@router.get("/health")
async def health():
    ext = await proxy("GET", "/api/health")
    if ext is None:
        return {"status": "offline", "live_armed": False, "external_api_reachable": False}
    ext["live_armed"] = False  # ABSOLUTE CONSTRAINT: execution can never be armed
    ext["external_api_reachable"] = True
    return ext


@router.get("/safety")
async def safety():
    return {"live_armed": False, "allow_real_live": False, "read_only": True,
            "external_api": bool(API_BASE_URL)}


# ---------- instruments (external only) ----------
@router.get("/instruments")
async def instruments(user: dict = Depends(get_current_user)):
    return _require(await proxy("GET", "/api/instruments"))


# ---------- edge lab (external only) ----------
@router.post("/edge/session-scan")
async def session_scan(body: SymbolsIn, user: dict = Depends(get_current_user)):
    result = _require(await proxy("POST", "/api/edge/session-scan", json=body.model_dump(), timeout=EDGE_TIMEOUT))
    run_id = await persist_run("session-scan", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


@router.post("/edge/ny-conditional")
async def ny_conditional(body: SymbolsIn, user: dict = Depends(get_current_user)):
    result = _require(await proxy("POST", "/api/edge/ny-conditional", json=body.model_dump(), timeout=EDGE_TIMEOUT))
    run_id = await persist_run("ny-conditional", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


@router.post("/edge/overnight")
async def edge_overnight(body: SymbolsIn, user: dict = Depends(get_current_user)):
    result = _require(await proxy("POST", "/api/edge/overnight", json=body.model_dump(), timeout=EDGE_TIMEOUT))
    run_id = await persist_run("overnight", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


@router.post("/edge/significance-audit")
async def significance_audit(body: SymbolsIn, user: dict = Depends(get_current_user)):
    result = _require(await proxy("POST", "/api/edge/significance-audit", json=body.model_dump(), timeout=EDGE_TIMEOUT))
    run_id = await persist_run("significance-audit", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


# ---------- bot diagnostics (external only) ----------
@router.get("/bot/rejection-taxonomy")
async def bot_rejection(user: dict = Depends(get_current_user)):
    return _require(await proxy("GET", "/api/bot/rejection-taxonomy"))


@router.get("/bot/market-structure")
async def bot_structure(user: dict = Depends(get_current_user)):
    return _require(await proxy("GET", "/api/bot/market-structure"))


@router.get("/bot/quality-review")
async def bot_quality(user: dict = Depends(get_current_user)):
    return _require(await proxy("GET", "/api/bot/quality-review"))


@router.get("/bot/demo-readiness")
async def bot_demo(user: dict = Depends(get_current_user)):
    return _require(await proxy("GET", "/api/bot/demo-readiness"))


# ---------- runs persistence ----------
@router.get("/runs")
async def list_runs(run_type: str | None = None, limit: int = 50, user: dict = Depends(get_current_user)):
    q = {}
    if run_type:
        q["run_type"] = run_type
    runs = await db.runs.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 200))
    summary = [{"id": r["id"], "run_type": r["run_type"], "params": r["params"],
                "source": r.get("source"), "created_at": r["created_at"]} for r in runs]
    return {"runs": summary}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    run = await db.runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
