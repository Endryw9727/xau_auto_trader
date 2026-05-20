"""Risk monitor for Control Room."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_PAPER_DAILY_LOG_PATH = Path("reports/paper_forward/paper_forward_daily_log.csv")
DEFAULT_PAPER_EQUITY_PATH = Path("reports/paper_forward/paper_forward_equity.csv")
DEFAULT_DEMO_POSITIONS_PATH = Path("reports/demo_execution/demo_positions.csv")


def collect_risk_snapshot(config: Any, *, account_snapshot: dict, market_snapshot: dict) -> dict:
    """Build risk state from available paper/demo CSVs."""
    daily = _read_latest_row(DEFAULT_PAPER_DAILY_LOG_PATH)
    equity = _read_latest_row(DEFAULT_PAPER_EQUITY_PATH)
    demo_positions = _read_csv(DEFAULT_DEMO_POSITIONS_PATH)

    current_equity = _float(equity.get("equity"), None)
    daily_loss_pct = _float(daily.get("daily_loss_pct"), 0.0)
    paper_open_trades = int(_float(daily.get("open_trades"), 0.0) or 0)
    demo_open_positions = 0 if demo_positions.empty else int(len(demo_positions))
    open_positions = max(paper_open_trades, demo_open_positions)
    spread = _float(account_snapshot.get("spread_current"), None)

    status = "OK"
    reasons = []
    if daily_loss_pct is not None and daily_loss_pct > float(config.max_daily_loss_pct):
        status = "STOP"
        reasons.append(f"daily loss {daily_loss_pct:.2f}% > {config.max_daily_loss_pct:.2f}%")
    if open_positions > int(config.max_open_positions):
        status = "STOP"
        reasons.append(f"open positions {open_positions} > {config.max_open_positions}")
    if spread is not None and spread > float(config.max_spread_points):
        status = "WARNING" if status == "OK" else status
        reasons.append(f"spread {spread:.1f} > {config.max_spread_points:.1f}")
    if market_snapshot.get("status") in {"STALE", "ERROR"}:
        status = "WARNING" if status == "OK" else status
        reasons.append(f"market data {market_snapshot.get('status')}")

    return {
        "status": status,
        "reason": "; ".join(reasons) if reasons else "risk within configured monitor limits",
        "equity": current_equity,
        "open_positions": open_positions,
        "paper_open_trades": paper_open_trades,
        "demo_open_positions": demo_open_positions,
        "daily_pnl": _float(daily.get("daily_pnl"), 0.0),
        "daily_loss_pct": daily_loss_pct,
        "max_dd_paper_or_demo": _float(equity.get("drawdown_pct"), 0.0),
        "spread_current": spread,
    }


def _read_latest_row(path: Path) -> dict:
    frame = _read_csv(path)
    if frame.empty:
        return {}
    return frame.iloc[-1].to_dict()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _float(value, default):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
