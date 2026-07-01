"""
Service layer for the research console API (pure, framework-agnostic).

Each function returns JSON-serializable dicts by reusing the existing read-only
runners (the same code paths as the CLI), so API results are identical to what
the scripts produce. No web framework is imported here, so this layer is fully
unit-testable.

Hard invariant: this layer is research/diagnostics only. It never imports
execution code, never sends orders, and reports ``live_armed = false`` so the UI
can prove the system is disarmed.
"""

from __future__ import annotations

import math
from pathlib import Path
import tempfile
import threading
import time
from typing import Any

import pandas as pd
import yaml

from scripts.run_edge_significance_audit import run_edge_significance_audit
from scripts.run_ny_conditional_edge import run_ny_conditional_edge
from scripts.run_overfitting_audit import run_overfitting_audit
from scripts.run_overnight_anomaly import run_overnight_anomaly
from scripts.run_session_edge_lab import run_session_edge_lab
from scripts.run_v51_demo_readiness_report import run_v51_demo_readiness_report
from scripts.run_v51_market_structure_diagnostics import run_v51_market_structure_diagnostics
from scripts.run_v51_quality_review import run_v51_quality_review
from scripts.run_v51_rejection_diagnostics import run_v51_rejection_diagnostics


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EDGE_CONFIG = PROJECT_ROOT / "config" / "edge_lab.yaml"
API_VERSION = "1.0.0"

# Overridable top-level keys accepted by the edge endpoints.
_CONFIG_OVERRIDE_KEYS = ("min_trades", "oos_fraction", "t_stat_threshold")

# Heavy endpoints re-run the full edge computation, which is slow on real data
# and can exceed an HTTP client / tunnel timeout. We cache results for the default
# config with a STALE-WHILE-REVALIDATE policy: the first call computes; every
# later call returns the last result INSTANTLY and, if the underlying data
# changed, refreshes in the background. This is essential on a live VPS where the
# MT5 feed keeps rewriting ``data/raw/*.csv`` — an mtime-keyed cache would
# otherwise miss on every request and block the caller for the full compute time.
_CACHE_TTL_SECONDS = 1800
# key -> (computed_at, data_signature, result)
_cache: dict[Any, tuple[float, tuple, Any]] = {}
_cache_lock = threading.Lock()
_refreshing: set[Any] = set()


def _data_signature() -> tuple:
    raw = PROJECT_ROOT / "data" / "raw"
    if not raw.exists():
        return ()
    return tuple(sorted((path.name, int(path.stat().st_mtime)) for path in raw.glob("*.csv")))


def _cache_key(name: str, config_path: str | Path, overrides: dict[str, Any]) -> Any | None:
    # Only cache the default config (tests pass temporary configs and must not
    # share cached results). The data signature is deliberately NOT part of the
    # key: it is stored alongside the value so a changing signature refreshes the
    # entry in place instead of orphaning it (see _cached_call).
    if Path(config_path) != DEFAULT_EDGE_CONFIG:
        return None
    return (name, tuple(sorted((overrides or {}).items())))


def _cache_get(name: str, config_path: str | Path, overrides: dict[str, Any]) -> Any | None:
    key = _cache_key(name, config_path, overrides)
    if key is None:
        return None
    with _cache_lock:
        entry = _cache.get(key)
    if entry is not None and (time.time() - entry[0]) < _CACHE_TTL_SECONDS:
        return entry[2]
    return None


def _cache_put(name: str, config_path: str | Path, overrides: dict[str, Any], result: Any) -> None:
    key = _cache_key(name, config_path, overrides)
    if key is None:
        return
    with _cache_lock:
        _cache[key] = (time.time(), _data_signature(), result)


def _cached_call(name: str, config_path: str | Path, overrides: dict[str, Any], compute) -> Any:
    """Stale-while-revalidate cache around a heavy ``compute()`` for the default config.

    - Cold cache: compute synchronously (the only path that can block the caller).
    - Warm, data unchanged, within TTL: return the cached result instantly.
    - Warm but stale (data changed or TTL elapsed): return the last result
      immediately AND recompute in the background so the next call is fresh.
    """
    key = _cache_key(name, config_path, overrides)
    if key is None:
        return compute()  # never cache custom configs (tests / ad-hoc runs)
    sig = _data_signature()
    with _cache_lock:
        entry = _cache.get(key)
    if entry is not None:
        computed_at, entry_sig, result = entry
        fresh = entry_sig == sig and (time.time() - computed_at) < _CACHE_TTL_SECONDS
        if not fresh:
            _refresh_async(key, compute)
        return result
    result = compute()
    with _cache_lock:
        _cache[key] = (time.time(), sig, result)
    return result


def _refresh_async(key: Any, compute) -> None:
    """Recompute ``key`` in a background thread, coalescing concurrent refreshes."""
    with _cache_lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def _worker() -> None:
        try:
            result = compute()
            with _cache_lock:
                _cache[key] = (time.time(), _data_signature(), result)
        except Exception:  # noqa: BLE001 - background refresh is best effort
            pass
        finally:
            with _cache_lock:
                _refreshing.discard(key)

    threading.Thread(target=_worker, daemon=True).start()


def warm_cache() -> None:
    """Pre-compute the heavy default-config endpoints so the first UI call is fast."""
    for func in (significance_audit, session_scan, ny_conditional, overnight, overfitting):
        try:
            func()
        except Exception:  # noqa: BLE001 - warming is best effort
            pass


def health() -> dict[str, Any]:
    """Liveness payload. ``live_armed`` is always false by construction."""
    return {"status": "ok", "version": API_VERSION, "live_armed": False}


def list_instruments(config_path: str | Path = DEFAULT_EDGE_CONFIG) -> dict[str, Any]:
    """List configured instruments and whether their local data exists."""
    config = _load_config(config_path)
    instruments = []
    for item in config.get("instruments", []):
        symbol = str(item.get("symbol", "?"))
        csv_path = Path(item.get("csv", ""))
        info = {
            "symbol": symbol,
            "csv": str(csv_path),
            "cost_per_trade": float(item.get("cost_per_trade", 0.0)),
            "has_data": csv_path.exists(),
            "rows": 0,
            "first": None,
            "last": None,
        }
        if csv_path.exists():
            info.update(_csv_span(csv_path))
        instruments.append(info)
    return {"status": "OK", "live_armed": False, "instruments": instruments}


def session_scan(*, config_path: str | Path = DEFAULT_EDGE_CONFIG, **overrides) -> dict[str, Any]:
    """Run the multi-instrument session edge scan and return verdicts + detail."""
    def compute() -> dict[str, Any]:
        with _prepared_config(config_path, overrides) as cfg, tempfile.TemporaryDirectory() as out:
            run_session_edge_lab(config_path=cfg, output_dir=out)
            return {
                "status": "OK",
                "live_armed": False,
                "verdicts": _read_records(Path(out) / "session_edge_verdicts.csv"),
                "detail": _read_records(Path(out) / "session_edge_detail.csv"),
            }
    return _cached_call("session_scan", config_path, overrides, compute)


def ny_conditional(*, config_path: str | Path = DEFAULT_EDGE_CONFIG, **overrides) -> dict[str, Any]:
    """Run the NY conditional edge scan."""
    def compute() -> dict[str, Any]:
        with _prepared_config(config_path, overrides) as cfg, tempfile.TemporaryDirectory() as out:
            run_ny_conditional_edge(config_path=cfg, output_dir=out)
            return {
                "status": "OK",
                "live_armed": False,
                "verdicts": _read_records(Path(out) / "ny_conditional_verdicts.csv"),
                "detail": _read_records(Path(out) / "ny_conditional_detail.csv"),
            }
    return _cached_call("ny_conditional", config_path, overrides, compute)


def overnight(*, config_path: str | Path = DEFAULT_EDGE_CONFIG, **overrides) -> dict[str, Any]:
    """Run the pre-registered overnight/intraday anomaly test."""
    def compute() -> dict[str, Any]:
        with _prepared_config(config_path, overrides) as cfg, tempfile.TemporaryDirectory() as out:
            run_overnight_anomaly(config_path=cfg, output_dir=out)
            rows = _read_records(Path(out) / "overnight_anomaly_audit.csv")
            return {
                "status": "OK",
                "live_armed": False,
                "rows": rows,
                "mtc_survivors": int(sum(1 for r in rows if r.get("mtc_robust"))),
            }
    return _cached_call("overnight", config_path, overrides, compute)


def significance_audit(*, config_path: str | Path = DEFAULT_EDGE_CONFIG, **overrides) -> dict[str, Any]:
    """Run the multiple-testing significance audit (the headline verdict)."""
    def compute() -> dict[str, Any]:
        with _prepared_config(config_path, overrides) as cfg, tempfile.TemporaryDirectory() as out:
            run_edge_significance_audit(config_path=cfg, output_dir=out)
            rows = _read_records(Path(out) / "edge_significance_audit.csv")
            return {
                "status": "OK",
                "live_armed": False,
                "family_size": len(rows),
                "walk_forward_robust": int(sum(1 for r in rows if r.get("robust_edge"))),
                "mtc_survivors": int(sum(1 for r in rows if r.get("mtc_robust"))),
                "rows": rows,
            }
    return _cached_call("significance_audit", config_path, overrides, compute)


def overfitting(*, config_path: str | Path = DEFAULT_EDGE_CONFIG, **overrides) -> dict[str, Any]:
    """Deflated Sharpe + PBO overfitting audit for the whole edge family."""
    def compute() -> dict[str, Any]:
        with _prepared_config(config_path, overrides) as cfg, tempfile.TemporaryDirectory() as out:
            run_overfitting_audit(config_path=cfg, output_dir=out)
            summary = _read_records(Path(out) / "overfitting_summary.csv")
            strategies = _read_records(Path(out) / "overfitting_strategies.csv")
            row = summary[0] if summary else {}
            return {
                "status": row.get("status", "OK"),
                "live_armed": False,
                "n_strategies": row.get("n_strategies"),
                "n_days": row.get("n_days"),
                "best_strategy": row.get("best_strategy"),
                "best_sharpe": row.get("best_sharpe"),
                "expected_max_sharpe_under_null": row.get("expected_max_sharpe_under_null"),
                "deflated_sharpe_ratio": row.get("deflated_sharpe_ratio"),
                "probability_of_backtest_overfitting": row.get("probability_of_backtest_overfitting"),
                "pbo_n_combinations": row.get("pbo_n_combinations"),
                "strategies": strategies,
            }
    return _cached_call("overfitting", config_path, overrides, compute)


def bot_rejection_taxonomy(*, candles: int = 200) -> dict[str, Any]:
    """V51 rejection taxonomy as JSON."""
    with tempfile.TemporaryDirectory() as out:
        result = run_v51_rejection_diagnostics(candles=candles, output_dir=out)
        return {
            "status": result.status,
            "live_armed": False,
            "rows": _read_records(Path(out) / "v51_rejection_taxonomy.csv"),
        }


def bot_market_structure(*, candles: int = 200) -> dict[str, Any]:
    """V51 market-structure context summary as JSON."""
    with tempfile.TemporaryDirectory() as out:
        result = run_v51_market_structure_diagnostics(candles=candles, output_dir=out)
        return {
            "status": result.status,
            "live_armed": False,
            "summary": _read_records(Path(out) / "v51_market_structure_summary.csv"),
        }


def bot_quality_review(*, candles: int = 400) -> dict[str, Any]:
    """V51 quality review (RR, false negatives, rejection review) as JSON."""
    with tempfile.TemporaryDirectory() as out:
        result = run_v51_quality_review(candles=candles, output_dir=out)
        return {
            "status": result.status,
            "live_armed": False,
            "rr_quality": _read_records(Path(out) / "v51_quality_rr.csv"),
            "rejection_review": _read_records(Path(out) / "v51_quality_rejection_review.csv"),
            "false_negatives": _read_records(Path(out) / "v51_quality_false_negatives.csv"),
        }


def bot_demo_readiness(*, candles: int = 800) -> dict[str, Any]:
    """V51 demo readiness checklist + guardrail equity as JSON (report-only)."""
    with tempfile.TemporaryDirectory() as out:
        result = run_v51_demo_readiness_report(candles=candles, output_dir=out)
        return {
            "status": result.status,
            "live_armed": False,
            "checklist": _read_records(Path(out) / "v51_demo_readiness_checklist.csv"),
            "equity": _read_records(Path(out) / "v51_demo_readiness_equity.csv"),
        }


def _csv_span(csv_path: Path) -> dict[str, Any]:
    try:
        frame = pd.read_csv(csv_path)
    except Exception:  # noqa: BLE001
        return {"rows": 0, "first": None, "last": None}
    date_col = next((c for c in ("Date", "time", "timestamp") if c in frame.columns), None)
    first = last = None
    if date_col is not None and not frame.empty:
        dates = pd.to_datetime(frame[date_col], errors="coerce").dropna()
        if not dates.empty:
            first, last = dates.min().isoformat(), dates.max().isoformat()
    return {"rows": int(len(frame)), "first": first, "last": last}


class _prepared_config:
    """Context manager that yields a config path, with overrides applied if any."""

    def __init__(self, config_path: str | Path, overrides: dict[str, Any]):
        self._base = Path(config_path)
        self._overrides = {k: v for k, v in (overrides or {}).items() if k in _CONFIG_OVERRIDE_KEYS and v is not None}
        self._tmp: tempfile.NamedTemporaryFile | None = None

    def __enter__(self) -> Path:
        if not self._overrides:
            return self._base
        config = _load_config(self._base)
        config.update(self._overrides)
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
        yaml.safe_dump(config, self._tmp)
        self._tmp.flush()
        self._tmp.close()
        return Path(self._tmp.name)

    def __exit__(self, *exc) -> None:
        if self._tmp is not None:
            Path(self._tmp.name).unlink(missing_ok=True)


def _load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {"instruments": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"instruments": []}


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    frame = pd.read_csv(path)
    records = frame.to_dict(orient="records")
    # Replacing NaN with None on a float column re-introduces NaN (the column
    # stays float), so clean per value: any non-finite float -> None. This keeps
    # the payload strictly JSON-compliant (no NaN/Infinity tokens).
    return [_json_safe(record) for record in records]


def _json_safe(value: Any) -> Any:
    """Recursively replace NaN/Infinity floats with None for strict JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
