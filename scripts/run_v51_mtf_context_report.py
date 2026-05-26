"""Build a V51 multi-timeframe context report from local XAU/USD CSV files."""

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
PRICE_MISMATCH_MAX_RATIO = 0.02

SUMMARY_COLUMNS = [
    "generated_at",
    "symbol",
    "final_bias",
    "final_reason",
    "timeframe",
    "status",
    "data_status",
    "used_in_bias",
    "source_file",
    "rows",
    "latest_candle_time",
    "candle_age_minutes",
    "age_minutes",
    "last_close",
    "primary_close",
    "price_gap_from_primary",
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


@dataclass(frozen=True)
class LoadedTimeframe:
    """Loaded CSV data plus alignment metadata."""

    frame: pd.DataFrame
    source_file: Path | None
    data_status: str
    used_in_bias: bool
    primary_close: float | None
    price_gap_from_primary: float | None
    reason: str


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

    primary = load_primary_reference(Path(data_dir), now=now)
    loaded = load_available_timeframes(Path(data_dir), primary=primary, now=now)
    contexts = []
    for timeframe in TIMEFRAMES:
        item = loaded.get(timeframe)
        if item is None:
            contexts.append(missing_context(timeframe, config.symbol, primary_close=primary.primary_close))
            continue
        contexts.append(analyze_timeframe(timeframe, item, symbol=config.symbol, now=now))

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


def load_available_timeframes(data_dir: Path, *, primary: LoadedTimeframe, now: pd.Timestamp) -> dict[str, LoadedTimeframe]:
    """Load available local timeframe files; derive D1 if no D1 CSV exists."""
    result: dict[str, LoadedTimeframe] = {}
    for timeframe in ("H4", "H1", "M15", "M5", "M1", "D1"):
        source = find_timeframe_file(data_dir, timeframe)
        if source is None:
            continue
        loaded = load_timeframe_with_alignment(timeframe, source, primary=primary, now=now)
        if timeframe == "M15" and loaded.data_status not in {"OK", "EXCLUDED"} and primary.data_status == "OK":
            loaded = LoadedTimeframe(
                frame=primary.frame,
                source_file=primary.source_file,
                data_status="OK",
                used_in_bias=True,
                primary_close=primary.primary_close,
                price_gap_from_primary=0.0,
                reason=f"M15 fallback to primary CSV because {source.name} status={loaded.data_status}",
            )
        result[timeframe] = loaded

    if "D1" not in result:
        base = next(
            (result[timeframe] for timeframe in ("H4", "H1", "M15") if timeframe in result and result[timeframe].used_in_bias),
            None,
        )
        if base is not None and not base.frame.empty:
            result["D1"] = LoadedTimeframe(
                frame=resample_to_d1(base.frame),
                source_file=base.source_file,
                data_status="OK",
                used_in_bias=True,
                primary_close=primary.primary_close,
                price_gap_from_primary=base.price_gap_from_primary,
                reason="D1 derived from aligned intraday data",
            )
    return result


def load_primary_reference(data_dir: Path, *, now: pd.Timestamp) -> LoadedTimeframe:
    """Load the primary M15 CSV used as data-alignment reference."""
    source = next((path for path in (data_dir / "xauusd.csv", data_dir / "XAUUSD.csv") if path.exists()), None)
    if source is None:
        return LoadedTimeframe(
            frame=pd.DataFrame(),
            source_file=None,
            data_status="MISSING",
            used_in_bias=False,
            primary_close=None,
            price_gap_from_primary=None,
            reason="primary CSV missing",
        )
    frame, status, reason = load_ohlcv_file_with_status(source)
    primary_close = latest_close(frame) if status == "OK" else None
    if status == "OK" and alignment_freshness_status("M15", frame, primary=_missing_primary_stub(), now=now) == "STALE":
        status = "STALE"
    return LoadedTimeframe(
        frame=frame,
        source_file=source,
        data_status=status,
        used_in_bias=status == "OK",
        primary_close=primary_close,
        price_gap_from_primary=0.0 if primary_close is not None else None,
        reason=reason,
    )


def load_timeframe_with_alignment(
    timeframe: str,
    source: Path,
    *,
    primary: LoadedTimeframe,
    now: pd.Timestamp,
) -> LoadedTimeframe:
    """Load one timeframe and mark whether it can be used in final bias."""
    frame, status, reason = load_ohlcv_file_with_status(source)
    if status != "OK":
        return LoadedTimeframe(frame, source, status, False, primary.primary_close, None, reason)
    if primary.source_file is not None and source.resolve() == primary.source_file.resolve() and primary.data_status != "OK":
        return LoadedTimeframe(
            frame,
            source,
            primary.data_status,
            False,
            primary.primary_close,
            0.0 if primary.primary_close is not None else None,
            "primary CSV is stale or unavailable",
        )

    close = latest_close(frame)
    if close is None:
        return LoadedTimeframe(frame, source, "EMPTY", False, primary.primary_close, None, "no latest close")

    freshness_status = alignment_freshness_status(timeframe, frame, primary=primary, now=now)
    price_gap = None if primary.primary_close is None else abs(close - primary.primary_close)
    price_status = alignment_price_status(close, primary.primary_close)
    data_status = "OK"
    used = True
    reason = "aligned with primary reference"
    if freshness_status is not None:
        data_status = freshness_status
        used = False
        reason = "latest candle is stale versus primary reference"
    elif price_status is not None:
        data_status = price_status
        used = False
        reason = "latest close too far from primary close"
    if primary.data_status != "OK" and timeframe != "M15":
        data_status = "EXCLUDED"
        used = False
        reason = "primary reference unavailable for alignment"

    return LoadedTimeframe(
        frame=frame,
        source_file=source,
        data_status=data_status,
        used_in_bias=used,
        primary_close=primary.primary_close,
        price_gap_from_primary=price_gap,
        reason=reason,
    )


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
    frame, status, reason = load_ohlcv_file_with_status(path)
    if status != "OK":
        raise ValueError(reason)
    return frame


def load_ohlcv_file_with_status(path: str | Path) -> tuple[pd.DataFrame, str, str]:
    """Load a local OHLCV file and return a guard status instead of raising."""
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame(), "MISSING", "file missing"
    if csv_path.stat().st_size == 0:
        return pd.DataFrame(), "EMPTY", "file empty"
    try:
        separator = detect_csv_separator(csv_path)
        header_mode = detect_header_or_no_header(csv_path)
        raw = pd.read_csv(csv_path, sep=separator, header=0 if header_mode == "header" else None, engine="python")
    except EmptyDataError:
        return pd.DataFrame(), "EMPTY", "file empty"
    try:
        normalized = normalize_ohlc_columns(raw)
    except ValueError as exc:
        return pd.DataFrame(), "INVALID_COLUMNS", str(exc)
    normalized["time"] = pd.to_datetime(normalized["time"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(1.0)
    else:
        normalized["volume"] = 1.0
    normalized = normalized.dropna(subset=["time", "open", "high", "low", "close"])
    normalized = normalized.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    if normalized.empty:
        return normalized, "EMPTY", "no valid OHLC rows"
    return normalized[["time", "open", "high", "low", "close", "volume"]], "OK", "loaded"


def resample_to_d1(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive D1 candles from the highest available intraday data."""
    data = frame.copy()
    data["time"] = pd.to_datetime(data["time"], errors="coerce")
    data = data.dropna(subset=["time"]).set_index("time").sort_index()
    resampled = data.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return resampled.dropna(subset=["open", "high", "low", "close"]).reset_index()


def analyze_timeframe(
    timeframe: str,
    loaded: LoadedTimeframe,
    *,
    symbol: str,
    now: pd.Timestamp,
) -> dict[str, Any]:
    """Calculate one timeframe context row."""
    frame = loaded.frame
    if frame.empty or loaded.data_status in {"MISSING", "EMPTY", "INVALID_COLUMNS"}:
        return missing_context(
            timeframe,
            symbol,
            status=loaded.data_status,
            source_file=loaded.source_file,
            primary_close=loaded.primary_close,
            price_gap_from_primary=loaded.price_gap_from_primary,
            reason=loaded.reason,
        )

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
        "status": loaded.data_status,
        "data_status": loaded.data_status,
        "used_in_bias": loaded.used_in_bias,
        "source_file": "" if loaded.source_file is None else str(loaded.source_file),
        "rows": int(len(frame)),
        "latest_candle_time": latest_time.isoformat(),
        "candle_age_minutes": age,
        "age_minutes": age,
        "last_close": latest_close,
        "primary_close": "" if loaded.primary_close is None else loaded.primary_close,
        "price_gap_from_primary": "" if loaded.price_gap_from_primary is None else loaded.price_gap_from_primary,
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
        "context_note": context_note(timeframe, trend, alignment, latest_close, recent_low, recent_high, loaded.reason),
    }


def missing_context(
    timeframe: str,
    symbol: str,
    *,
    status: str = "MISSING",
    source_file: Path | None = None,
    primary_close: float | None = None,
    price_gap_from_primary: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a placeholder context for a missing timeframe."""
    return {
        "timeframe": timeframe,
        "status": status,
        "data_status": status,
        "used_in_bias": False,
        "source_file": "" if source_file is None else str(source_file),
        "rows": 0,
        "latest_candle_time": "",
        "candle_age_minutes": "",
        "age_minutes": "",
        "last_close": "",
        "primary_close": "" if primary_close is None else primary_close,
        "price_gap_from_primary": "" if price_gap_from_primary is None else price_gap_from_primary,
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
        "context_note": f"{symbol} {timeframe} context unavailable: {reason or status}",
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


def alignment_freshness_status(
    timeframe: str,
    frame: pd.DataFrame,
    *,
    primary: LoadedTimeframe,
    now: pd.Timestamp,
) -> str | None:
    latest = latest_timestamp(frame)
    if latest is None:
        return "EMPTY"
    primary_latest = latest_timestamp(primary.frame)
    if primary_latest is not None:
        lag_minutes = (primary_latest - latest).total_seconds() / 60.0
        if lag_minutes > allowed_alignment_lag_minutes(timeframe):
            return "STALE"
        return None
    age_minutes = max(0.0, (now - latest).total_seconds() / 60.0)
    if age_minutes > allowed_absolute_age_minutes(timeframe):
        return "STALE"
    return None


def alignment_price_status(close: float, primary_close: float | None) -> str | None:
    if primary_close is None or primary_close <= 0:
        return None
    if abs(close - primary_close) / primary_close > PRICE_MISMATCH_MAX_RATIO:
        return "PRICE_MISMATCH"
    return None


def allowed_alignment_lag_minutes(timeframe: str) -> float:
    return max(float(TIMEFRAME_MINUTES.get(timeframe, 15)) * 1.5, 30.0)


def allowed_absolute_age_minutes(timeframe: str) -> float:
    return max(float(TIMEFRAME_MINUTES.get(timeframe, 15)) * 3.0, 90.0)


def latest_timestamp(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame.empty or "time" not in frame.columns:
        return None
    times = pd.to_datetime(frame["time"], errors="coerce").dropna()
    if times.empty:
        return None
    return pd.Timestamp(times.max()).tz_localize(None)


def latest_close(frame: pd.DataFrame) -> float | None:
    if frame.empty or "close" not in frame.columns:
        return None
    closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1])


def _missing_primary_stub() -> LoadedTimeframe:
    return LoadedTimeframe(
        frame=pd.DataFrame(),
        source_file=None,
        data_status="MISSING",
        used_in_bias=False,
        primary_close=None,
        price_gap_from_primary=None,
        reason="primary unavailable",
    )


def context_note(
    timeframe: str,
    trend: str,
    alignment: str,
    last_close: float,
    support: float,
    resistance: float,
    alignment_note: str,
) -> str:
    return (
        f"{timeframe}: trend={trend}, ema_alignment={alignment}, "
        f"close={last_close:.2f}, support={support:.2f}, resistance={resistance:.2f}, "
        f"alignment={alignment_note}"
    )


def build_final_bias(contexts: list[dict[str, Any]]) -> tuple[str, str]:
    """Aggregate timeframe context into a conservative operational bias."""
    by_tf = {context["timeframe"]: context for context in contexts}
    available = [context for context in contexts if bool(context.get("used_in_bias"))]
    if len(available) < 2:
        excluded = ", ".join(f"{context['timeframe']}={context['data_status']}" for context in contexts)
        return "NO_TRADE_CONTEXT", f"Not enough aligned multi-timeframe context is available. Data status: {excluded}"

    higher = [by_tf[tf]["trend_direction"] for tf in ("D1", "H4") if bool(by_tf.get(tf, {}).get("used_in_bias"))]
    h1 = by_tf.get("H1", {}).get("trend_direction", "UNKNOWN") if bool(by_tf.get("H1", {}).get("used_in_bias")) else "UNUSED"
    m15 = by_tf.get("M15", {}).get("trend_direction", "UNKNOWN") if bool(by_tf.get("M15", {}).get("used_in_bias")) else "UNUSED"
    lower = [by_tf[tf]["trend_direction"] for tf in ("M5", "M1") if bool(by_tf.get(tf, {}).get("used_in_bias"))]

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
    lines.extend(["", "Data Alignment", "-" * 72])
    for context in contexts:
        lines.append(
            f"{context['timeframe']} file={context['source_file']} "
            f"latest={context['latest_candle_time']} close={context['last_close']} "
            f"age_minutes={context['age_minutes']} price_gap_vs_primary={context['price_gap_from_primary']} "
            f"status={context['data_status']} used_in_bias={context['used_in_bias']}"
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
        parts.append(f"{timeframe}={context['trend_direction']} ({context['data_status']}, used={context['used_in_bias']})")
    return ", ".join(parts) if parts else "UNAVAILABLE"


if __name__ == "__main__":
    main()
