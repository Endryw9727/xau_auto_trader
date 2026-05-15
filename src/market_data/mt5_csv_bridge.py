"""MT5 CSV bridge for safe local market-data imports.

This module imports candle CSV files exported from MetaTrader 5 on Mac/Wine.
It only reads and writes local CSV data for paper/research workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pandas.errors import EmptyDataError

from src.market_data.timeframe_loader import (
    TIMEFRAME_FILES,
    TIMEFRAME_MINUTES,
    detect_csv_separator,
    load_timeframe_csv,
)


DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH = Path("config/mt5_csv_bridge.yaml")
DEFAULT_TIMEFRAME_OUTPUT_DIR = Path("data/raw/timeframes")
DEFAULT_M15_OUTPUT_PATH = Path("data/raw/xauusd.csv")
SUPPORTED_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")


@dataclass(frozen=True)
class MT5CsvBridgeConfig:
    """Static config for MT5 CSV bridge imports."""

    enabled: bool
    symbol: str
    source: str
    allow_live: bool
    execution_enabled: bool
    demo_only: bool
    auto_import: bool
    input_dir: Path
    archive_dir: Path
    timeframes: dict[str, str]


@dataclass(frozen=True)
class MT5CsvBridgeResult:
    """Result for one timeframe imported from an MT5 CSV export."""

    symbol: str
    timeframe: str
    source_file: str
    output_file: str
    rows_read: int
    rows_before: int
    rows_after: int
    added_rows: int
    last_timestamp_before: pd.Timestamp | None
    last_timestamp_after: pd.Timestamp | None
    status: str
    reason: str


def load_mt5_csv_bridge_config(path: str | Path = DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH) -> MT5CsvBridgeConfig:
    """Load and validate bridge config."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid MT5 CSV bridge config: {config_path}")

    timeframes_raw = raw.get("timeframes", {})
    if not isinstance(timeframes_raw, dict):
        raise ValueError("MT5 CSV bridge timeframes must be a mapping.")

    timeframes = {_normalize_timeframe(key): str(value) for key, value in timeframes_raw.items()}
    unsupported = sorted(set(timeframes) - set(SUPPORTED_TIMEFRAMES))
    if unsupported:
        raise ValueError(f"Unsupported MT5 CSV bridge timeframes: {unsupported}")

    config = MT5CsvBridgeConfig(
        enabled=_as_bool(raw.get("enabled", True)),
        symbol=str(raw.get("symbol", "XAUUSD")),
        source=str(raw.get("source", "mt5_csv_bridge")),
        allow_live=_as_bool(raw.get("allow_live", True)),
        execution_enabled=_as_bool(raw.get("execution_enabled", True)),
        demo_only=_as_bool(raw.get("demo_only", False)),
        auto_import=_as_bool(raw.get("auto_import", False)),
        input_dir=Path(str(raw.get("input_dir", "data/mt5_bridge/input"))),
        archive_dir=Path(str(raw.get("archive_dir", "data/mt5_bridge/archive"))),
        timeframes=timeframes,
    )
    validate_mt5_csv_bridge_config(config)
    return config


def validate_mt5_csv_bridge_config(config: MT5CsvBridgeConfig) -> None:
    """Validate read-only bridge guardrails."""
    if config.allow_live:
        raise PermissionError("MT5 CSV bridge requires allow_live=false.")
    if config.execution_enabled:
        raise PermissionError("MT5 CSV bridge requires execution_enabled=false.")
    if not config.demo_only:
        raise PermissionError("MT5 CSV bridge requires demo_only=true.")


def import_mt5_csv_bridge(
    *,
    config_path: str | Path = DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_TIMEFRAME_OUTPUT_DIR,
    m15_output_path: str | Path = DEFAULT_M15_OUTPUT_PATH,
) -> list[MT5CsvBridgeResult]:
    """Import all configured MT5 CSV exports into local project data paths."""
    config = load_mt5_csv_bridge_config(config_path)
    ensure_bridge_directories(config)
    if not config.enabled:
        return [
            _result(
                config,
                timeframe,
                source_file=config.input_dir / filename,
                output_file=_output_path(timeframe, Path(output_dir), Path(m15_output_path)),
                status="WARNING",
                reason="MT5 CSV bridge is disabled.",
            )
            for timeframe, filename in config.timeframes.items()
        ]

    results = []
    for timeframe, filename in config.timeframes.items():
        results.append(
            import_mt5_csv_timeframe(
                config,
                timeframe=timeframe,
                source_file=config.input_dir / filename,
                output_dir=Path(output_dir),
                m15_output_path=Path(m15_output_path),
            )
        )
    return results


def import_mt5_csv_timeframe(
    config: MT5CsvBridgeConfig,
    *,
    timeframe: str,
    source_file: str | Path,
    output_dir: Path = DEFAULT_TIMEFRAME_OUTPUT_DIR,
    m15_output_path: Path = DEFAULT_M15_OUTPUT_PATH,
) -> MT5CsvBridgeResult:
    """Import one timeframe CSV export."""
    validate_mt5_csv_bridge_config(config)
    normalized_timeframe = _normalize_timeframe(timeframe)
    source_path = Path(source_file)
    output_file = _output_path(normalized_timeframe, output_dir, m15_output_path)
    before = _existing_snapshot(normalized_timeframe, output_dir, m15_output_path)

    if not source_path.exists():
        return _result(
            config,
            normalized_timeframe,
            source_file=source_path,
            output_file=output_file,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            status="FILE_MISSING",
            reason="MT5 CSV export file is missing.",
        )
    if source_path.stat().st_size == 0:
        return _result(
            config,
            normalized_timeframe,
            source_file=source_path,
            output_file=output_file,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            status="EMPTY_FILE",
            reason="MT5 CSV export file is empty.",
        )

    try:
        imported = load_mt5_export_csv(source_path, normalized_timeframe)
        rows_read = int(imported.attrs.get("rows_read", len(imported)))
        existing = _load_existing_output(normalized_timeframe, output_dir, m15_output_path)
        merged, added_rows = _merge_frames(existing, imported)
        _save_timeframe_output(merged, normalized_timeframe, output_dir)
        if normalized_timeframe == "M15":
            _save_main_m15_output(merged, m15_output_path)
    except EmptyDataError:
        return _result(
            config,
            normalized_timeframe,
            source_file=source_path,
            output_file=output_file,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            status="EMPTY_FILE",
            reason="MT5 CSV export file is empty.",
        )
    except Exception as exc:
        return _result(
            config,
            normalized_timeframe,
            source_file=source_path,
            output_file=output_file,
            rows_before=before["rows"],
            rows_after=before["rows"],
            last_timestamp_before=before["last"],
            last_timestamp_after=before["last"],
            status="ERROR",
            reason=str(exc),
        )

    return _result(
        config,
        normalized_timeframe,
        source_file=source_path,
        output_file=output_file,
        rows_read=rows_read,
        rows_before=before["rows"],
        rows_after=len(merged),
        added_rows=added_rows,
        last_timestamp_before=before["last"],
        last_timestamp_after=_last_timestamp(merged),
        status="OK",
        reason="MT5 CSV export imported into local project data.",
    )


def load_mt5_export_csv(path: str | Path, timeframe: str) -> pd.DataFrame:
    """Load, normalize, and validate one MT5-exported candle CSV."""
    csv_path = Path(path)
    separator = detect_csv_separator(csv_path)
    header = _detect_mt5_header(csv_path, separator)
    raw = pd.read_csv(csv_path, sep=separator, header=0 if header else None, engine="python")
    if raw.empty:
        raise EmptyDataError("empty MT5 CSV")
    rows_read = int(len(raw))
    normalized = normalize_mt5_export_dataframe(raw)
    normalized["timeframe"] = _normalize_timeframe(timeframe)
    normalized = normalized.dropna(subset=["time", "open", "high", "low", "close"])
    normalized = normalized.sort_values("time")
    normalized = normalized.drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)
    validate_ohlc(normalized)
    validate_timeframe(normalized, timeframe)
    result = normalized[
        ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume", "timeframe"]
    ]
    result.attrs["rows_read"] = rows_read
    return result


def normalize_mt5_export_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize common MT5 export columns to canonical names."""
    data = raw.copy()
    if _has_generic_columns(data):
        data = _rename_headerless_mt5_columns(data)
    else:
        data.columns = [_clean_column_name(column) for column in data.columns]
        data = data.rename(columns=_column_aliases())

    time = _build_timestamp(data)
    missing = [column for column in ["open", "high", "low", "close"] if column not in data.columns]
    if missing:
        raise ValueError(f"Missing required MT5 OHLC columns: {missing}")
    result = pd.DataFrame(
        {
            "time": time,
            "open": pd.to_numeric(data["open"], errors="coerce"),
            "high": pd.to_numeric(data["high"], errors="coerce"),
            "low": pd.to_numeric(data["low"], errors="coerce"),
            "close": pd.to_numeric(data["close"], errors="coerce"),
            "tick_volume": _numeric_column(data, "tick_volume", 1.0),
            "spread": _numeric_column(data, "spread", 0.0),
            "real_volume": _numeric_column(data, "real_volume", 0.0),
        }
    )
    return result


def validate_ohlc(data: pd.DataFrame) -> None:
    """Raise if any candle has invalid OHLC relationships."""
    if data.empty:
        raise ValueError("No valid MT5 candle rows after normalization.")
    invalid = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
        | (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if bool(invalid.any()):
        raise ValueError(f"Invalid OHLC rows found: {int(invalid.sum())}")


def validate_timeframe(data: pd.DataFrame, timeframe: str) -> None:
    """Validate that the median candle spacing matches the expected timeframe."""
    expected_minutes = TIMEFRAME_MINUTES[_normalize_timeframe(timeframe)]
    if len(data) < 3:
        return
    diffs = data["time"].diff().dropna().dt.total_seconds() / 60.0
    diffs = diffs[diffs > 0]
    if diffs.empty:
        raise ValueError("Timeframe cannot be validated from duplicate timestamps only.")
    median_minutes = float(diffs.median())
    if abs(median_minutes - expected_minutes) > 0.01:
        raise ValueError(
            f"CSV timeframe mismatch for {timeframe}: median spacing {median_minutes:g} minutes, "
            f"expected {expected_minutes:g}."
        )


def ensure_bridge_directories(config: MT5CsvBridgeConfig) -> None:
    """Ensure local bridge directories exist."""
    config.input_dir.mkdir(parents=True, exist_ok=True)
    config.archive_dir.mkdir(parents=True, exist_ok=True)


def _detect_mt5_header(path: Path, separator: str) -> bool:
    first_line = ""
    with path.open("r", encoding="utf-8-sig") as file:
        for line in file:
            if line.strip():
                first_line = line.strip()
                break
    if not first_line:
        return False
    cleaned = [_clean_column_name(part) for part in first_line.split(separator)]
    header_tokens = {"date", "time", "open", "high", "low", "close", "tick_volume", "tickvol"}
    return any(part in header_tokens for part in cleaned)


def _rename_headerless_mt5_columns(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    count = len(result.columns)
    if count >= 9:
        names = ["date", "time", "open", "high", "low", "close", "tick_volume", "real_volume", "spread"]
    elif count == 8:
        names = ["date", "time", "open", "high", "low", "close", "tick_volume", "spread"]
    elif count == 7:
        names = ["date", "time", "open", "high", "low", "close", "tick_volume"]
    elif count == 6:
        names = ["datetime", "open", "high", "low", "close", "tick_volume"]
    else:
        raise ValueError("MT5 CSV export must contain at least 6 columns.")
    result.columns = names[:count]
    return result


def _build_timestamp(data: pd.DataFrame) -> pd.Series:
    if "date" in data.columns and "time" in data.columns:
        return pd.to_datetime(
            data["date"].astype(str).str.strip() + " " + data["time"].astype(str).str.strip(),
            errors="coerce",
        )
    if "datetime" in data.columns:
        return pd.to_datetime(data["datetime"], errors="coerce")
    if "time" in data.columns:
        return pd.to_datetime(data["time"], errors="coerce")
    raise ValueError("MT5 CSV export must include Date+Time, datetime, or time columns.")


def _column_aliases() -> dict[str, str]:
    return {
        "datetime": "datetime",
        "timestamp": "datetime",
        "date": "date",
        "time": "time",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tickvol": "tick_volume",
        "tick_vol": "tick_volume",
        "tick_volume": "tick_volume",
        "volume": "real_volume",
        "vol": "real_volume",
        "real_volume": "real_volume",
        "spread": "spread",
    }


def _load_existing_output(timeframe: str, output_dir: Path, m15_output_path: Path) -> pd.DataFrame:
    path = _timeframe_output_path(timeframe, output_dir)
    if timeframe == "M15" and m15_output_path.exists():
        try:
            raw = pd.read_csv(m15_output_path)
            loaded = pd.DataFrame(
                {
                    "time": pd.to_datetime(raw.get("Date"), errors="coerce"),
                    "open": pd.to_numeric(raw.get("Open"), errors="coerce"),
                    "high": pd.to_numeric(raw.get("High"), errors="coerce"),
                    "low": pd.to_numeric(raw.get("Low"), errors="coerce"),
                    "close": pd.to_numeric(raw.get("Close"), errors="coerce"),
                    "tick_volume": pd.to_numeric(raw.get("Volume"), errors="coerce").fillna(1.0),
                    "spread": 0.0,
                    "real_volume": 0.0,
                    "timeframe": "M15",
                }
            )
            return raw_cleanup(loaded)
        except Exception:
            return _empty_standard_frame(timeframe)
    if path.exists():
        try:
            loaded = load_timeframe_csv(path, timeframe)
            return _standard_from_loaded(loaded, timeframe)
        except Exception:
            return _empty_standard_frame(timeframe)
    return _empty_standard_frame(timeframe)


def _standard_from_loaded(data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    return raw_cleanup(
        pd.DataFrame(
            {
                "time": pd.to_datetime(data["time"], errors="coerce"),
                "open": pd.to_numeric(data["open"], errors="coerce"),
                "high": pd.to_numeric(data["high"], errors="coerce"),
                "low": pd.to_numeric(data["low"], errors="coerce"),
                "close": pd.to_numeric(data["close"], errors="coerce"),
                "tick_volume": pd.to_numeric(data["volume"], errors="coerce").fillna(1.0),
                "spread": 0.0,
                "real_volume": 0.0,
                "timeframe": timeframe,
            }
        )
    )


def raw_cleanup(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["time"] = pd.to_datetime(result["time"], errors="coerce")
    return result.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _existing_snapshot(timeframe: str, output_dir: Path, m15_output_path: Path) -> dict[str, Any]:
    data = _load_existing_output(timeframe, output_dir, m15_output_path)
    return {"rows": int(len(data)), "last": _last_timestamp(data)}


def _merge_frames(existing: pd.DataFrame, imported: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    existing_times = set(pd.to_datetime(existing["time"], errors="coerce").dropna()) if not existing.empty else set()
    imported_times = set(pd.to_datetime(imported["time"], errors="coerce").dropna())
    added_rows = len(imported_times - existing_times)
    merged = pd.concat([existing, imported], ignore_index=True)
    merged = raw_cleanup(merged)
    merged = merged.drop_duplicates(subset=["time"], keep="last").sort_values("time").reset_index(drop=True)
    return merged[
        ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume", "timeframe"]
    ], int(added_rows)


def _save_timeframe_output(data: pd.DataFrame, timeframe: str, output_dir: Path) -> Path:
    path = _timeframe_output_path(timeframe, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = data[["time", "open", "high", "low", "close", "tick_volume", "real_volume", "spread"]].copy()
    output["time"] = pd.to_datetime(output["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, sep="\t", header=False, index=False)
    return path


def _save_main_m15_output(data: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = data[["time", "open", "high", "low", "close", "tick_volume"]].copy()
    output.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    output["Date"] = pd.to_datetime(output["Date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, index=False)
    return path


def _result(
    config: MT5CsvBridgeConfig,
    timeframe: str,
    *,
    source_file: str | Path,
    output_file: str | Path,
    rows_read: int = 0,
    rows_before: int = 0,
    rows_after: int = 0,
    added_rows: int = 0,
    last_timestamp_before: pd.Timestamp | None = None,
    last_timestamp_after: pd.Timestamp | None = None,
    status: str,
    reason: str,
) -> MT5CsvBridgeResult:
    return MT5CsvBridgeResult(
        symbol=config.symbol,
        timeframe=timeframe,
        source_file=str(source_file),
        output_file=str(output_file),
        rows_read=int(rows_read),
        rows_before=int(rows_before),
        rows_after=int(rows_after),
        added_rows=int(added_rows),
        last_timestamp_before=last_timestamp_before,
        last_timestamp_after=last_timestamp_after,
        status=status,
        reason=reason,
    )


def _output_path(timeframe: str, output_dir: Path, m15_output_path: Path) -> Path:
    if _normalize_timeframe(timeframe) == "M15":
        return m15_output_path
    return _timeframe_output_path(timeframe, output_dir)


def _timeframe_output_path(timeframe: str, output_dir: Path) -> Path:
    return output_dir / TIMEFRAME_FILES[_normalize_timeframe(timeframe)]


def _last_timestamp(data: pd.DataFrame) -> pd.Timestamp | None:
    if data.empty:
        return None
    timestamps = pd.to_datetime(data["time"], errors="coerce").dropna()
    if timestamps.empty:
        return None
    return pd.Timestamp(timestamps.max()).tz_localize(None)


def _normalize_timeframe(timeframe: Any) -> str:
    value = str(timeframe).strip().upper()
    aliases = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
    value = aliases.get(value, value)
    if value not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return value


def _clean_column_name(column: Any) -> str:
    return str(column).strip().strip("<>").strip().lower().replace(" ", "_")


def _has_generic_columns(data: pd.DataFrame) -> bool:
    return all(isinstance(column, int) for column in data.columns)


def _numeric_column(data: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column in data.columns:
        return pd.to_numeric(data[column], errors="coerce").fillna(default)
    return pd.Series([default] * len(data), index=data.index, dtype="float64")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _empty_standard_frame(timeframe: str) -> pd.DataFrame:
    return pd.DataFrame(
        columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume", "timeframe"]
    ).assign(timeframe=timeframe)
