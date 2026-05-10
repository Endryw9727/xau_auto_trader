"""
Multi-timeframe CSV loader for research/backtest data.

The loader is intentionally local-file only. It does not fetch data, call
brokers, or execute trades.
"""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


TIMEFRAME_FILES = {
    "M1": "XAUUSD_M1.csv",
    "M5": "XAUUSD_M5.csv",
    "M15": "XAUUSD_M15.csv",
    "M30": "XAUUSD_M30.csv",
    "H1": "XAUUSD_H1.csv",
    "H4": "XAUUSD_H4.csv",
}
TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
}
STANDARD_COLUMNS = [
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "timeframe",
]
SUPPORTED_SEPARATORS = ("\t", ",", ";", "|")


def detect_csv_separator(path: str | Path) -> str:
    """Detect the most likely CSV separator from the first non-empty lines."""
    sample = _read_text_sample(path)
    lines = [line for line in sample.splitlines() if line.strip()]

    if not lines:
        return ","

    scores = {
        separator: sum(line.count(separator) for line in lines[:10])
        for separator in SUPPORTED_SEPARATORS
    }
    best_separator, best_score = max(scores.items(), key=lambda item: item[1])

    return best_separator if best_score > 0 else ","


def detect_header_or_no_header(path: str | Path) -> str:
    """
    Return "header" or "no_header" for a timeframe CSV.

    Headerless TradingView/export files usually start with a datetime value in
    column 1 and numeric OHLC values after it.
    """
    separator = detect_csv_separator(path)
    sample = _read_text_sample(path)

    first_line = ""
    for line in sample.splitlines():
        if line.strip():
            first_line = line.strip()
            break

    if not first_line:
        return "no_header"

    parts = [part.strip() for part in first_line.split(separator)]
    first_value = parts[0] if parts else ""

    if _looks_like_datetime(first_value):
        return "no_header"

    lowered = [part.lower() for part in parts]
    header_tokens = {
        "date",
        "datetime",
        "time",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "timeframe",
    }
    if any(token in header_tokens for token in lowered):
        return "header"

    return "header" if any(re.search(r"[A-Za-z]", part) for part in parts) else "no_header"


def normalize_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize raw OHLC columns to lowercase canonical names.

    The function accepts either header-based files or headerless files with:
    time, open, high, low, close, optional extra/volume column.
    """
    if df.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])

    result = df.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]

    if _has_generic_columns(result):
        result = _rename_headerless_columns(result)
    else:
        result = _rename_header_columns(result)

    required = ["time", "open", "high", "low", "close"]
    missing = [column for column in required if column not in result.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")

    return result


def load_timeframe_csv(path: str | Path, timeframe_name: str) -> pd.DataFrame:
    """
    Load and normalize one timeframe CSV.

    Output always includes:
    time, open, high, low, close, volume, timeframe, has_real_volume.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Timeframe CSV not found: {csv_path}")

    timeframe = _normalize_timeframe_name(timeframe_name)
    separator = detect_csv_separator(csv_path)
    header_mode = detect_header_or_no_header(csv_path)

    raw = pd.read_csv(
        csv_path,
        sep=separator,
        header=0 if header_mode == "header" else None,
        engine="python",
    )
    normalized = normalize_ohlc_columns(raw)
    normalized = _coerce_market_data(normalized)
    normalized = _apply_volume_policy(normalized, timeframe)

    normalized["timeframe"] = timeframe
    normalized = normalized.dropna(subset=["time", "open", "high", "low", "close"])
    normalized = normalized.drop_duplicates(subset=["time"])
    normalized = normalized.sort_values("time").reset_index(drop=True)

    ordered_columns = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "timeframe",
        "has_real_volume",
    ]
    if "timeframe_code" in normalized.columns:
        ordered_columns.append("timeframe_code")

    return normalized[ordered_columns]


def load_xauusd_timeframes(base_dir: str | Path = "data/raw/timeframes") -> dict[str, pd.DataFrame]:
    """Load and validate all expected XAUUSD timeframe CSV files."""
    root = Path(base_dir)
    result = {}

    for timeframe, filename in TIMEFRAME_FILES.items():
        result[timeframe] = load_timeframe_csv(root / filename, timeframe)

    return result


def _apply_volume_policy(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    result = df.copy()

    candidate_column = None
    if "timeframe_code" in result.columns:
        candidate_column = "timeframe_code"
    elif "volume" in result.columns and _looks_like_timeframe_code(result["volume"], timeframe):
        candidate_column = "volume"
    elif "extra" in result.columns and _looks_like_timeframe_code(result["extra"], timeframe):
        candidate_column = "extra"

    if candidate_column is not None:
        result["timeframe_code"] = pd.to_numeric(result[candidate_column], errors="coerce")
        if candidate_column != "timeframe_code":
            result = result.drop(columns=[candidate_column])
        result["volume"] = 1.0
        result["has_real_volume"] = False
        return result

    if "volume" in result.columns:
        result["volume"] = pd.to_numeric(result["volume"], errors="coerce")
        result["has_real_volume"] = True
        result["volume"] = result["volume"].fillna(1.0)
        return result

    if "extra" in result.columns:
        result["volume"] = pd.to_numeric(result["extra"], errors="coerce").fillna(1.0)
        result = result.drop(columns=["extra"])
        result["has_real_volume"] = True
        return result

    result["volume"] = 1.0
    result["has_real_volume"] = False
    return result


def _coerce_market_data(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["time"] = pd.to_datetime(result["time"], errors="coerce")

    for column in ["open", "high", "low", "close"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    for optional_column in ["volume", "timeframe_code", "extra"]:
        if optional_column in result.columns:
            result[optional_column] = pd.to_numeric(result[optional_column], errors="coerce")

    return result


def _rename_headerless_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    column_count = len(result.columns)

    if column_count < 5:
        raise ValueError("Headerless timeframe CSV must have at least 5 columns")

    names = ["time", "open", "high", "low", "close"]
    if column_count == 6:
        names.append("extra")
    elif column_count >= 7:
        names.extend(["volume", "extra"])
        names.extend(f"extra_{index}" for index in range(7, column_count))

    result.columns = names[:column_count]
    return result


def _rename_header_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "date": "time",
        "datetime": "time",
        "timestamp": "time",
        "time": "time",
        "open": "open",
        "o": "open",
        "high": "high",
        "h": "high",
        "low": "low",
        "l": "low",
        "close": "close",
        "c": "close",
        "volume": "volume",
        "vol": "volume",
        "tick_volume": "volume",
        "timeframe": "timeframe_code",
        "timeframe_code": "timeframe_code",
        "tf": "timeframe_code",
        "tf_code": "timeframe_code",
    }

    result = df.copy()
    rename_map = {}
    used_names = set()

    for column in result.columns:
        normalized = aliases.get(column)
        if normalized is None:
            normalized = _normalize_header_name(column)
        if normalized in used_names:
            continue
        rename_map[column] = normalized
        used_names.add(normalized)

    return result.rename(columns=rename_map)


def _normalize_header_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or name


def _has_generic_columns(df: pd.DataFrame) -> bool:
    return all(column.isdigit() for column in df.columns)


def _looks_like_timeframe_code(series: pd.Series, timeframe: str) -> bool:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return False

    expected_minutes = TIMEFRAME_MINUTES.get(_normalize_timeframe_name(timeframe))
    unique_values = sorted(float(value) for value in numeric.unique())

    if expected_minutes is not None and len(unique_values) == 1:
        return abs(unique_values[0] - expected_minutes) < 1e-9

    if expected_minutes is None:
        return False

    mode_value = float(numeric.mode().iloc[0])
    mode_frequency = float((numeric == mode_value).mean())
    mode_matches_timeframe = abs(mode_value - expected_minutes) < 1e-9
    duration_like_range = max(unique_values) <= expected_minutes * 1.2
    if mode_matches_timeframe and mode_frequency >= 0.5 and duration_like_range:
        return True

    integer_like = all(abs(value - round(value)) < 1e-9 for value in unique_values)
    small_set = len(unique_values) <= 5
    positive = all(value > 0 for value in unique_values)
    within_timeframe = max(unique_values) <= expected_minutes

    return integer_like and small_set and positive and within_timeframe


def _normalize_timeframe_name(timeframe_name: str) -> str:
    normalized = str(timeframe_name).strip().upper()
    aliases = {
        "1M": "M1",
        "5M": "M5",
        "15M": "M15",
        "30M": "M30",
        "1H": "H1",
        "4H": "H4",
    }
    return aliases.get(normalized, normalized)


def _looks_like_datetime(value: str) -> bool:
    if not value:
        return False
    return pd.notna(pd.to_datetime(value, errors="coerce"))


def _read_text_sample(path: str | Path, byte_count: int = 8192) -> str:
    with Path(path).open("rb") as handle:
        return handle.read(byte_count).decode("utf-8-sig", errors="replace")
