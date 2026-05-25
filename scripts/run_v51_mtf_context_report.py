"""Build a V51 multi-timeframe context report from local XAU/USD CSV files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.timeframe_loader import (
    detect_csv_separator,
    detect_header_or_no_header,
    normalize_ohlc_columns,
)
from src.strategy_lab.strategy_v51_demo_intraday import DEFAULT_V51_CONFIG_PATH, load_v51_config


DEFAULT_DATA_DIR = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
SUMMARY_FILENAME = "v51_mtf_context_summary.csv"
LATEST_FILENAME = "v51_mtf_context_latest.txt"
TIMEFRAMES = ("D1", "H4", "H1", "M15", "M5", "M1")
TIMEFRAME_MINUTES = {"D1": 1440, "H4": 240, "H1": 60, "M15": 15, "M5": 5, "M1": 1}
FAST_EMA = 21
SLOW_EMA = 55
ATR_PERIOD = 14
SWING_LOOKBACK = 20

SUMMARY_COLUMNS = [
    "generated_at",
    "symbol",
    "final_bias",
    "final_reason",
    "timeframe",
    "status",
    "source_file",
    "rows",
    "latest_candle_time",
    "candle_age_minutes",
    "last_close",
    "trend_direction",
    "ema_fast",
    "ema_slow",
    "ema_alignment",
    "recent_swing_high",
    "recent_swing_low",
    "atr",
    "volatility_regime",
    "distance_from_support",
    "distance_from_resistance",
    "context_note",
]


@dataclass(frozen=True)
class MTFContextResult:
    """Paths and final bias for one V51 MTF context report run."""

    status: str
    final_bias: str
    summary_path: Path
    latest_path: Path


def run_v51_mtf_context_report(
    *,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    now: pd.Timestamp | None = None,
) -> MTFContextResult:
    """Generate a local-only MTF context report for V51 diagnostics."""
    config = load_v51_config(config_path)
    now = pd.Timestamp.now() if now is None else pd.Timestamp(now).tz_localize(None)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_FILENAME
    latest_path = output_dir / LATEST_FILENAME

    loaded = load_available_timeframes(Path(data_dir))
    contexts = []
    for timeframe in TIMEFRAMES:
        item = loaded.get(timeframe)
        if item is None:
            contexts.append(missing_context(timeframe, config.symbol))
            continue
        frame, source_file, status = item
        contexts.append(analyze_timeframe(timeframe, frame, source_file=source_file, symbol=config.symbol, now=now, status=status))

    final_bias, final_reason = build_final_bias(contexts)
    rows = []
    generated_at = pd.Timestamp.now().isoformat()
    for context in contexts:
        row = {
            "generated_at": generated_at,
            "symbol": config.symbol,
            "final_bias": final_bias,
            "final_reason": final_reason,
            **context,
        }
        rows.append(row)

    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(summary_path, index=False)
    latest_path.write_text(build_latest_text(config.symbol, final_bias, final_reason, contexts), encoding="utf-8")
    return MTFContextResult("OK", final_bias, summary_path, latest_path)


def load_available_timeframes(data_dir: Path) -> dict[str, tuple[pd.DataFrame, Path, str]]:
    """Load available local timeframe files; derive D1 if no D1 CSV exists."""
    result: dict[str, tuple[pd.DataFrame, Path, str]] = {}
    for timeframe in ("H4", "H1", "M15", "M5", "M1", "D1"):
        source = find_timeframe_file(data_dir, timeframe)
        if source is None:
            continue
        try:
            result[timeframe] = (load_ohlcv_file(source), source, "OK")
        except Exception:
            result[timeframe] = (pd.DataFrame(), source, "ERROR")

    if "D1" not in result:
        base = next((result[timeframe] for timeframe in ("H4", "H1", "M15") if timeframe in result), None)
        if base is not None and not base[0].empty:
            result["D1"] = (resample_to_d1(base[0]), base[1], "DERIVED")
    return result


def find_timeframe_file(data_dir: Path, timeframe: str) -> Path | None:
    """Find a local file for a timeframe using supported project naming variants."""
    tf_lower = timeframe.lower()
    candidates = []
    if timeframe == "M15":
        candidates.extend([data_dir / "xauusd.csv", data_dir / "XAUUSD.csv"])
    candidates.extend(
        [
            data_dir / f"xauusd_{tf_lower}.csv",
            data_dir / f"XAUUSD_{timeframe}.csv",
            data_dir / "timeframes" / f"xauusd_{tf_lower}.csv",
            data_dir / "timeframes" / f"XAUUSD_{timeframe}.csv",
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def load_ohlcv_file(path: str | Path) -> pd.DataFrame:
    """Load a local OHLCV file into standard lowercase columns."""
    csv_path = Path(path)
    separator = detect_csv_separator(csv_path)
    header_mode = detect_header_or_no_header(csv_path)
    raw = pd.read_csv(csv_path, sep=separator, header=0 if header_mode == "header" else None, engine="python")
    normalized = normalize_ohlc_columns(raw)
    normalized["time"] = pd.to_datetime(normalized["time"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(1.0)
    else:
        normalized["volume"] = 1.0
    normalized = normalized.dropna(subset=["time", "open", "high", "low", "close"])
    normalized = normalized.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return normalized[["time", "open", "high", "low", "close", "volume"]]


def resample_to_d1(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive D1 candles from the highest available intraday data."""
    data = frame.copy()
    data["time"] = pd.to_datetime(data["time"], errors="coerce")
    data = data.dropna(subset=["time"]).set_index("time").sort_index()
    resampled = data.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return resampled.dropna(subset=["open", "high", "low", "close"]).reset_index()


def analyze_timeframe(
    timeframe: str,
    frame: pd.DataFrame,
    *,
    source_file: Path,
    symbol: str,
    now: pd.Timestamp,
    status: str = "OK",
) -> dict[str, Any]:
    """Calculate one timeframe context row."""
    if frame.empty or status == "ERROR":
        return missing_context(timeframe, symbol, status=status, source_file=source_file)

    data = frame.tail(max(SLOW_EMA + ATR_PERIOD + SWING_LOOKBACK, 120)).copy()
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    ema_fast = close.ewm(span=FAST_EMA, adjust=False).mean()
    ema_slow = close.ewm(span=SLOW_EMA, adjust=False).mean()
    atr = calculate_atr(data)
    latest_close = float(close.iloc[-1])
    latest_fast = float(ema_fast.iloc[-1])
    latest_slow = float(ema_slow.iloc[-1])
    latest_atr = float(atr.iloc[-1]) if not atr.dropna().empty else 0.0
    recent_high = float(high.tail(SWING_LOOKBACK).max())
    recent_low = float(low.tail(SWING_LOOKBACK).min())
    alignment = ema_alignment(latest_close, latest_fast, latest_slow)
    trend = trend_direction(alignment, ema_fast, ema_slow)
    latest_time = pd.Timestamp(data["time"].iloc[-1]).tz_localize(None)
    age = max(0.0, (now - latest_time).total_seconds() / 60.0)
    return {
        "timeframe": timeframe,
        "status": status,
        "source_file": str(source_file),
        "rows": int(len(frame)),
        "latest_candle_time": latest_time.isoformat(),
        "candle_age_minutes": age,
        "last_close": latest_close,
        "trend_direction": trend,
        "ema_fast": latest_fast,
        "ema_slow": latest_slow,
        "ema_alignment": alignment,
        "recent_swing_high": recent_high,
        "recent_swing_low": recent_low,
        "atr": latest_atr,
        "volatility_regime": volatility_regime(atr),
        "distance_from_support": latest_close - recent_low,
        "distance_from_resistance": recent_high - latest_close,
        "context_note": context_note(timeframe, trend, alignment, latest_close, recent_low, recent_high),
    }


def missing_context(
    timeframe: str,
    symbol: str,
    *,
    status: str = "MISSING",
    source_file: Path | None = None,
) -> dict[str, Any]:
    """Return a placeholder context for a missing timeframe."""
    return {
        "timeframe": timeframe,
        "status": status,
        "source_file": "" if source_file is None else str(source_file),
        "rows": 0,
        "latest_candle_time": "",
        "candle_age_minutes": "",
        "last_close": "",
        "trend_direction": "UNKNOWN",
        "ema_fast": "",
        "ema_slow": "",
        "ema_alignment": "UNKNOWN",
        "recent_swing_high": "",
        "recent_swing_low": "",
        "atr": "",
        "volatility_regime": "UNKNOWN",
        "distance_from_support": "",
        "distance_from_resistance": "",
        "context_note": f"{symbol} {timeframe} context unavailable: {status}",
    }


def calculate_atr(frame: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Calculate ATR from standard OHLC columns."""
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def ema_alignment(last_close: float, ema_fast: float, ema_slow: float) -> str:
    if last_close > ema_fast > ema_slow:
        return "BULLISH"
    if last_close < ema_fast < ema_slow:
        return "BEARISH"
    return "MIXED"


def trend_direction(alignment: str, ema_fast: pd.Series, ema_slow: pd.Series) -> str:
    fast_slope = float(ema_fast.iloc[-1] - ema_fast.iloc[max(0, len(ema_fast) - 6)])
    slow_slope = float(ema_slow.iloc[-1] - ema_slow.iloc[max(0, len(ema_slow) - 6)])
    if alignment == "BULLISH" and fast_slope >= 0 and slow_slope >= 0:
        return "BULL"
    if alignment == "BEARISH" and fast_slope <= 0 and slow_slope <= 0:
        return "BEAR"
    return "RANGE"


def volatility_regime(atr: pd.Series) -> str:
    values = pd.to_numeric(atr, errors="coerce").dropna()
    if values.empty:
        return "UNKNOWN"
    latest = float(values.iloc[-1])
    median = float(values.tail(100).median())
    if median <= 0:
        return "UNKNOWN"
    ratio = latest / median
    if ratio >= 1.3:
        return "HIGH"
    if ratio <= 0.7:
        return "LOW"
    return "NORMAL"


def context_note(timeframe: str, trend: str, alignment: str, last_close: float, support: float, resistance: float) -> str:
    return (
        f"{timeframe}: trend={trend}, ema_alignment={alignment}, "
        f"close={last_close:.2f}, support={support:.2f}, resistance={resistance:.2f}"
    )


def build_final_bias(contexts: list[dict[str, Any]]) -> tuple[str, str]:
    """Aggregate timeframe context into a conservative operational bias."""
    by_tf = {context["timeframe"]: context for context in contexts}
    available = [context for context in contexts if context["status"] in {"OK", "DERIVED"}]
    if len(available) < 2:
        return "NO_TRADE_CONTEXT", "Not enough multi-timeframe context is available."

    higher = [by_tf[tf]["trend_direction"] for tf in ("D1", "H4") if by_tf.get(tf, {}).get("status") in {"OK", "DERIVED"}]
    h1 = by_tf.get("H1", {}).get("trend_direction", "UNKNOWN")
    m15 = by_tf.get("M15", {}).get("trend_direction", "UNKNOWN")
    lower = [by_tf[tf]["trend_direction"] for tf in ("M5", "M1") if by_tf.get(tf, {}).get("status") == "OK"]

    bull_score = sum(direction == "BULL" for direction in higher) * 2 + (h1 == "BULL") + (m15 == "BULL")
    bear_score = sum(direction == "BEAR" for direction in higher) * 2 + (h1 == "BEAR") + (m15 == "BEAR")
    if lower:
        bull_score += 0.5 * sum(direction == "BULL" for direction in lower)
        bear_score += 0.5 * sum(direction == "BEAR" for direction in lower)

    explanation = (
        f"D1/H4 bias={','.join(higher) or 'UNKNOWN'}; "
        f"H1 structure={h1}; M15 setup environment={m15}; "
        f"M5/M1 timing readiness={','.join(lower) or 'UNAVAILABLE'}"
    )
    if bull_score >= 4 and bear_score == 0:
        return "LONG_BIAS", explanation
    if bear_score >= 4 and bull_score == 0:
        return "SHORT_BIAS", explanation
    if bull_score == 0 and bear_score == 0:
        return "NO_TRADE_CONTEXT", explanation
    return "MIXED", explanation


def build_latest_text(symbol: str, final_bias: str, final_reason: str, contexts: list[dict[str, Any]]) -> str:
    """Render the latest MTF context as a concise text report."""
    lines = [
        "V51 MTF Context Report",
        "=" * 72,
        f"Symbol: {symbol}",
        f"Final bias: {final_bias}",
        f"Why: {final_reason}",
        "",
        "Professional Context",
        "-" * 72,
        f"D1/H4 bias: {_tf_reason(contexts, ('D1', 'H4'))}",
        f"H1 structure: {_tf_reason(contexts, ('H1',))}",
        f"M15 setup environment: {_tf_reason(contexts, ('M15',))}",
        f"M5/M1 timing readiness: {_tf_reason(contexts, ('M5', 'M1'))}",
        "",
        "Support / Resistance",
        "-" * 72,
    ]
    for context in contexts:
        lines.append(
            f"{context['timeframe']} [{context['status']}]: close={context['last_close']} "
            f"support={context['recent_swing_low']} resistance={context['recent_swing_high']} "
            f"dist_support={context['distance_from_support']} dist_resistance={context['distance_from_resistance']}"
        )
    lines.extend(["", "No orders were sent. This is context diagnostics only.", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Local data directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Diagnostics output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_mtf_context_report(config_path=args.config, data_dir=args.data_dir, output_dir=args.output_dir)
    print("=" * 72)
    print("XAU Auto Trader - V51 MTF Context Report")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Final bias: {result.final_bias}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is context diagnostics only.")


def _tf_reason(contexts: list[dict[str, Any]], timeframes: tuple[str, ...]) -> str:
    by_tf = {context["timeframe"]: context for context in contexts}
    parts = []
    for timeframe in timeframes:
        context = by_tf.get(timeframe)
        if context is None:
            continue
        parts.append(f"{timeframe}={context['trend_direction']} ({context['status']})")
    return ", ".join(parts) if parts else "UNAVAILABLE"


if __name__ == "__main__":
    main()
