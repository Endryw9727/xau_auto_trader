"""
Local market-data freshness checks for controlled paper-forward.

This module reads local CSV data only. It does not fetch market data, contact
brokers, execute trades, or require API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.data_feed.market_data import load_csv_data


DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")
DEFAULT_FRESHNESS_LOG_PATH = Path("reports/paper_forward/data_freshness_log.csv")
FRESHNESS_LOG_COLUMNS = [
    "checked_at",
    "symbol",
    "path",
    "status",
    "timeframe",
    "timeframe_minutes",
    "latest_timestamp",
    "age_minutes",
    "row_count",
    "gap_count",
    "missing_candles",
    "max_gap_minutes",
    "missing_expected_candle",
    "market_open",
    "error",
]


@dataclass(frozen=True)
class DataFreshnessReport:
    """Freshness result for one local market data file."""

    symbol: str
    path: str
    status: str
    latest_timestamp: pd.Timestamp | None
    timeframe_minutes: float | None
    timeframe: str
    row_count: int
    gap_count: int
    missing_candles: int
    max_gap_minutes: float
    age_minutes: float | None
    missing_expected_candle: bool
    market_open: bool
    checked_at: pd.Timestamp
    error: str = ""

    @property
    def is_fresh(self) -> bool:
        """Return True when data is fresh enough for paper-forward."""
        return self.status == "OK"

    @property
    def is_stale(self) -> bool:
        """Return True when data is too old for new paper-forward trades."""
        return self.status == "STALE"


def analyze_data_freshness(
    path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    *,
    symbol: str = "XAUUSD",
    expected_timeframe_minutes: int | None = 15,
    now: pd.Timestamp | None = None,
    timezone: str = "Europe/Rome",
    ok_age_minutes: float = 30.0,
    warning_age_minutes: float = 90.0,
    closed_market_max_age_minutes: float = 3 * 24 * 60.0,
) -> DataFreshnessReport:
    """Load a local OHLCV CSV and calculate freshness diagnostics."""
    checked_at = normalize_now(now, timezone)
    csv_path = Path(path)
    if not csv_path.exists():
        return error_report(symbol, csv_path, checked_at, "file missing")

    try:
        data = load_csv_data(csv_path)
    except Exception as exc:
        return error_report(symbol, csv_path, checked_at, str(exc))

    return analyze_dataframe_freshness(
        data,
        path=csv_path,
        symbol=symbol,
        expected_timeframe_minutes=expected_timeframe_minutes,
        now=checked_at,
        ok_age_minutes=ok_age_minutes,
        warning_age_minutes=warning_age_minutes,
        closed_market_max_age_minutes=closed_market_max_age_minutes,
    )


def analyze_dataframe_freshness(
    data: pd.DataFrame,
    *,
    path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    symbol: str = "XAUUSD",
    expected_timeframe_minutes: int | None = 15,
    now: pd.Timestamp | None = None,
    ok_age_minutes: float = 30.0,
    warning_age_minutes: float = 90.0,
    closed_market_max_age_minutes: float = 3 * 24 * 60.0,
) -> DataFreshnessReport:
    """Calculate freshness diagnostics for an already loaded OHLCV frame."""
    checked_at = normalize_now(now)
    csv_path = Path(path)
    if data is None or data.empty:
        return error_report(symbol, csv_path, checked_at, "data empty")
    if not isinstance(data.index, pd.DatetimeIndex):
        return error_report(symbol, csv_path, checked_at, "data index is not datetime")

    index = pd.DatetimeIndex(pd.to_datetime(data.index, errors="coerce")).dropna().sort_values()
    if index.empty:
        return error_report(symbol, csv_path, checked_at, "timestamp invalid")

    detected_minutes = detect_timeframe_minutes(index)
    timeframe_minutes = float(expected_timeframe_minutes or detected_minutes or 0)
    if timeframe_minutes <= 0:
        timeframe_minutes = float(detected_minutes or 0)
    timeframe = format_timeframe(timeframe_minutes)
    latest = pd.Timestamp(index[-1]).tz_localize(None)
    age_minutes = max(0.0, (checked_at - latest).total_seconds() / 60.0)
    gaps = find_temporal_gaps(index, timeframe_minutes)
    gap_count = len(gaps)
    missing_candles = int(sum(gap["missing_candles"] for gap in gaps))
    max_gap_minutes = max((float(gap["gap_minutes"]) for gap in gaps), default=0.0)
    market_open = is_market_open(checked_at)
    missing_expected = bool(
        market_open
        and timeframe_minutes > 0
        and age_minutes > max(ok_age_minutes, timeframe_minutes * 1.5)
    )
    status = classify_freshness_status(
        age_minutes,
        market_open=market_open,
        ok_age_minutes=ok_age_minutes,
        warning_age_minutes=warning_age_minutes,
        closed_market_max_age_minutes=closed_market_max_age_minutes,
    )

    return DataFreshnessReport(
        symbol=symbol,
        path=str(csv_path),
        status=status,
        latest_timestamp=latest,
        timeframe_minutes=timeframe_minutes or None,
        timeframe=timeframe,
        row_count=int(len(index)),
        gap_count=gap_count,
        missing_candles=missing_candles,
        max_gap_minutes=max_gap_minutes,
        age_minutes=age_minutes,
        missing_expected_candle=missing_expected,
        market_open=market_open,
        checked_at=checked_at,
        error="",
    )


def detect_timeframe_minutes(index: pd.DatetimeIndex) -> float | None:
    """Infer timeframe minutes from the median timestamp distance."""
    if len(index) < 2:
        return None
    diffs = pd.Series(index).diff().dropna().dt.total_seconds() / 60.0
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None
    return float(round(float(diffs.median()), 6))


def find_temporal_gaps(index: pd.DatetimeIndex, timeframe_minutes: float | None) -> list[dict]:
    """Return internal gaps larger than one expected candle interval."""
    if not timeframe_minutes or timeframe_minutes <= 0 or len(index) < 2:
        return []
    gaps = []
    diffs = pd.Series(index).diff()
    threshold_minutes = timeframe_minutes * 1.5
    for position, diff in diffs.items():
        if pd.isna(diff):
            continue
        gap_minutes = diff.total_seconds() / 60.0
        if gap_minutes > threshold_minutes:
            missing = max(1, int(round(gap_minutes / timeframe_minutes)) - 1)
            gaps.append(
                {
                    "start": pd.Timestamp(index[position - 1]),
                    "end": pd.Timestamp(index[position]),
                    "gap_minutes": float(gap_minutes),
                    "missing_candles": missing,
                }
            )
    return gaps


def classify_freshness_status(
    age_minutes: float | None,
    *,
    market_open: bool,
    ok_age_minutes: float = 30.0,
    warning_age_minutes: float = 90.0,
    closed_market_max_age_minutes: float = 3 * 24 * 60.0,
) -> str:
    """Classify data freshness as OK, WARNING, or STALE."""
    if age_minutes is None:
        return "ERROR"
    if market_open:
        if age_minutes <= ok_age_minutes:
            return "OK"
        if age_minutes <= warning_age_minutes:
            return "WARNING"
        return "STALE"
    if age_minutes > closed_market_max_age_minutes:
        return "STALE"
    if age_minutes > warning_age_minutes:
        return "WARNING"
    return "OK"


def is_market_open(now: pd.Timestamp) -> bool:
    """
    Approximate XAUUSD market-open status for freshness checks.

    The check intentionally stays simple and local: weekdays are open except
    late Friday through the weekend. It is a safety gate, not a broker calendar.
    """
    timestamp = pd.Timestamp(now).tz_localize(None)
    weekday = int(timestamp.weekday())
    hour = int(timestamp.hour)
    if weekday == 5:
        return False
    if weekday == 6 and hour < 23:
        return False
    if weekday == 4 and hour >= 23:
        return False
    return True


def append_freshness_log(
    report: DataFreshnessReport,
    path: str | Path = DEFAULT_FRESHNESS_LOG_PATH,
) -> Path:
    """Append one freshness check to the local paper-forward log."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row = report_to_row(report)
    if output_path.exists() and output_path.stat().st_size > 0:
        existing = pd.read_csv(output_path)
    else:
        existing = pd.DataFrame(columns=FRESHNESS_LOG_COLUMNS)
    result = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    result = result[FRESHNESS_LOG_COLUMNS]
    result.to_csv(output_path, index=False)
    return output_path


def report_to_row(report: DataFreshnessReport) -> dict:
    """Serialize a freshness report for CSV output."""
    return {
        "checked_at": _timestamp_to_string(report.checked_at),
        "symbol": report.symbol,
        "path": report.path,
        "status": report.status,
        "timeframe": report.timeframe,
        "timeframe_minutes": report.timeframe_minutes,
        "latest_timestamp": _timestamp_to_string(report.latest_timestamp),
        "age_minutes": report.age_minutes,
        "row_count": report.row_count,
        "gap_count": report.gap_count,
        "missing_candles": report.missing_candles,
        "max_gap_minutes": report.max_gap_minutes,
        "missing_expected_candle": report.missing_expected_candle,
        "market_open": report.market_open,
        "error": report.error,
    }


def format_freshness_detail(report: DataFreshnessReport) -> str:
    """Return a compact preflight/script detail string."""
    if report.status == "ERROR":
        return f"ERROR: {report.error}"
    latest = _timestamp_to_string(report.latest_timestamp)
    age = "n/a" if report.age_minutes is None else f"{report.age_minutes:.1f} min"
    return (
        f"{report.status}: last={latest}, age={age}, timeframe={report.timeframe}, "
        f"rows={report.row_count}, gaps={report.gap_count}, missing_expected={report.missing_expected_candle}"
    )


def normalize_now(now: pd.Timestamp | None = None, timezone: str = "Europe/Rome") -> pd.Timestamp:
    """Return a timezone-normalized, tz-naive timestamp for comparisons."""
    if now is None:
        return pd.Timestamp.now(tz=ZoneInfo(timezone)).tz_localize(None)
    timestamp = pd.Timestamp(now)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone).tz_localize(None)
    return timestamp


def error_report(symbol: str, path: Path, checked_at: pd.Timestamp, message: str) -> DataFreshnessReport:
    """Build an ERROR report."""
    return DataFreshnessReport(
        symbol=symbol,
        path=str(path),
        status="ERROR",
        latest_timestamp=None,
        timeframe_minutes=None,
        timeframe="unknown",
        row_count=0,
        gap_count=0,
        missing_candles=0,
        max_gap_minutes=0.0,
        age_minutes=None,
        missing_expected_candle=False,
        market_open=is_market_open(checked_at),
        checked_at=checked_at,
        error=message,
    )


def format_timeframe(minutes: float | None) -> str:
    """Return a short timeframe label from minutes."""
    if not minutes or minutes <= 0:
        return "unknown"
    if minutes < 60:
        return f"{int(minutes) if float(minutes).is_integer() else minutes:g}m"
    hours = minutes / 60.0
    return f"{int(hours) if float(hours).is_integer() else hours:g}h"


def _timestamp_to_string(timestamp: pd.Timestamp | None) -> str:
    if timestamp is None or pd.isna(timestamp):
        return ""
    return pd.Timestamp(timestamp).isoformat()
