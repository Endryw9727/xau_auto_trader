"""Read-only MT5 market-data updater for local research CSV files.

The updater can read candles from a locally available MetaTrader 5 terminal,
but it never opens, changes, or closes trades. If MT5 is not installed or not
connected, it exits with a safe status and leaves existing CSV files untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.broker.demo_broker_readonly import DEFAULT_DEMO_BROKER_CONFIG_PATH, load_demo_broker_config
from src.market_data.timeframe_loader import TIMEFRAME_FILES, TIMEFRAME_MINUTES, load_timeframe_csv


DEFAULT_MARKET_DATA_CONFIG_PATH = Path("config/market_data.yaml")
DEFAULT_TIMEFRAME_DIR = Path("data/raw/timeframes")
DEFAULT_M15_CSV_PATH = Path("data/raw/xauusd.csv")
SUPPORTED_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")


@dataclass(frozen=True)
class MarketDataUpdateConfig:
    """Static config for read-only market-data updates."""

    symbol: str
    source: str
    auto_update_data: bool
    timeframes: tuple[str, ...]
    max_bars: dict[str, int]


@dataclass(frozen=True)
class MT5DataUpdateResult:
    """Result for one read-only MT5 candle update."""

    symbol: str
    timeframe: str
    rows_before: int
    rows_after: int
    last_timestamp_before: pd.Timestamp | None
    last_timestamp_after: pd.Timestamp | None
    added_rows: int
    status: str
    reason: str


def load_market_data_config(path: str | Path = DEFAULT_MARKET_DATA_CONFIG_PATH) -> MarketDataUpdateConfig:
    """Load market data update settings."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid market data config: {config_path}")

    timeframes = tuple(_normalize_timeframe(item) for item in raw.get("timeframes", SUPPORTED_TIMEFRAMES))
    unsupported = [timeframe for timeframe in timeframes if timeframe not in SUPPORTED_TIMEFRAMES]
    if unsupported:
        raise ValueError(f"Unsupported MT5 read-only timeframes: {unsupported}")

    raw_max_bars = raw.get("max_bars", {})
    max_bars = {timeframe: int(raw_max_bars.get(timeframe, 100000)) for timeframe in SUPPORTED_TIMEFRAMES}

    return MarketDataUpdateConfig(
        symbol=str(raw.get("symbol", "XAUUSD")),
        source=str(raw.get("source", "mt5_demo_readonly")),
        auto_update_data=_as_bool(raw.get("auto_update_data", False)),
        timeframes=timeframes,
        max_bars=max_bars,
    )


def update_market_data_from_mt5_readonly(
    *,
    market_config_path: str | Path = DEFAULT_MARKET_DATA_CONFIG_PATH,
    demo_config_path: str | Path = DEFAULT_DEMO_BROKER_CONFIG_PATH,
    timeframe_dir: str | Path = DEFAULT_TIMEFRAME_DIR,
    m15_csv_path: str | Path = DEFAULT_M15_CSV_PATH,
    mt5_module: Any | None = None,
) -> list[MT5DataUpdateResult]:
    """Update configured local CSV files from MT5 read-only candles."""
    market_config = load_market_data_config(market_config_path)
    demo_config = load_demo_broker_config(demo_config_path)
    if demo_config.execution_enabled or demo_config.allow_live or not demo_config.demo_only:
        raise PermissionError("MT5 data updater requires demo_only=true, allow_live=false, execution_enabled=false.")

    existing_snapshots = {
        timeframe: _read_existing_snapshot(timeframe, Path(timeframe_dir), Path(m15_csv_path))
        for timeframe in market_config.timeframes
    }

    mt5 = mt5_module or import_mt5_module()
    if mt5 is None:
        return [
            _safe_unavailable_result(
                market_config.symbol,
                timeframe,
                existing_snapshots[timeframe],
                "MetaTrader5 package is not installed; local CSV files were not changed.",
            )
            for timeframe in market_config.timeframes
        ]

    initialized = False
    try:
        initialize = getattr(mt5, "initialize", None)
        if callable(initialize):
            initialized = bool(initialize())
        if not initialized:
            reason = f"MT5_NOT_CONNECTED: {getattr(mt5, 'last_error', lambda: 'unknown')()}"
            return [
                _safe_unavailable_result(market_config.symbol, timeframe, existing_snapshots[timeframe], reason)
                for timeframe in market_config.timeframes
            ]

        results = []
        for timeframe in market_config.timeframes:
            results.append(
                update_one_timeframe(
                    mt5,
                    symbol=market_config.symbol,
                    timeframe=timeframe,
                    max_bars=market_config.max_bars[timeframe],
                    timeframe_dir=Path(timeframe_dir),
                    m15_csv_path=Path(m15_csv_path),
                )
            )
        return results
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()


def update_one_timeframe(
    mt5: Any,
    *,
    symbol: str,
    timeframe: str,
    max_bars: int,
    timeframe_dir: Path = DEFAULT_TIMEFRAME_DIR,
    m15_csv_path: Path = DEFAULT_M15_CSV_PATH,
) -> MT5DataUpdateResult:
    """Read one timeframe from MT5 and merge it into local CSV files."""
    normalized_timeframe = _normalize_timeframe(timeframe)
    before = _read_existing_snapshot(normalized_timeframe, timeframe_dir, m15_csv_path)
    mt5_timeframe = _mt5_timeframe_constant(mt5, normalized_timeframe)
    if mt5_timeframe is None:
        return MT5DataUpdateResult(
            symbol=symbol,
            timeframe=normalized_timeframe,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            added_rows=0,
            status="ERROR",
            reason=f"MT5 timeframe constant missing for {normalized_timeframe}",
        )

    # start_pos=1 skips the currently forming bar and keeps local CSVs closed-candle only.
    rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 1, int(max_bars))
    if rates is None or len(rates) == 0:
        return MT5DataUpdateResult(
            symbol=symbol,
            timeframe=normalized_timeframe,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            added_rows=0,
            status="WARNING",
            reason=f"No candles returned for {symbol} {normalized_timeframe}.",
        )

    new_data = _rates_to_standard_frame(rates, normalized_timeframe)
    existing = _load_existing_timeframe(normalized_timeframe, timeframe_dir, m15_csv_path)
    merged, added_rows = _merge_market_data(existing, new_data, max_rows=int(max_bars))
    _save_timeframe_csv(merged, normalized_timeframe, timeframe_dir)
    if normalized_timeframe == "M15":
        _save_main_m15_csv(merged, m15_csv_path)

    after_last = _last_timestamp(merged)
    return MT5DataUpdateResult(
        symbol=symbol,
        timeframe=normalized_timeframe,
        rows_before=before["rows"],
        rows_after=int(len(merged)),
        last_timestamp_before=before["last"],
        last_timestamp_after=after_last,
        added_rows=added_rows,
        status="OK",
        reason="Updated local read-only market data from MT5 candles.",
    )


def import_mt5_module() -> Any | None:
    """Import MetaTrader5 if available."""
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError:
        return None
    return mt5


def _safe_unavailable_result(
    symbol: str,
    timeframe: str,
    snapshot: dict[str, Any],
    reason: str,
) -> MT5DataUpdateResult:
    return MT5DataUpdateResult(
        symbol=symbol,
        timeframe=timeframe,
        rows_before=int(snapshot["rows"]),
        rows_after=int(snapshot["rows"]),
        last_timestamp_before=snapshot["last"],
        last_timestamp_after=snapshot["last"],
        added_rows=0,
        status="MT5_NOT_AVAILABLE",
        reason=reason,
    )


def _read_existing_snapshot(timeframe: str, timeframe_dir: Path, m15_csv_path: Path) -> dict[str, Any]:
    data = _load_existing_timeframe(timeframe, timeframe_dir, m15_csv_path)
    return {"rows": int(len(data)), "last": _last_timestamp(data)}


def _load_existing_timeframe(timeframe: str, timeframe_dir: Path, m15_csv_path: Path) -> pd.DataFrame:
    path = _timeframe_path(timeframe, timeframe_dir)
    if not path.exists():
        if timeframe == "M15" and m15_csv_path.exists():
            return _load_main_m15_csv(m15_csv_path)
        return _empty_standard_frame(timeframe)
    try:
        return load_timeframe_csv(path, timeframe)[["time", "open", "high", "low", "close", "volume", "timeframe"]]
    except Exception:
        if timeframe == "M15" and m15_csv_path.exists():
            return _load_main_m15_csv(m15_csv_path)
        return _empty_standard_frame(timeframe)


def _load_main_m15_csv(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if raw.empty:
        return _empty_standard_frame("M15")
    result = pd.DataFrame(
        {
            "time": pd.to_datetime(raw.get("Date"), errors="coerce"),
            "open": pd.to_numeric(raw.get("Open"), errors="coerce"),
            "high": pd.to_numeric(raw.get("High"), errors="coerce"),
            "low": pd.to_numeric(raw.get("Low"), errors="coerce"),
            "close": pd.to_numeric(raw.get("Close"), errors="coerce"),
            "volume": pd.to_numeric(raw.get("Volume"), errors="coerce").fillna(1.0),
            "timeframe": "M15",
        }
    )
    return result.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _rates_to_standard_frame(rates: Any, timeframe: str) -> pd.DataFrame:
    raw = pd.DataFrame(rates)
    volume_source = "tick_volume" if "tick_volume" in raw.columns else "real_volume" if "real_volume" in raw.columns else None
    volume = pd.to_numeric(raw[volume_source], errors="coerce").fillna(1.0) if volume_source else 1.0
    result = pd.DataFrame(
        {
            "time": pd.to_datetime(raw["time"], unit="s", errors="coerce"),
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": volume,
            "timeframe": timeframe,
        }
    )
    return result.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _merge_market_data(existing: pd.DataFrame, new_data: pd.DataFrame, *, max_rows: int) -> tuple[pd.DataFrame, int]:
    existing = existing.copy() if not existing.empty else _empty_standard_frame(str(new_data["timeframe"].iloc[0]))
    new_timestamps = set(pd.to_datetime(new_data["time"]).dropna())
    existing_timestamps = set(pd.to_datetime(existing["time"]).dropna()) if not existing.empty else set()
    added_rows = len(new_timestamps - existing_timestamps)
    merged = pd.concat([existing, new_data], ignore_index=True)
    merged["time"] = pd.to_datetime(merged["time"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=["time", "open", "high", "low", "close"])
    merged = merged.drop_duplicates(subset=["time"], keep="last")
    merged = merged.sort_values("time").tail(max_rows).reset_index(drop=True)
    return merged[["time", "open", "high", "low", "close", "volume", "timeframe"]], int(added_rows)


def _save_timeframe_csv(data: pd.DataFrame, timeframe: str, timeframe_dir: Path) -> None:
    path = _timeframe_path(timeframe, timeframe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = data[["time", "open", "high", "low", "close", "volume"]].copy()
    output["time"] = pd.to_datetime(output["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, sep="\t", index=False, header=False)


def _save_main_m15_csv(data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = data[["time", "open", "high", "low", "close", "volume"]].copy()
    output.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    output["Date"] = pd.to_datetime(output["Date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, index=False)


def _timeframe_path(timeframe: str, timeframe_dir: Path) -> Path:
    filename = TIMEFRAME_FILES[_normalize_timeframe(timeframe)]
    return timeframe_dir / filename


def _mt5_timeframe_constant(mt5: Any, timeframe: str) -> Any | None:
    return getattr(mt5, f"TIMEFRAME_{_normalize_timeframe(timeframe)}", None)


def _normalize_timeframe(timeframe: Any) -> str:
    value = str(timeframe).strip().upper()
    aliases = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
    value = aliases.get(value, value)
    if value not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _empty_standard_frame(timeframe: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "timeframe"]).assign(
        timeframe=timeframe
    )


def _last_timestamp(data: pd.DataFrame) -> pd.Timestamp | None:
    if data.empty or "time" not in data.columns:
        return None
    times = pd.to_datetime(data["time"], errors="coerce").dropna()
    if times.empty:
        return None
    return pd.Timestamp(times.max()).tz_localize(None)
