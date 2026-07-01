"""
Wire the edge families into the overfitting-resistance engine (read-only).

``session_edge_lab`` scores each (instrument, session, direction) strategy with a
walk-forward t-stat. To judge the *whole search* for backtest overfitting we need
the underlying per-period return series of every strategy, aligned on a common
calendar, so the CSCV/PBO and Deflated-Sharpe machinery in ``overfitting`` can run
on the real family.

This module builds that (days x strategies) return matrix and produces a summary.
A strategy is treated as flat (0 return) on days it does not trade, so all
strategies share one daily calendar. Pure research: no IO here (the runner does
the file/config IO), no execution, no orders.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.overfitting import overfitting_report, sharpe_moments
from src.analysis.session_edge_lab import _EDGE_SESSIONS, _cost_pct, compute_session_trades


def session_return_series(
    market_data: pd.DataFrame,
    symbol: str,
    *,
    cost_per_trade: float = 0.0,
) -> dict[str, pd.Series]:
    """Per-strategy daily net-return series for one instrument.

    Keys are ``"<symbol>/<session>/<direction>"``; each value is a day-indexed
    Series of post-cost percent returns (one entry per trading day for that
    session/direction).
    """
    trades = compute_session_trades(market_data)
    out: dict[str, pd.Series] = {}
    if trades.empty:
        return out
    for session in _EDGE_SESSIONS:
        session_trades = trades[trades["session"] == session].sort_values("day")
        if session_trades.empty:
            continue
        entries = session_trades["entry"].to_numpy()
        gross_long = session_trades["long_return_pct"].to_numpy()
        cost_pct = _cost_pct(cost_per_trade, entries)
        index = pd.DatetimeIndex(pd.to_datetime(session_trades["day"]))
        for direction in ("LONG", "SHORT"):
            net = (gross_long if direction == "LONG" else -gross_long) - cost_pct
            out[f"{symbol}/{session}/{direction}"] = pd.Series(net, index=index)
    return out


def align_return_matrix(
    series_by_strategy: dict[str, pd.Series],
) -> tuple[list[str], np.ndarray]:
    """Align per-strategy series into a (days x strategies) matrix (0 when flat)."""
    if not series_by_strategy:
        return [], np.empty((0, 0))
    # Collapse duplicate days within a strategy (defensive) then union-align.
    cleaned = {name: s[~s.index.duplicated(keep="last")] for name, s in series_by_strategy.items()}
    frame = pd.DataFrame(cleaned).sort_index().fillna(0.0)
    return list(frame.columns), frame.to_numpy()


def overfitting_audit(
    series_by_strategy: dict[str, pd.Series],
    *,
    n_splits: int = 16,
) -> dict:
    """Deflated-Sharpe + PBO summary for a family of strategies.

    Returns JSON-friendly fields, always with ``live_armed = False``.
    """
    names, matrix = align_return_matrix(series_by_strategy)
    if matrix.size == 0 or matrix.shape[1] < 2:
        return {"status": "INSUFFICIENT_DATA", "live_armed": False, "n_strategies": len(names)}

    report = overfitting_report(matrix, n_splits=n_splits)
    report["live_armed"] = False
    report["n_days"] = int(matrix.shape[0])
    best = report.get("best_strategy_index")
    if best is not None and names:
        report["best_strategy"] = names[best]

    # Per-strategy full-sample Sharpe, most-promising first (for the UI table).
    per_strategy = [
        {"strategy": name, "sharpe": round(float(sharpe_moments(matrix[:, j]).sharpe), 4)}
        for j, name in enumerate(names)
    ]
    per_strategy.sort(key=lambda row: row["sharpe"], reverse=True)
    report["strategies"] = per_strategy
    return report
