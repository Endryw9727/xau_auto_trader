"""Safely update and validate MT5 multi-timeframe CSV files.

This script reads MT5 candles through the existing read-only updater boundary.
It never sends orders and keeps previous CSV files unchanged when a timeframe
cannot be fetched.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.broker.demo_broker_readonly import DEFAULT_DEMO_BROKER_CONFIG_PATH, load_demo_broker_config
from src.market_data.mt5_readonly_data_updater import import_mt5_module, update_one_timeframe
from src.market_data.timeframe_loader import (
    TIMEFRAME_FILES,
    detect_csv_separator,
    detect_header_or_no_header,
    normalize_ohlc_columns,
)


DEFAULT_DATA_DIR = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
SUMMARY_FILENAME = "mt5_timeframe_update_summary.csv"
LATEST_FILENAME = "mt5_timeframe_update_latest.txt"
DEFAULT_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
DEFAULT_MAX_BARS = {"M1": 100000, "M5": 100000, "M15": 100000, "M30": 50000, "H1": 20000, "H4": 10000}

SUMMARY_COLUMNS = [
    "checked_at",
    "symbol",
    "timeframe",
    "output_file",
    "update_status",
    "update_reason",
    "rows_before",
    "rows_after",
    "added_rows",
    "validation_status",
    "file_exists",
    "non_empty",
    "has_ohlc_columns",
    "timestamp_ordered",
    "latest_timestamp",
    "latest_close",
    "candle_age_minutes",
    "updated",
]


@dataclass(frozen=True)
class TimeframeUpdateRunResult:
    """Result paths and high-level status for one update run."""

    status: str
    summary_path: Path
    latest_path: Path


@dataclass(frozen=True)
class ValidationResult:
    """Validation details for one timeframe CSV."""

    status: str
    file_exists: bool
    non_empty: bool
    has_ohlc_columns: bool
    timestamp_ordered: bool
    rows: int
    latest_timestamp: pd.Timestamp | None
    latest_close: float | None
    candle_age_minutes: float | None
    reason: str


def run_mt5_timeframe_update(
    *,
    symbol: str = "XAUUSD-P",
    data_dir: str | Path = DEFAULT_DATA_DIR,
    timeframes: tuple[str, ...] | list[str] = DEFAULT_TIMEFRAMES,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    now: pd.Timestamp | None = None,
    mt5_module: Any | None = None,
) -> TimeframeUpdateRunResult:
    """Update requested timeframes from MT5 read-only data and validate outputs."""
    now = pd.Timestamp.now() if now is None else pd.Timestamp(now).tz_localize(None)
    data_dir = Path(data_dir)
    timeframe_dir = data_dir / "timeframes"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_FILENAME
    latest_path = output_dir / LATEST_FILENAME
    normalized_timeframes = tuple(normalize_timeframe(item) for item in timeframes)

    safety_error = validate_readonly_safety()
    mt5 = None if safety_error else mt5_module or import_mt5_module()
    update_results = {}
    initialized = False
    try:
        if safety_error:
            update_results = {timeframe: warning_update(symbol, timeframe, safety_error) for timeframe in normalized_timeframes}
        elif mt5 is None:
            update_results = {
                timeframe: warning_update(symbol, timeframe, "MetaTrader5 package is not installed; files were not changed.")
                for timeframe in normalized_timeframes
            }
        else:
            initialize = getattr(mt5, "initialize", None)
            initialized = bool(initialize()) if callable(initialize) else False
            if not initialized:
                reason = f"MT5_NOT_CONNECTED: {getattr(mt5, 'last_error', lambda: 'unknown')()}"
                update_results = {timeframe: warning_update(symbol, timeframe, reason) for timeframe in normalized_timeframes}
            else:
                for timeframe in normalized_timeframes:
                    update_results[timeframe] = update_one_timeframe(
                        mt5,
                        symbol=symbol,
                        timeframe=timeframe,
                        max_bars=DEFAULT_MAX_BARS[timeframe],
                        timeframe_dir=timeframe_dir,
                        m15_csv_path=data_dir / "xauusd.csv",
                    )
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()

    rows = []
    for timeframe in normalized_timeframes:
        output_file = timeframe_dir / TIMEFRAME_FILES[timeframe]
        validation = validate_timeframe_csv(output_file, now=now)
        update = update_results[timeframe]
        rows.append(summary_row(symbol, timeframe, output_file, update, validation, now))

    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(summary_path, index=False)
    latest_path.write_text(build_latest_text(summary), encoding="utf-8")
    status = "OK" if (summary["validation_status"] == "OK").all() else "WARNING"
    return TimeframeUpdateRunResult(status=status, summary_path=summary_path, latest_path=latest_path)


def validate_timeframe_csv(path: str | Path, *, now: pd.Timestamp | None = None) -> ValidationResult:
    """Validate one timeframe CSV without sorting away timestamp-order problems."""
    now = pd.Timestamp.now() if now is None else pd.Timestamp(now).tz_localize(None)
    csv_path = Path(path)
    if not csv_path.exists():
        return ValidationResult("MISSING", False, False, False, False, 0, None, None, None, "file missing")
    if csv_path.stat().st_size == 0:
        return ValidationResult("EMPTY", True, False, False, False, 0, None, None, None, "file empty")

    try:
        separator = detect_csv_separator(csv_path)
        header_mode = detect_header_or_no_header(csv_path)
        raw = pd.read_csv(csv_path, sep=separator, header=0 if header_mode == "header" else None, engine="python")
    except EmptyDataError:
        return ValidationResult("EMPTY", True, False, False, False, 0, None, None, None, "file empty")

    if raw.empty:
        return ValidationResult("EMPTY", True, False, False, False, 0, None, None, None, "file empty")

    try:
        normalized = normalize_ohlc_columns(raw)
    except ValueError as exc:
        return ValidationResult("INVALID_COLUMNS", True, True, False, False, len(raw), None, None, None, str(exc))

    normalized["time"] = pd.to_datetime(normalized["time"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    prepared = normalized.dropna(subset=["time", "open", "high", "low", "close"])
    if prepared.empty:
        return ValidationResult("INVALID_COLUMNS", True, True, False, False, 0, None, None, None, "no valid OHLC rows")

    timestamps = pd.to_datetime(prepared["time"], errors="coerce")
    ordered = bool(timestamps.is_monotonic_increasing)
    latest_position = timestamps.idxmax()
    latest_timestamp = pd.Timestamp(timestamps.loc[latest_position]).tz_localize(None)
    latest_close = float(prepared.loc[latest_position, "close"])
    age = max(0.0, (now - latest_timestamp).total_seconds() / 60.0)
    status = "OK" if ordered else "INVALID_TIMESTAMP_ORDER"
    reason = "CSV valid" if ordered else "timestamps are not sorted ascending"
    return ValidationResult(status, True, True, True, ordered, int(len(prepared)), latest_timestamp, latest_close, age, reason)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSD-P", help="MT5 symbol to read in read-only mode.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Root data directory.")
    parser.add_argument("--timeframes", nargs="+", default=list(DEFAULT_TIMEFRAMES), help="Timeframes to update.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Diagnostics output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_mt5_timeframe_update(
        symbol=args.symbol,
        data_dir=args.data_dir,
        timeframes=tuple(args.timeframes),
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - MT5 Multi-Timeframe CSV Update")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This script reads MT5 candles only.")


def validate_readonly_safety() -> str | None:
    try:
        load_demo_broker_config(DEFAULT_DEMO_BROKER_CONFIG_PATH)
    except Exception as exc:
        return f"read-only safety config rejected: {exc}"
    return None


def warning_update(symbol: str, timeframe: str, reason: str) -> Any:
    return _UpdateFallback(
        symbol=symbol,
        timeframe=timeframe,
        rows_before=0,
        rows_after=0,
        last_timestamp_before=None,
        last_timestamp_after=None,
        added_rows=0,
        status="WARNING",
        reason=reason,
    )


def summary_row(symbol: str, timeframe: str, output_file: Path, update: Any, validation: ValidationResult, now: pd.Timestamp) -> dict:
    update_status = str(getattr(update, "status", "WARNING"))
    return {
        "checked_at": now.isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "output_file": str(output_file),
        "update_status": update_status,
        "update_reason": str(getattr(update, "reason", "")),
        "rows_before": int(getattr(update, "rows_before", 0) or 0),
        "rows_after": int(getattr(update, "rows_after", validation.rows) or 0),
        "added_rows": int(getattr(update, "added_rows", 0) or 0),
        "validation_status": validation.status,
        "file_exists": validation.file_exists,
        "non_empty": validation.non_empty,
        "has_ohlc_columns": validation.has_ohlc_columns,
        "timestamp_ordered": validation.timestamp_ordered,
        "latest_timestamp": "" if validation.latest_timestamp is None else validation.latest_timestamp.isoformat(),
        "latest_close": validation.latest_close,
        "candle_age_minutes": validation.candle_age_minutes,
        "updated": update_status == "OK" and int(getattr(update, "added_rows", 0) or 0) > 0,
    }


def build_latest_text(summary: pd.DataFrame) -> str:
    lines = [
        "MT5 Multi-Timeframe CSV Update",
        "=" * 72,
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"{row['timeframe']}: update={row['update_status']} validation={row['validation_status']} "
            f"file={row['output_file']} latest={row['latest_timestamp']} close={row['latest_close']} "
            f"age_minutes={row['candle_age_minutes']} updated={row['updated']} reason={row['update_reason']}"
        )
    lines.extend(["", "No orders were sent. This script reads MT5 candles only.", ""])
    return "\n".join(lines)


def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe).strip().upper()
    aliases = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
    value = aliases.get(value, value)
    if value not in DEFAULT_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return value


@dataclass(frozen=True)
class _UpdateFallback:
    symbol: str
    timeframe: str
    rows_before: int
    rows_after: int
    last_timestamp_before: pd.Timestamp | None
    last_timestamp_after: pd.Timestamp | None
    added_rows: int
    status: str
    reason: str


if __name__ == "__main__":
    main()
