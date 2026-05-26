"""Safely update and validate MT5 multi-timeframe CSV files.

This script reads MT5 candles through the existing read-only updater boundary.
It never sends orders and keeps previous CSV files unchanged when a timeframe
cannot be fetched.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.broker.demo_broker_readonly import DEFAULT_DEMO_BROKER_CONFIG_PATH, load_demo_broker_config
from src.market_data.mt5_readonly_data_updater import (
    _last_timestamp,
    _load_existing_timeframe,
    _merge_market_data,
    _rates_to_standard_frame,
    _read_existing_snapshot,
    _save_main_m15_csv,
    _save_timeframe_csv,
    import_mt5_module,
)
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
SAFE_CAPS = {"M1": 10000, "M5": 10000, "M15": 10000, "M30": 50000, "H1": 20000, "H4": 10000}
RANGE_LOOKBACK_DAYS = {"M1": 7, "M5": 7, "M15": 7, "M30": 30, "H1": 90, "H4": 365}

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
    "candles_returned",
    "method_used",
    "mt5_last_error",
    "fallback_used",
    "terminal_connected",
    "account_info_available",
    "symbol_selected",
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


@dataclass(frozen=True)
class MT5TimeframeUpdateResult:
    """Update diagnostics for one timeframe."""

    symbol: str
    timeframe: str
    rows_before: int
    rows_after: int
    last_timestamp_before: pd.Timestamp | None
    last_timestamp_after: pd.Timestamp | None
    added_rows: int
    status: str
    reason: str
    candles_returned: int = 0
    method_used: str = ""
    mt5_last_error: str = ""
    fallback_used: bool = False
    terminal_connected: bool = False
    account_info_available: bool = False
    symbol_selected: bool = False


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
    now = normalize_now(now)
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
                    update_results[timeframe] = update_timeframe_from_mt5(
                        mt5,
                        symbol=symbol,
                        timeframe=timeframe,
                        max_bars=DEFAULT_MAX_BARS[timeframe],
                        timeframe_dir=timeframe_dir,
                        m15_csv_path=data_dir / "xauusd.csv",
                        now=now,
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
    status = "OK" if (summary["update_status"].astype(str).str.startswith("OK")).all() else "WARNING"
    return TimeframeUpdateRunResult(status=status, summary_path=summary_path, latest_path=latest_path)


def update_timeframe_from_mt5(
    mt5: Any,
    *,
    symbol: str,
    timeframe: str,
    max_bars: int,
    timeframe_dir: Path,
    m15_csv_path: Path,
    now: pd.Timestamp,
) -> MT5TimeframeUpdateResult:
    """Update one timeframe using multiple MT5 read-only candle methods."""
    normalized = normalize_timeframe(timeframe)
    before = _read_existing_snapshot(normalized, timeframe_dir, m15_csv_path)
    terminal_connected = terminal_connected_status(mt5)
    account_info_available = account_info_available_status(mt5)
    symbol_selected = symbol_select_status(mt5, symbol)
    mt5_timeframe = mt5_timeframe_constant(mt5, normalized)
    if mt5_timeframe is None:
        return MT5TimeframeUpdateResult(
            symbol=symbol,
            timeframe=normalized,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            added_rows=0,
            status="WARNING_NO_MT5_CANDLES",
            reason=f"MT5 timeframe constant missing for {normalized}",
            mt5_last_error=last_error_text(mt5),
            terminal_connected=terminal_connected,
            account_info_available=account_info_available,
            symbol_selected=symbol_selected,
        )

    rates, method_used, error_text = fetch_rates(
        mt5,
        symbol,
        normalized,
        mt5_timeframe,
        max_bars,
    )
    candles_returned = 0 if rates is None else int(len(rates))
    if candles_returned == 0:
        if normalized == "M15":
            fallback = fallback_primary_m15(
                symbol=symbol,
                timeframe_dir=timeframe_dir,
                m15_csv_path=m15_csv_path,
                before=before,
                now=now,
                mt5_last_error=error_text,
                terminal_connected=terminal_connected,
                account_info_available=account_info_available,
                symbol_selected=symbol_selected,
            )
            if fallback is not None:
                return fallback
        return MT5TimeframeUpdateResult(
            symbol=symbol,
            timeframe=normalized,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            added_rows=0,
            status="WARNING_NO_MT5_CANDLES",
            reason=f"No candles returned from {symbol} {normalized}",
            candles_returned=0,
            method_used=method_used,
            mt5_last_error=error_text,
            fallback_used=False,
            terminal_connected=terminal_connected,
            account_info_available=account_info_available,
            symbol_selected=symbol_selected,
        )

    new_data = _rates_to_standard_frame(rates, normalized)
    existing = _load_existing_timeframe(normalized, timeframe_dir, m15_csv_path)
    merged, added_rows = _merge_market_data(existing, new_data, max_rows=int(max_bars))
    _save_timeframe_csv(merged, normalized, timeframe_dir)
    if normalized == "M15":
        _save_main_m15_csv(merged, m15_csv_path)
    return MT5TimeframeUpdateResult(
        symbol=symbol,
        timeframe=normalized,
        rows_before=before["rows"],
        rows_after=int(len(merged)),
        last_timestamp_before=before["last"],
        last_timestamp_after=_last_timestamp(merged),
        added_rows=added_rows,
        status="OK",
        reason="Updated local read-only market data from MT5 candles.",
        candles_returned=candles_returned,
        method_used=method_used,
        mt5_last_error=error_text,
        fallback_used=False,
        terminal_connected=terminal_connected,
        account_info_available=account_info_available,
        symbol_selected=symbol_selected,
    )


def validate_timeframe_csv(path: str | Path, *, now: pd.Timestamp | None = None) -> ValidationResult:
    """Validate one timeframe CSV without sorting away timestamp-order problems."""
    now = normalize_now(now)
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
    parser.add_argument("--debug-mt5", action="store_true", help="Print direct MT5 API candle diagnostics for each timeframe.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.debug_mt5:
        print(run_mt5_debug(symbol=args.symbol, timeframes=tuple(args.timeframes)))
        return

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


def warning_update(symbol: str, timeframe: str, reason: str) -> MT5TimeframeUpdateResult:
    return MT5TimeframeUpdateResult(
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
    updated = update_status == "OK" and int(getattr(update, "added_rows", 0) or 0) > 0
    if update_status == "OK_FALLBACK_PRIMARY_M15":
        updated = bool(getattr(update, "fallback_used", False))
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
        "candles_returned": int(getattr(update, "candles_returned", 0) or 0),
        "method_used": str(getattr(update, "method_used", "")),
        "mt5_last_error": str(getattr(update, "mt5_last_error", "")),
        "fallback_used": bool(getattr(update, "fallback_used", False)),
        "terminal_connected": bool(getattr(update, "terminal_connected", False)),
        "account_info_available": bool(getattr(update, "account_info_available", False)),
        "symbol_selected": bool(getattr(update, "symbol_selected", False)),
        "validation_status": validation.status,
        "file_exists": validation.file_exists,
        "non_empty": validation.non_empty,
        "has_ohlc_columns": validation.has_ohlc_columns,
        "timestamp_ordered": validation.timestamp_ordered,
        "latest_timestamp": "" if validation.latest_timestamp is None else validation.latest_timestamp.isoformat(),
        "latest_close": validation.latest_close,
        "candle_age_minutes": validation.candle_age_minutes,
        "updated": updated,
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
            f"age_minutes={row['candle_age_minutes']} updated={row['updated']} "
            f"method_used={row['method_used']} candles_returned={row['candles_returned']} "
            f"mt5_last_error={row['mt5_last_error']} terminal_connected={row['terminal_connected']} "
            f"account_info_available={row['account_info_available']} symbol_selected={row['symbol_selected']} "
            f"fallback_used={row['fallback_used']} reason={row['update_reason']}"
        )
    lines.extend(["", "No orders were sent. This script reads MT5 candles only.", ""])
    return "\n".join(lines)


def fetch_rates(
    mt5: Any,
    symbol: str,
    timeframe_name: str,
    timeframe_constant: Any,
    bars: int,
) -> tuple[Any | None, str, str]:
    """Try the direct MT5 candle calls that work in VPS diagnostics."""
    timeframe = normalize_timeframe(timeframe_name)
    request_bars = min(max(1, int(bars)), int(SAFE_CAPS[timeframe]))
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=int(RANGE_LOOKBACK_DAYS[timeframe]))
    attempts = [
        ("copy_rates_from_pos", lambda: mt5.copy_rates_from_pos(symbol, timeframe_constant, 0, request_bars)),
        ("copy_rates_from", lambda: mt5.copy_rates_from(symbol, timeframe_constant, now_utc, request_bars)),
        ("copy_rates_range", lambda: mt5.copy_rates_range(symbol, timeframe_constant, start_utc, now_utc)),
    ]
    errors = []
    for method_name, call in attempts:
        method = getattr(mt5, method_name, None)
        if not callable(method):
            errors.append(f"{method_name}: unavailable")
            continue
        try:
            rates = call()
        except Exception as exc:
            errors.append(f"{method_name}: exception={exc}; last_error={last_error_text(mt5)}")
            continue
        if rates is not None and len(rates) > 0:
            return trim_rates(rates, request_bars), method_name, "; ".join(errors)
        errors.append(f"{method_name}: empty; last_error={last_error_text(mt5)}")
    return None, "none", "; ".join(errors)


def trim_rates(rates: Any, request_bars: int) -> Any:
    """Keep at most the most recent requested bars without changing MT5 row shape."""
    try:
        if len(rates) <= request_bars:
            return rates
        return rates[-request_bars:]
    except Exception:
        return rates


def run_mt5_debug(*, symbol: str = "XAUUSD-P", timeframes: tuple[str, ...] | list[str] = DEFAULT_TIMEFRAMES) -> str:
    """Run direct MT5 candle API diagnostics without writing files."""
    safety_error = validate_readonly_safety()
    if safety_error:
        return f"MT5 direct debug blocked by safety config: {safety_error}"
    mt5 = import_mt5_module()
    if mt5 is None:
        return "MT5 direct debug unavailable: MetaTrader5 package is not installed."

    lines = [
        "MT5 Direct Timeframe Debug",
        "=" * 72,
        "No orders were sent. This diagnostic reads MT5 candles only.",
    ]
    initialized = False
    try:
        initialize = getattr(mt5, "initialize", None)
        initialized = bool(initialize()) if callable(initialize) else False
        lines.append(f"initialize={initialized} last_error={last_error_text(mt5)}")
        if not initialized:
            return "\n".join(lines)

        selected = symbol_select_status(mt5, symbol)
        lines.append(f"symbol_select({symbol!r}, True)={selected} last_error={last_error_text(mt5)}")
        for timeframe in tuple(normalize_timeframe(item) for item in timeframes):
            constant = mt5_timeframe_constant(mt5, timeframe)
            now_utc = datetime.now(timezone.utc)
            start_utc = now_utc - timedelta(days=int(RANGE_LOOKBACK_DAYS[timeframe]))
            lines.append(f"{timeframe} constant={constant}:")
            for method_name, call in (
                ("copy_rates_from_pos", lambda: mt5.copy_rates_from_pos(symbol, constant, 0, 10)),
                ("copy_rates_from", lambda: mt5.copy_rates_from(symbol, constant, now_utc, 10)),
                ("copy_rates_range", lambda: mt5.copy_rates_range(symbol, constant, start_utc, now_utc)),
            ):
                try:
                    rates = call()
                    rows = 0 if rates is None else len(rates)
                    lines.append(f"  {method_name} => {rows} rows, last_error={last_error_text(mt5)}")
                except Exception as exc:
                    lines.append(f"  {method_name} => exception={exc}, last_error={last_error_text(mt5)}")
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()
    return "\n".join(lines)


def fallback_primary_m15(
    *,
    symbol: str,
    timeframe_dir: Path,
    m15_csv_path: Path,
    before: dict[str, Any],
    now: pd.Timestamp,
    mt5_last_error: str,
    terminal_connected: bool,
    account_info_available: bool,
    symbol_selected: bool,
) -> MT5TimeframeUpdateResult | None:
    """Copy fresh primary M15 data into the timeframe M15 file when MT5 returns none."""
    validation = validate_timeframe_csv(m15_csv_path, now=now)
    if validation.status != "OK" or validation.candle_age_minutes is None or validation.candle_age_minutes > 90:
        return None
    frame = load_primary_m15_frame(m15_csv_path)
    if frame.empty:
        return None
    frame["timeframe"] = "M15"
    _save_timeframe_csv(frame, "M15", timeframe_dir)
    after = validate_timeframe_csv(timeframe_dir / TIMEFRAME_FILES["M15"], now=now)
    return MT5TimeframeUpdateResult(
        symbol=symbol,
        timeframe="M15",
        rows_before=int(before["rows"]),
        rows_after=after.rows,
        last_timestamp_before=before["last"],
        last_timestamp_after=after.latest_timestamp,
        added_rows=max(0, after.rows - int(before["rows"])),
        status="OK_FALLBACK_PRIMARY_M15",
        reason="MT5 returned no M15 candles; refreshed XAUUSD_M15.csv from fresh primary data/raw/xauusd.csv.",
        candles_returned=0,
        method_used="primary_m15_fallback",
        mt5_last_error=mt5_last_error,
        fallback_used=True,
        terminal_connected=terminal_connected,
        account_info_available=account_info_available,
        symbol_selected=symbol_selected,
    )


def load_primary_m15_frame(path: Path) -> pd.DataFrame:
    separator = detect_csv_separator(path)
    header_mode = detect_header_or_no_header(path)
    raw = pd.read_csv(path, sep=separator, header=0 if header_mode == "header" else None, engine="python")
    normalized = normalize_ohlc_columns(raw)
    normalized["time"] = pd.to_datetime(normalized["time"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(1.0)
    else:
        normalized["volume"] = 1.0
    return normalized.dropna(subset=["time", "open", "high", "low", "close"])[
        ["time", "open", "high", "low", "close", "volume"]
    ].sort_values("time")


def mt5_timeframe_constant(mt5: Any, timeframe: str) -> Any | None:
    mapping = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
    }
    return getattr(mt5, mapping[normalize_timeframe(timeframe)], None)


def symbol_select_status(mt5: Any, symbol: str) -> bool:
    selector = getattr(mt5, "symbol_select", None)
    if not callable(selector):
        return False
    try:
        return bool(selector(symbol, True))
    except Exception:
        return False


def terminal_connected_status(mt5: Any) -> bool:
    terminal_info = getattr(mt5, "terminal_info", None)
    if not callable(terminal_info):
        return False
    try:
        info = terminal_info()
    except Exception:
        return False
    if info is None:
        return False
    return bool(getattr(info, "connected", True))


def account_info_available_status(mt5: Any) -> bool:
    account_info = getattr(mt5, "account_info", None)
    if not callable(account_info):
        return False
    try:
        return account_info() is not None
    except Exception:
        return False


def last_error_text(mt5: Any) -> str:
    last_error = getattr(mt5, "last_error", None)
    if not callable(last_error):
        return ""
    try:
        return str(last_error())
    except Exception as exc:
        return f"last_error unavailable: {exc}"


def as_utc_datetime(now: pd.Timestamp) -> Any:
    timestamp = pd.Timestamp(now)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.to_pydatetime()


def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe).strip().upper()
    aliases = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
    value = aliases.get(value, value)
    if value not in DEFAULT_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return value


def normalize_now(now: pd.Timestamp | None) -> pd.Timestamp:
    if now is None:
        return pd.Timestamp.now(tz=UTC).tz_localize(None)
    timestamp = pd.Timestamp(now)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(UTC).tz_localize(None)
    return timestamp


if __name__ == "__main__":
    main()
