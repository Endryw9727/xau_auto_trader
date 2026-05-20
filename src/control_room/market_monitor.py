"""Market-data monitor for Control Room."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.market_data.data_freshness import DEFAULT_XAUUSD_CSV_PATH, analyze_data_freshness


def collect_market_snapshot(config: Any, data_path: str | Path = DEFAULT_XAUUSD_CSV_PATH) -> dict:
    """Return local data freshness status without writing runtime logs."""
    report = analyze_data_freshness(data_path, symbol=config.symbol)
    return {
        "status": report.status,
        "reason": report.reason,
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "latest_timestamp": _iso(report.latest_timestamp),
        "age_minutes": report.age_minutes,
        "row_count": report.row_count,
        "gap_count": report.gap_count,
        "missing_candles": report.missing_candles,
        "missing_expected_candle": report.missing_expected_candle,
    }


def _iso(value) -> str:
    return "" if value is None else value.isoformat()
