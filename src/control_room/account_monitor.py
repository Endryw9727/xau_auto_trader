"""Account monitor for Control Room."""

from __future__ import annotations

from typing import Any

from src.execution.mt5_demo_executor import check_demo_execution_readiness


def collect_account_snapshot(config: Any) -> dict:
    """Collect MT5 demo account readiness in a safe read-only way."""
    readiness = check_demo_execution_readiness()
    return {
        "status": _normalize_status(readiness.status),
        "reason": readiness.reason,
        "symbol": config.symbol,
        "mt5_initialized": readiness.mt5_initialized,
        "account_connected": readiness.account_connected,
        "account_demo": readiness.account_demo,
        "trade_allowed": readiness.trade_allowed,
        "symbol_found": readiness.symbol_found,
        "symbol_visible": readiness.symbol_visible,
        "volume_min": readiness.volume_min,
        "volume_step": readiness.volume_step,
        "stops_level": readiness.stops_level,
        "filling_mode": readiness.filling_mode,
        "spread_current": readiness.spread_current,
    }


def _normalize_status(status: str) -> str:
    return "WARNING" if status in {"MT5_NOT_AVAILABLE", "ERROR"} else status
