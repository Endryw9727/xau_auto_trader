import io
import os
import uuid
from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel

import mock_data
from auth import get_current_user
from db import db

router = APIRouter(prefix="/api", tags=["analysis"])

API_BASE_URL = os.environ.get("API_BASE_URL", "").strip()


async def proxy(method: str, path: str, json=None, params=None):
    """Forward to the external research API if configured; else return None (mock fallback)."""
    if not API_BASE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.request(method, API_BASE_URL.rstrip("/") + path, json=json, params=params)
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


async def persist_run(run_type: str, params: dict, result: dict, user_email: str) -> str:
    run_id = str(uuid.uuid4())
    doc = {
        "id": run_id,
        "run_type": run_type,
        "params": params,
        "result": result,
        "user_email": user_email,
        "source": "external" if API_BASE_URL else "mock",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.runs.insert_one(doc)
    return run_id


class SymbolsIn(BaseModel):
    symbols: list[str] = ["XAUUSD"]


class SyntheticIn(BaseModel):
    symbol: str = "SYNTH1"
    rows: int = 500


class FetchIn(BaseModel):
    symbol: str = "XAUUSD"


# ---------- health / safety ----------
@router.get("/health")
async def health():
    ext = await proxy("GET", "/api/health")
    data = ext or mock_data.health()
    data["live_armed"] = False  # ABSOLUTE CONSTRAINT: execution can never be armed
    return data


@router.get("/safety")
async def safety():
    return {"live_armed": False, "allow_real_live": False, "read_only": True,
            "external_api": bool(API_BASE_URL)}


# ---------- instruments / data ----------
@router.get("/instruments")
async def instruments(user: dict = Depends(get_current_user)):
    ext = await proxy("GET", "/api/instruments")
    base = ext or mock_data.instruments()
    uploaded = await db.uploaded_instruments.find({}, {"_id": 0}).to_list(200)
    merged = {i["symbol"]: i for i in base.get("instruments", [])}
    for u in uploaded:
        merged[u["symbol"]] = u  # uploaded/fetched copy overrides bundled
    base["instruments"] = list(merged.values())
    return base


@router.post("/data/upload-csv")
async def upload_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")
    cols = {c.lower(): c for c in df.columns}
    if "date" not in cols or "close" not in cols:
        raise HTTPException(status_code=400, detail="CSV must contain at least Date and Close columns")
    symbol = os.path.splitext(file.filename or "UPLOAD")[0].upper()[:16]
    date_col = cols["date"]
    first = str(df[date_col].iloc[0])
    last = str(df[date_col].iloc[-1])
    inst = {
        "symbol": symbol,
        "has_data": True,
        "rows": int(len(df)),
        "first": first,
        "last": last,
        "cost_per_trade": 0.10,
        "source": "upload",
    }
    await db.uploaded_instruments.update_one({"symbol": symbol}, {"$set": inst}, upsert=True)
    return inst


@router.post("/data/synthetic")
async def synthetic(body: SyntheticIn, user: dict = Depends(get_current_user)):
    rows = max(50, min(body.rows, 5000))
    symbol = body.symbol.upper()[:16]
    series = mock_data.synthetic_series(symbol, rows)
    inst = {
        "symbol": symbol,
        "has_data": True,
        "rows": rows,
        "first": series[0]["date"],
        "last": series[-1]["date"],
        "cost_per_trade": 0.10,
        "source": "synthetic",
    }
    await db.uploaded_instruments.update_one({"symbol": symbol}, {"$set": inst}, upsert=True)
    return {"instrument": inst, "preview": series[-120:]}


@router.post("/data/fetch-yahoo")
async def fetch_yahoo(body: FetchIn, user: dict = Depends(get_current_user)):
    ext = await proxy("POST", "/api/data/fetch-yahoo", json=body.model_dump())
    if ext:
        return ext
    symbol = body.symbol.upper()[:16]
    series = mock_data.synthetic_series(symbol, 1200)
    inst = {
        "symbol": symbol,
        "has_data": True,
        "rows": 1200,
        "first": series[0]["date"],
        "last": series[-1]["date"],
        "cost_per_trade": 0.10,
        "source": "yahoo(mock)",
    }
    await db.uploaded_instruments.update_one({"symbol": symbol}, {"$set": inst}, upsert=True)
    return {"instrument": inst, "preview": series[-120:], "note": "External API not connected — synthetic fallback."}


# ---------- edge lab ----------
@router.post("/edge/session-scan")
async def session_scan(body: SymbolsIn, user: dict = Depends(get_current_user)):
    ext = await proxy("POST", "/api/edge/session-scan", json=body.model_dump())
    result = ext or mock_data.session_scan(body.symbols)
    run_id = await persist_run("session-scan", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


@router.post("/edge/ny-conditional")
async def ny_conditional(body: SymbolsIn, user: dict = Depends(get_current_user)):
    ext = await proxy("POST", "/api/edge/ny-conditional", json=body.model_dump())
    result = ext or mock_data.ny_conditional(body.symbols)
    run_id = await persist_run("ny-conditional", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


def _normalize_overnight(result: dict) -> dict:
    """External /api/edge/overnight returns dense 'rows' but no aggregated 'verdicts'.
    Synthesize a per-symbol verdict (best leg) so the contract matches the other edge
    endpoints. Mock data already includes 'verdicts', so this is a no-op there."""
    if result.get("verdicts"):
        return result
    rows = result.get("rows") or result.get("detail") or []
    best_by_symbol: dict = {}
    for r in rows:
        sym = r.get("symbol")
        if sym is None:
            continue
        cur = best_by_symbol.get(sym)
        if cur is None or (r.get("oos_t_stat") or 0) > (cur.get("oos_t_stat") or 0):
            best_by_symbol[sym] = r
    verdicts = []
    for sym, best in best_by_symbol.items():
        leg = str(best.get("leg", "")).upper()
        direction = "LONG" if "LONG" in leg else ("SHORT" if "SHORT" in leg else best.get("direction", "—"))
        t = best.get("oos_t_stat")
        keep = bool(best.get("mtc_robust")) or (isinstance(t, (int, float)) and t >= 1.8)
        verdicts.append({
            "symbol": sym,
            "verdict": "KEEP" if keep else "EXCLUDE",
            "best_session": "OVERNIGHT",
            "best_direction": direction,
            "best_oos_t_stat": t,
            "p_value": best.get("p_value"),
            "bh_significant": best.get("bh_significant"),
            "mtc_robust": best.get("mtc_robust"),
        })
    result["verdicts"] = verdicts
    if not result.get("detail"):
        result["detail"] = rows
    return result


@router.post("/edge/overnight")
async def edge_overnight(body: SymbolsIn, user: dict = Depends(get_current_user)):
    ext = await proxy("POST", "/api/edge/overnight", json=body.model_dump())
    result = _normalize_overnight(ext or mock_data.overnight(body.symbols))
    run_id = await persist_run("overnight", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


@router.post("/edge/significance-audit")
async def significance_audit(body: SymbolsIn, user: dict = Depends(get_current_user)):
    ext = await proxy("POST", "/api/edge/significance-audit", json=body.model_dump())
    result = ext or mock_data.significance_audit(body.symbols)
    run_id = await persist_run("significance-audit", body.model_dump(), result, user["email"])
    return {**result, "run_id": run_id}


# ---------- bot diagnostics ----------
@router.get("/bot/rejection-taxonomy")
async def bot_rejection(user: dict = Depends(get_current_user)):
    ext = await proxy("GET", "/api/bot/rejection-taxonomy")
    return ext or mock_data.rejection_taxonomy()


@router.get("/bot/market-structure")
async def bot_structure(user: dict = Depends(get_current_user)):
    ext = await proxy("GET", "/api/bot/market-structure")
    return ext or mock_data.market_structure()


@router.get("/bot/quality-review")
async def bot_quality(user: dict = Depends(get_current_user)):
    ext = await proxy("GET", "/api/bot/quality-review")
    return ext or mock_data.quality_review()


@router.get("/bot/demo-readiness")
async def bot_demo(user: dict = Depends(get_current_user)):
    ext = await proxy("GET", "/api/bot/demo-readiness")
    data = ext or mock_data.demo_readiness()
    data["live_armed"] = False
    data["allow_real_live"] = False
    return data


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
