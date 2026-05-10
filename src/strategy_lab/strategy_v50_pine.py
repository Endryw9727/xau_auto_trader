"""
Strategy Lab V50 Pine translation candidate.

This module is a research-safe approximation of reference/xau_v50_strategy.pine.
It builds technical features and returns analytical BUY / SELL / NO_TRADE
signals only. It does not execute trades or contact brokers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.market_data.timeframe_loader import load_xauusd_timeframes
from src.strategy.indicators import add_adx, add_atr, add_ema, add_rsi
from src.strategy.rules import StrategyConfig, calculate_trade_levels
from src.strategy.signals import TradingSignal
from src.strategy_lab.v50_mtf_features import build_v50_mtf_dataset


STRATEGY_NAME = "v50_pine_technical_strategy"
MTF_STRATEGY_NAME = "v50_pine_mtf_strategy"
REQUIRED_HISTORY_CANDLES = 500
DEFAULT_TIMEFRAMES_DIR = Path("data/raw/timeframes")

WILLIAMS_R_PERIOD = 24
ADX_PERIOD = 14
ATR_PERIOD = 14
RSI_PERIOD = 14
VOLUME_LOOKBACK = 20
STRUCTURE_LOOKBACK = 20
SHIFT_LOOKBACK = 24
LATE_IMPULSE_LOOKBACK = 24

MIN_ACTIVE_ADX = 16.0
SCORE_THRESHOLD = 72.0
SCORE_GAP = 8.0
MAX_EXTENSION_ATR = 1.8
LATE_IMPULSE_ATR_MIN = 3.2
LATE_IMPULSE_EXTENSION_ATR = 1.15
LATE_IMPULSE_RSI = 58.0

V50_REQUIRED_COLUMNS = {
    "v50_score_long",
    "v50_score_short",
    "v50_quality_long_ok",
    "v50_quality_short_ok",
    "v50_setup_long",
    "v50_setup_short",
}
V50_MTF_REQUIRED_COLUMNS = {
    "ema21",
    "ema50",
    "ema200",
    "rsi",
    "williams_r",
    "plus_di",
    "minus_di",
    "adx",
    "atr",
    "ema21_10",
    "ema50_10",
    "williams_r_10",
    "plus_di_10",
    "minus_di_10",
    "close_15",
    "ema21_15",
    "ema50_15",
    "ema200_15",
    "rsi_15",
    "close_1h",
    "ema50_1h",
    "ema200_1h",
    "rsi_1h",
    "plus_di_1h",
    "minus_di_1h",
    "adx_1h",
    "close_4h",
    "ema50_4h",
    "ema200_4h",
    "ema50_slope_4h",
    "rsi_4h",
}


def build_v50_features(data: pd.DataFrame) -> pd.DataFrame:
    """
    Build V50-inspired research features.

    The row count and index are preserved. When the input timeframe is higher
    than 5m/10m, lower-timeframe trigger features are approximated from the
    available base timeframe and marked in v50_approximation_mode.
    """
    _validate_ohlcv(data)

    result = _add_indicator_pack(data.copy())
    result = _add_local_aliases(result)

    base_minutes = _infer_timeframe_minutes(result.index)
    result["v50_base_timeframe_minutes"] = base_minutes if base_minutes is not None else np.nan

    approximation_parts: list[str] = []
    for label, rule, target_minutes in [
        ("4h", "4h", 240),
        ("1h", "1h", 60),
        ("15m", "15min", 15),
        ("10m", "10min", 10),
        ("5m", "5min", 5),
    ]:
        frame_pack, approximated = _build_timeframe_pack(
            result,
            rule=rule,
            target_minutes=target_minutes,
            base_minutes=base_minutes,
        )
        if approximated:
            approximation_parts.append(label)

        for column in frame_pack.columns:
            result[f"v50_{label}_{column}"] = frame_pack[column]

    if approximation_parts:
        result["v50_approximation_mode"] = "approximated_" + "_".join(approximation_parts)
    else:
        result["v50_approximation_mode"] = "native_or_resampled"

    _add_session_features(result)
    _add_structure_features(result)
    result = result.copy()
    _add_mtf_conditions(result)
    result = result.copy()
    _add_quality_features(result)
    result = result.copy()
    _add_scores(result)

    return result.replace([np.inf, -np.inf], np.nan).copy()


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate a V50-inspired technical research signal."""
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    features = df if V50_REQUIRED_COLUMNS.issubset(df.columns) else build_v50_features(df)
    latest = features.iloc[-1]
    timestamp = _get_timestamp(features)

    side = _select_signal_side(latest)
    if side == "NO_TRADE":
        return _no_trade(timestamp, config, _build_no_trade_reason(latest))

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)

    if risk_reward < config.min_risk_reward:
        return _no_trade(
            timestamp,
            config,
            f"V50 Pine approximation RR below minimum | Side={side} | RR={risk_reward:.2f}",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
        )

    score = float(latest["v50_score_long"] if side == "BUY" else latest["v50_score_short"])
    opposite_score = float(latest["v50_score_short"] if side == "BUY" else latest["v50_score_long"])

    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe=config.timeframe,
        side=side,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=min(score, 100.0),
        reason=(
            "V50 Pine technical approximation"
            f" | Side={side}"
            f" | score={score:.1f}"
            f" | opposite_score={opposite_score:.1f}"
            f" | session={latest.get('v50_session', 'Unknown')}"
            f" | mode={latest.get('v50_approximation_mode', 'unknown')}"
            f" | RR={risk_reward:.2f}"
        ),
    )


def generate_mtf_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate the M5-based V50 MTF research signal."""
    if config is None:
        config = StrategyConfig(timeframe="5m")

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    if not V50_MTF_REQUIRED_COLUMNS.issubset(df.columns):
        return generate_signal(df, config)

    latest = df.iloc[-1]
    timestamp = _get_timestamp(df)
    mtf_state = _calculate_mtf_state(latest)
    side = _select_mtf_side(mtf_state)

    if side == "NO_TRADE":
        return _no_trade(timestamp, config, _build_mtf_no_trade_reason(latest, mtf_state))

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)

    if risk_reward < config.min_risk_reward:
        return _no_trade(
            timestamp,
            config,
            f"V50 Pine MTF RR below minimum | Side={side} | RR={risk_reward:.2f}",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
        )

    score = mtf_state["score_long"] if side == "BUY" else mtf_state["score_short"]
    opposite_score = mtf_state["score_short"] if side == "BUY" else mtf_state["score_long"]

    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe="5m",
        side=side,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=min(float(score), 100.0),
        reason=(
            "V50 Pine MTF research candidate"
            f" | Side={side}"
            f" | score={float(score):.1f}"
            f" | opposite_score={float(opposite_score):.1f}"
            f" | session={latest.get('session', 'Unknown')}"
            f" | RR={risk_reward:.2f}"
        ),
    )


def prepare_mtf_backtest_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Load local MTF CSVs and build the M5 research dataset when available.

    The input length is used as the Strategy Lab quick/full window selector.
    """
    try:
        timeframes = load_xauusd_timeframes(DEFAULT_TIMEFRAMES_DIR)
        mtf_data = build_v50_mtf_dataset(timeframes)
    except (FileNotFoundError, ValueError):
        return df

    if len(df) > 0 and len(mtf_data) > len(df):
        mtf_data = mtf_data.tail(len(df)).copy()

    return mtf_data


def _add_indicator_pack(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    for period in (21, 50, 200):
        column = f"EMA_{period}"
        if column not in result.columns:
            result = add_ema(result, period)

    if f"RSI_{RSI_PERIOD}" not in result.columns:
        result = add_rsi(result, RSI_PERIOD)

    if f"ATR_{ATR_PERIOD}" not in result.columns:
        result = add_atr(result, ATR_PERIOD)

    if f"ADX_{ADX_PERIOD}" not in result.columns:
        result = add_adx(result, ADX_PERIOD)

    result[f"WILLIAMS_R_{WILLIAMS_R_PERIOD}"] = _calculate_williams_r(result, WILLIAMS_R_PERIOD)
    result["EMA_50_SLOPE"] = result["EMA_50"].diff(3)
    result["VOLUME_RATIO"] = _safe_divide(
        result["Volume"],
        result["Volume"].rolling(VOLUME_LOOKBACK, min_periods=1).mean(),
    )

    return result


def _add_local_aliases(result: pd.DataFrame) -> pd.DataFrame:
    result = result.copy()
    result["v50_ema21"] = result["EMA_21"]
    result["v50_ema50"] = result["EMA_50"]
    result["v50_ema200"] = result["EMA_200"]
    result["v50_rsi"] = result[f"RSI_{RSI_PERIOD}"]
    result["v50_williams_r"] = result[f"WILLIAMS_R_{WILLIAMS_R_PERIOD}"]
    result["v50_plus_di"] = result[f"PLUS_DI_{ADX_PERIOD}"]
    result["v50_minus_di"] = result[f"MINUS_DI_{ADX_PERIOD}"]
    result["v50_adx"] = result[f"ADX_{ADX_PERIOD}"]
    result["v50_atr"] = result[f"ATR_{ATR_PERIOD}"]
    result["v50_volume_ratio"] = result["VOLUME_RATIO"]
    result["v50_candle_body"] = (result["Close"] - result["Open"]).abs()
    result["v50_candle_range"] = result["High"] - result["Low"]
    result["v50_body_to_range_ratio"] = _safe_divide(
        result["v50_candle_body"],
        result["v50_candle_range"],
    )
    result["v50_vwap"] = _calculate_daily_vwap(result)
    result["v50_above_value"] = result["Close"] >= result["v50_vwap"]
    result["v50_below_value"] = result["Close"] <= result["v50_vwap"]
    return result


def _build_timeframe_pack(
    data: pd.DataFrame,
    *,
    rule: str,
    target_minutes: int,
    base_minutes: float | None,
) -> tuple[pd.DataFrame, bool]:
    use_base_approximation = (
        not isinstance(data.index, pd.DatetimeIndex)
        or base_minutes is None
        or base_minutes > target_minutes
    )

    if use_base_approximation or base_minutes == target_minutes:
        source = data
    else:
        source = _resample_ohlcv(data, rule)

    pack = _add_indicator_pack(source)
    pack = pack[
        [
            "Close",
            "EMA_21",
            "EMA_50",
            "EMA_200",
            "EMA_50_SLOPE",
            f"RSI_{RSI_PERIOD}",
            f"WILLIAMS_R_{WILLIAMS_R_PERIOD}",
            f"PLUS_DI_{ADX_PERIOD}",
            f"MINUS_DI_{ADX_PERIOD}",
            f"ADX_{ADX_PERIOD}",
            f"ATR_{ATR_PERIOD}",
            "VOLUME_RATIO",
        ]
    ].rename(
        columns={
            "Close": "close",
            "EMA_21": "ema21",
            "EMA_50": "ema50",
            "EMA_200": "ema200",
            "EMA_50_SLOPE": "ema50_slope",
            f"RSI_{RSI_PERIOD}": "rsi",
            f"WILLIAMS_R_{WILLIAMS_R_PERIOD}": "williams_r",
            f"PLUS_DI_{ADX_PERIOD}": "plus_di",
            f"MINUS_DI_{ADX_PERIOD}": "minus_di",
            f"ADX_{ADX_PERIOD}": "adx",
            f"ATR_{ATR_PERIOD}": "atr",
            "VOLUME_RATIO": "volume_ratio",
        }
    )

    aligned = pack.reindex(data.index, method="ffill")
    return aligned, bool(use_base_approximation)


def _resample_ohlcv(data: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        data[["Open", "High", "Low", "Close", "Volume"]]
        .resample(rule, label="right", closed="right")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna(subset=["Open", "High", "Low", "Close"])
    )


def _add_session_features(result: pd.DataFrame) -> None:
    if not isinstance(result.index, pd.DatetimeIndex):
        result["v50_session"] = "Unknown"
        result["v50_in_session"] = False
        result["v50_flat_now"] = False
        result["v50_time_guard"] = False
        return

    sessions = []
    in_session = []
    flat_now = []
    time_guard = []

    for timestamp in result.index:
        hour = int(timestamp.hour)
        minute = int(timestamp.minute)
        session = _classify_v50_session(hour)
        is_flat = hour == 22 and minute >= 45
        is_closed = hour == 23

        sessions.append(session)
        flat_now.append(is_flat)
        in_session.append(not is_closed and not is_flat and session != "OFF")
        time_guard.append(
            (hour == 2)
            or (10 <= hour < 14)
            or (15 <= hour < 16)
        )

    result["v50_session"] = sessions
    result["v50_in_session"] = in_session
    result["v50_flat_now"] = flat_now
    result["v50_time_guard"] = time_guard


def _add_structure_features(result: pd.DataFrame) -> None:
    prior_high = result["High"].shift(1).rolling(STRUCTURE_LOOKBACK, min_periods=STRUCTURE_LOOKBACK).max()
    prior_low = result["Low"].shift(1).rolling(STRUCTURE_LOOKBACK, min_periods=STRUCTURE_LOOKBACK).min()
    atr = result["v50_atr"]
    body = result["v50_candle_body"]
    volume_ok = result["v50_volume_ratio"].fillna(0.0) >= 0.75
    break_ok = (body >= atr * 0.35) & volume_ok & (result["v50_adx"] >= MIN_ACTIVE_ADX)

    result["v50_prior_swing_high"] = prior_high
    result["v50_prior_swing_low"] = prior_low
    result["v50_bos_long"] = (
        result["Close"].gt(prior_high + atr * 0.12)
        & result["Close"].shift(1).le(prior_high)
        & break_ok
    )
    result["v50_bos_short"] = (
        result["Close"].lt(prior_low - atr * 0.12)
        & result["Close"].shift(1).ge(prior_low)
        & break_ok
    )
    result["v50_sweep_long"] = (
        result["Low"].lt(prior_low)
        & result["Close"].gt(prior_low)
        & result["Close"].gt(result["Open"])
    )
    result["v50_sweep_short"] = (
        result["High"].gt(prior_high)
        & result["Close"].lt(prior_high)
        & result["Close"].lt(result["Open"])
    )
    result["v50_pullback_long"] = (
        result["Close"].gt(result["v50_ema50"])
        & result["Low"].le(result["v50_ema21"])
        & result["Close"].gt(result["v50_ema21"])
        & result["Close"].gt(result["Open"])
    )
    result["v50_pullback_short"] = (
        result["Close"].lt(result["v50_ema50"])
        & result["High"].ge(result["v50_ema21"])
        & result["Close"].lt(result["v50_ema21"])
        & result["Close"].lt(result["Open"])
    )
    result["v50_recent_bull_shift"] = _rolling_bool(
        result["v50_bos_long"] | result["v50_sweep_long"],
        SHIFT_LOOKBACK,
    )
    result["v50_recent_bear_shift"] = _rolling_bool(
        result["v50_bos_short"] | result["v50_sweep_short"],
        SHIFT_LOOKBACK,
    )
    result["v50_momentum_cross_long"] = (
        result["v50_williams_r"].gt(-80)
        & result["v50_williams_r"].shift(1).le(-80)
    ) | (
        result["v50_rsi"].gt(50)
        & result["v50_rsi"].shift(1).le(50)
    )
    result["v50_momentum_cross_short"] = (
        result["v50_williams_r"].lt(-20)
        & result["v50_williams_r"].shift(1).ge(-20)
    ) | (
        result["v50_rsi"].lt(50)
        & result["v50_rsi"].shift(1).ge(50)
    )


def _add_mtf_conditions(result: pd.DataFrame) -> None:
    result["v50_trend4_long"] = (
        result["v50_4h_close"].gt(result["v50_4h_ema200"])
        & result["v50_4h_ema50"].gt(result["v50_4h_ema200"])
        & result["v50_4h_ema50_slope"].gt(0)
    )
    result["v50_trend4_short"] = (
        result["v50_4h_close"].lt(result["v50_4h_ema200"])
        & result["v50_4h_ema50"].lt(result["v50_4h_ema200"])
        & result["v50_4h_ema50_slope"].lt(0)
    )
    result["v50_soft4_long"] = result["v50_4h_close"].gt(result["v50_4h_ema50"]) & result["v50_4h_rsi"].gt(48)
    result["v50_soft4_short"] = result["v50_4h_close"].lt(result["v50_4h_ema50"]) & result["v50_4h_rsi"].lt(52)

    result["v50_mom1_long"] = (
        result["v50_1h_close"].gt(result["v50_1h_ema50"])
        & result["v50_1h_plus_di"].gt(result["v50_1h_minus_di"])
        & result["v50_1h_adx"].ge(MIN_ACTIVE_ADX)
        & result["v50_1h_rsi"].gt(52)
    )
    result["v50_mom1_short"] = (
        result["v50_1h_close"].lt(result["v50_1h_ema50"])
        & result["v50_1h_minus_di"].gt(result["v50_1h_plus_di"])
        & result["v50_1h_adx"].ge(MIN_ACTIVE_ADX)
        & result["v50_1h_rsi"].lt(48)
    )
    result["v50_strong1_long"] = result["v50_mom1_long"] & result["v50_1h_adx"].ge(20) & result["v50_1h_close"].gt(result["v50_1h_ema200"])
    result["v50_strong1_short"] = result["v50_mom1_short"] & result["v50_1h_adx"].ge(20) & result["v50_1h_close"].lt(result["v50_1h_ema200"])

    result["v50_struct15_long"] = (
        result["v50_15m_close"].gt(result["v50_15m_ema200"])
        & result["v50_15m_ema21"].gt(result["v50_15m_ema50"])
        & result["v50_15m_rsi"].gt(50)
    )
    result["v50_struct15_short"] = (
        result["v50_15m_close"].lt(result["v50_15m_ema200"])
        & result["v50_15m_ema21"].lt(result["v50_15m_ema50"])
        & result["v50_15m_rsi"].lt(50)
    )
    result["v50_trigger10_long"] = (
        result["v50_10m_close"].gt(result["v50_10m_ema21"])
        & result["v50_10m_ema21"].gt(result["v50_10m_ema50"])
        & result["v50_10m_plus_di"].gt(result["v50_10m_minus_di"])
        & result["v50_10m_williams_r"].gt(-65)
    )
    result["v50_trigger10_short"] = (
        result["v50_10m_close"].lt(result["v50_10m_ema21"])
        & result["v50_10m_ema21"].lt(result["v50_10m_ema50"])
        & result["v50_10m_minus_di"].gt(result["v50_10m_plus_di"])
        & result["v50_10m_williams_r"].lt(-35)
    )
    result["v50_trigger5_long"] = (
        result["v50_5m_close"].gt(result["v50_5m_ema21"])
        & result["v50_5m_plus_di"].gt(result["v50_5m_minus_di"])
        & result["v50_5m_williams_r"].gt(-60)
    )
    result["v50_trigger5_short"] = (
        result["v50_5m_close"].lt(result["v50_5m_ema21"])
        & result["v50_5m_minus_di"].gt(result["v50_5m_plus_di"])
        & result["v50_5m_williams_r"].lt(-40)
    )


def _add_quality_features(result: pd.DataFrame) -> None:
    impulse_low = result["Low"].rolling(LATE_IMPULSE_LOOKBACK, min_periods=1).min()
    impulse_high = result["High"].rolling(LATE_IMPULSE_LOOKBACK, min_periods=1).max()
    impulse_range = impulse_high - impulse_low

    result["v50_long_chase_block"] = (
        result["Close"].gt(result["v50_ema50"] + result["v50_atr"] * MAX_EXTENSION_ATR)
        & ~result["v50_pullback_long"]
        & ~result["v50_sweep_long"]
        & ~result["v50_bos_long"]
    )
    result["v50_short_chase_block"] = (
        result["Close"].lt(result["v50_ema50"] - result["v50_atr"] * MAX_EXTENSION_ATR)
        & ~result["v50_pullback_short"]
        & ~result["v50_sweep_short"]
        & ~result["v50_bos_short"]
    )
    result["v50_rsi_exhaust_long"] = (
        result["v50_rsi"].gt(70)
        & result["Close"].gt(result["v50_ema21"] + result["v50_atr"] * 0.80)
        & ~result["v50_pullback_long"]
    )
    result["v50_rsi_exhaust_short"] = (
        result["v50_rsi"].lt(30)
        & result["Close"].lt(result["v50_ema21"] - result["v50_atr"] * 0.80)
        & ~result["v50_pullback_short"]
    )
    result["v50_late_long_impulse"] = (
        result["Close"].sub(impulse_low).ge(result["v50_atr"] * LATE_IMPULSE_ATR_MIN)
        & result["Close"].gt(result["v50_ema50"] + result["v50_atr"] * LATE_IMPULSE_EXTENSION_ATR)
        & ((result["v50_rsi"].ge(LATE_IMPULSE_RSI)) | (result["v50_williams_r"].gt(-18)))
        & ~result["v50_pullback_long"]
    )
    result["v50_late_short_impulse"] = (
        impulse_high.sub(result["Close"]).ge(result["v50_atr"] * LATE_IMPULSE_ATR_MIN)
        & result["Close"].lt(result["v50_ema50"] - result["v50_atr"] * LATE_IMPULSE_EXTENSION_ATR)
        & ((result["v50_rsi"].le(100.0 - LATE_IMPULSE_RSI)) | (result["v50_williams_r"].lt(-82)))
        & ~result["v50_pullback_short"]
    )
    result["v50_chop_block"] = (
        impulse_range.le(result["v50_atr"] * 1.1)
        & result["v50_adx"].lt(MIN_ACTIVE_ADX + 2)
    )
    result["v50_volume_ok"] = result["v50_volume_ratio"].fillna(0.0).ge(0.75)
    result["v50_quality_long_ok"] = (
        result["v50_in_session"]
        & result["v50_adx"].ge(MIN_ACTIVE_ADX)
        & result["v50_above_value"]
        & result["v50_volume_ok"]
        & ~result["v50_long_chase_block"]
        & ~result["v50_rsi_exhaust_long"]
        & ~result["v50_late_long_impulse"]
        & ~result["v50_chop_block"]
    )
    result["v50_quality_short_ok"] = (
        result["v50_in_session"]
        & result["v50_adx"].ge(MIN_ACTIVE_ADX)
        & result["v50_below_value"]
        & result["v50_volume_ok"]
        & ~result["v50_short_chase_block"]
        & ~result["v50_rsi_exhaust_short"]
        & ~result["v50_late_short_impulse"]
        & ~result["v50_chop_block"]
    )
    result["v50_setup_long"] = (
        (result["v50_trigger10_long"] | result["v50_trigger5_long"] | result["v50_pullback_long"] | result["v50_sweep_long"] | result["v50_bos_long"])
        & (result["v50_soft4_long"] | result["v50_mom1_long"] | result["v50_struct15_long"])
    )
    result["v50_setup_short"] = (
        (result["v50_trigger10_short"] | result["v50_trigger5_short"] | result["v50_pullback_short"] | result["v50_sweep_short"] | result["v50_bos_short"])
        & (result["v50_soft4_short"] | result["v50_mom1_short"] | result["v50_struct15_short"])
    )


def _add_scores(result: pd.DataFrame) -> None:
    score_long = pd.Series(0.0, index=result.index)
    score_short = pd.Series(0.0, index=result.index)

    score_long += np.where(result["v50_trend4_long"], 22.0, np.where(result["v50_soft4_long"], 11.0, 0.0))
    score_short += np.where(result["v50_trend4_short"], 22.0, np.where(result["v50_soft4_short"], 11.0, 0.0))
    score_long += np.where(result["v50_strong1_long"], 20.0, np.where(result["v50_mom1_long"], 14.0, 0.0))
    score_short += np.where(result["v50_strong1_short"], 20.0, np.where(result["v50_mom1_short"], 14.0, 0.0))
    score_long += np.where(result["v50_struct15_long"], 18.0, np.where(result["v50_15m_close"].gt(result["v50_15m_ema50"]), 9.0, 0.0))
    score_short += np.where(result["v50_struct15_short"], 18.0, np.where(result["v50_15m_close"].lt(result["v50_15m_ema50"]), 9.0, 0.0))
    score_long += np.where(result["v50_trigger10_long"], 12.0, 0.0)
    score_short += np.where(result["v50_trigger10_short"], 12.0, 0.0)
    score_long += np.where(result["v50_trigger5_long"], 10.0, 0.0)
    score_short += np.where(result["v50_trigger5_short"], 10.0, 0.0)
    score_long += np.where(result["v50_sweep_long"], 7.0, np.where(result["v50_bos_long"], 4.0, 0.0))
    score_short += np.where(result["v50_sweep_short"], 7.0, np.where(result["v50_bos_short"], 4.0, 0.0))
    score_long += np.where(result["v50_above_value"], 6.0, 0.0)
    score_short += np.where(result["v50_below_value"], 6.0, 0.0)
    score_long += np.where(result["Close"].gt(result["v50_ema21"]) & result["Close"].gt(result["v50_ema50"]), 4.0, 0.0)
    score_short += np.where(result["Close"].lt(result["v50_ema21"]) & result["Close"].lt(result["v50_ema50"]), 4.0, 0.0)
    score_long += np.where(result["v50_in_session"], 5.0, 0.0)
    score_short += np.where(result["v50_in_session"], 5.0, 0.0)
    score_long += np.where(result["v50_volume_ok"], 3.0, 0.0)
    score_short += np.where(result["v50_volume_ok"], 3.0, 0.0)
    score_long -= np.where(result["v50_long_chase_block"], 10.0, 0.0)
    score_short -= np.where(result["v50_short_chase_block"], 10.0, 0.0)
    score_long -= np.where(result["v50_late_long_impulse"], 16.0, 0.0)
    score_short -= np.where(result["v50_late_short_impulse"], 16.0, 0.0)
    score_long -= np.where(result["v50_chop_block"], 8.0, 0.0)
    score_short -= np.where(result["v50_chop_block"], 8.0, 0.0)
    score_long -= np.where(result["v50_time_guard"], 4.0, 0.0)
    score_short -= np.where(result["v50_time_guard"], 4.0, 0.0)

    result["v50_score_long"] = score_long.clip(lower=0.0, upper=100.0)
    result["v50_score_short"] = score_short.clip(lower=0.0, upper=100.0)
    result["v50_signal_long"] = (
        result["v50_setup_long"]
        & result["v50_quality_long_ok"]
        & result["v50_score_long"].ge(SCORE_THRESHOLD)
        & result["v50_score_long"].ge(result["v50_score_short"] + SCORE_GAP)
    )
    result["v50_signal_short"] = (
        result["v50_setup_short"]
        & result["v50_quality_short_ok"]
        & result["v50_score_short"].ge(SCORE_THRESHOLD)
        & result["v50_score_short"].ge(result["v50_score_long"] + SCORE_GAP)
    )


def _select_signal_side(row: pd.Series) -> str:
    if bool(row.get("v50_signal_long", False)):
        return "BUY"

    if bool(row.get("v50_signal_short", False)):
        return "SELL"

    return "NO_TRADE"


def _build_no_trade_reason(row: pd.Series) -> str:
    return (
        "V50 Pine technical approximation no setup"
        f" | scoreLong={_format_float(row.get('v50_score_long'))}"
        f" | scoreShort={_format_float(row.get('v50_score_short'))}"
        f" | session={row.get('v50_session', 'Unknown')}"
        f" | qualityLong={bool(row.get('v50_quality_long_ok', False))}"
        f" | qualityShort={bool(row.get('v50_quality_short_ok', False))}"
        f" | mode={row.get('v50_approximation_mode', 'unknown')}"
    )


def _calculate_mtf_state(row: pd.Series) -> dict[str, float | bool]:
    trend4_long = _gt(row, "close_4h", "ema200_4h") and _gt(row, "ema50_4h", "ema200_4h") and _positive(row, "ema50_slope_4h")
    trend4_short = _lt(row, "close_4h", "ema200_4h") and _lt(row, "ema50_4h", "ema200_4h") and _negative(row, "ema50_slope_4h")
    soft4_long = _gt(row, "close_4h", "ema50_4h") and _value(row, "rsi_4h") > 48
    soft4_short = _lt(row, "close_4h", "ema50_4h") and _value(row, "rsi_4h") < 52

    mom1_long = (
        _gt(row, "close_1h", "ema50_1h")
        and _gt(row, "plus_di_1h", "minus_di_1h")
        and _value(row, "adx_1h") >= MIN_ACTIVE_ADX
        and _value(row, "rsi_1h") > 52
    )
    mom1_short = (
        _lt(row, "close_1h", "ema50_1h")
        and _gt(row, "minus_di_1h", "plus_di_1h")
        and _value(row, "adx_1h") >= MIN_ACTIVE_ADX
        and _value(row, "rsi_1h") < 48
    )
    strong1_long = mom1_long and _value(row, "adx_1h") >= 20 and _gt(row, "close_1h", "ema200_1h")
    strong1_short = mom1_short and _value(row, "adx_1h") >= 20 and _lt(row, "close_1h", "ema200_1h")

    struct15_long = _gt(row, "close_15", "ema200_15") and _gt(row, "ema21_15", "ema50_15") and _value(row, "rsi_15") > 50
    struct15_short = _lt(row, "close_15", "ema200_15") and _lt(row, "ema21_15", "ema50_15") and _value(row, "rsi_15") < 50
    trigger10_long = _gt(row, "close_10", "ema21_10") and _gt(row, "ema21_10", "ema50_10") and _gt(row, "plus_di_10", "minus_di_10") and _value(row, "williams_r_10") > -65
    trigger10_short = _lt(row, "close_10", "ema21_10") and _lt(row, "ema21_10", "ema50_10") and _gt(row, "minus_di_10", "plus_di_10") and _value(row, "williams_r_10") < -35
    trigger5_long = _gt(row, "close", "ema21") and _gt(row, "plus_di", "minus_di") and _value(row, "williams_r") > -60
    trigger5_short = _lt(row, "close", "ema21") and _gt(row, "minus_di", "plus_di") and _value(row, "williams_r") < -40

    pullback_long = _gt(row, "close", "ema50") and _value(row, "low") <= _value(row, "ema21") and _gt(row, "close", "ema21") and _gt(row, "close", "open")
    pullback_short = _lt(row, "close", "ema50") and _value(row, "high") >= _value(row, "ema21") and _lt(row, "close", "ema21") and _lt(row, "close", "open")
    long_chase_block = _value(row, "close") > _value(row, "ema50") + _value(row, "atr") * MAX_EXTENSION_ATR and not pullback_long
    short_chase_block = _value(row, "close") < _value(row, "ema50") - _value(row, "atr") * MAX_EXTENSION_ATR and not pullback_short

    session = str(row.get("session", "Unknown"))
    in_session = session not in {"OFF", "FX CLOSED", "Unknown"}
    trade_allowed = in_session and not _is_flat_time(row.name)
    volume_ok = True

    score_long = 0.0
    score_short = 0.0
    score_long += 22.0 if trend4_long else 11.0 if soft4_long else 0.0
    score_short += 22.0 if trend4_short else 11.0 if soft4_short else 0.0
    score_long += 20.0 if strong1_long else 14.0 if mom1_long else 0.0
    score_short += 20.0 if strong1_short else 14.0 if mom1_short else 0.0
    score_long += 18.0 if struct15_long else 9.0 if _gt(row, "close_15", "ema50_15") else 0.0
    score_short += 18.0 if struct15_short else 9.0 if _lt(row, "close_15", "ema50_15") else 0.0
    score_long += 12.0 if trigger10_long else 0.0
    score_short += 12.0 if trigger10_short else 0.0
    score_long += 10.0 if trigger5_long else 0.0
    score_short += 10.0 if trigger5_short else 0.0
    score_long += 4.0 if _gt(row, "close", "ema21") and _gt(row, "close", "ema50") else 0.0
    score_short += 4.0 if _lt(row, "close", "ema21") and _lt(row, "close", "ema50") else 0.0
    score_long += 5.0 if in_session else 0.0
    score_short += 5.0 if in_session else 0.0
    score_long += 3.0 if volume_ok else 0.0
    score_short += 3.0 if volume_ok else 0.0
    score_long -= 10.0 if long_chase_block else 0.0
    score_short -= 10.0 if short_chase_block else 0.0
    score_long = max(0.0, min(100.0, score_long))
    score_short = max(0.0, min(100.0, score_short))

    long_mtf_count = sum([soft4_long, mom1_long, struct15_long, trigger10_long, trigger5_long])
    short_mtf_count = sum([soft4_short, mom1_short, struct15_short, trigger10_short, trigger5_short])

    return {
        "score_long": score_long,
        "score_short": score_short,
        "trade_allowed": trade_allowed,
        "quality_long_ok": trade_allowed and _value(row, "adx") >= MIN_ACTIVE_ADX and not long_chase_block,
        "quality_short_ok": trade_allowed and _value(row, "adx") >= MIN_ACTIVE_ADX and not short_chase_block,
        "trigger10_long": trigger10_long,
        "trigger10_short": trigger10_short,
        "trigger5_long": trigger5_long,
        "trigger5_short": trigger5_short,
        "long_mtf_count": long_mtf_count,
        "short_mtf_count": short_mtf_count,
    }


def _select_mtf_side(state: dict[str, float | bool]) -> str:
    long_ok = (
        bool(state["quality_long_ok"])
        and int(state["long_mtf_count"]) >= 3
        and float(state["score_long"]) >= SCORE_THRESHOLD
        and float(state["score_long"]) >= float(state["score_short"]) + SCORE_GAP
        and (bool(state["trigger10_long"]) or bool(state["trigger5_long"]))
    )
    short_ok = (
        bool(state["quality_short_ok"])
        and int(state["short_mtf_count"]) >= 3
        and float(state["score_short"]) >= SCORE_THRESHOLD
        and float(state["score_short"]) >= float(state["score_long"]) + SCORE_GAP
        and (bool(state["trigger10_short"]) or bool(state["trigger5_short"]))
    )

    if long_ok and not short_ok:
        return "BUY"
    if short_ok and not long_ok:
        return "SELL"
    return "NO_TRADE"


def _build_mtf_no_trade_reason(row: pd.Series, state: dict[str, float | bool]) -> str:
    return (
        "V50 Pine MTF no setup"
        f" | scoreLong={float(state['score_long']):.1f}"
        f" | scoreShort={float(state['score_short']):.1f}"
        f" | session={row.get('session', 'Unknown')}"
        f" | tradeAllowed={bool(state['trade_allowed'])}"
        f" | longMtf={int(state['long_mtf_count'])}"
        f" | shortMtf={int(state['short_mtf_count'])}"
    )


def _no_trade(
    timestamp: datetime,
    config: StrategyConfig,
    reason: str,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    risk_reward: float | None = None,
) -> TradingSignal:
    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe=config.timeframe,
        side="NO_TRADE",
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=0.0,
        reason=reason,
    )


def _calculate_williams_r(data: pd.DataFrame, period: int) -> pd.Series:
    highest_high = data["High"].rolling(period, min_periods=period).max()
    lowest_low = data["Low"].rolling(period, min_periods=period).min()
    return -100.0 * _safe_divide(highest_high - data["Close"], highest_high - lowest_low)


def _calculate_daily_vwap(data: pd.DataFrame) -> pd.Series:
    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3.0
    volume = data["Volume"].replace(0, np.nan)

    if isinstance(data.index, pd.DatetimeIndex):
        dates = data.index.date
        numerator = (typical_price * volume).groupby(dates).cumsum()
        denominator = volume.groupby(dates).cumsum()
    else:
        numerator = (typical_price * volume).cumsum()
        denominator = volume.cumsum()

    return _safe_divide(numerator, denominator)


def _infer_timeframe_minutes(index: pd.Index) -> float | None:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return None

    deltas = index.to_series().diff().dropna()
    if deltas.empty:
        return None

    return float(deltas.median().total_seconds() / 60.0)


def _rolling_bool(series: pd.Series, window: int) -> pd.Series:
    return series.astype(float).rolling(window, min_periods=1).max().fillna(0.0).astype(bool)


def _safe_divide(numerator, denominator) -> pd.Series:
    numerator_series = pd.Series(numerator)
    denominator_series = pd.Series(denominator).replace(0, np.nan)
    result = numerator_series / denominator_series
    return result.replace([np.inf, -np.inf], np.nan)


def _classify_v50_session(hour: int) -> str:
    if hour == 23:
        return "FX CLOSED"
    if 9 <= hour < 10:
        return "ASIA/LONDON"
    if 16 <= hour < 18:
        return "LONDON/US"
    if 0 <= hour < 10:
        return "ASIA"
    if 10 <= hour < 16:
        return "LONDON"
    if 18 <= hour < 23:
        return "NEW YORK"
    return "OFF"


def _get_timestamp(df: pd.DataFrame) -> datetime:
    latest_index = df.index[-1]

    if isinstance(latest_index, pd.Timestamp):
        return latest_index.to_pydatetime()

    return datetime.now(UTC)


def _format_float(value) -> str:
    if value is None or pd.isna(value):
        return "nan"

    return f"{float(value):.1f}"


def _value(row: pd.Series, column: str) -> float:
    value = row.get(column, np.nan)
    if pd.isna(value):
        return np.nan
    return float(value)


def _gt(row: pd.Series, left: str, right: str) -> bool:
    left_value = _value(row, left)
    right_value = _value(row, right)
    return bool(pd.notna(left_value) and pd.notna(right_value) and left_value > right_value)


def _lt(row: pd.Series, left: str, right: str) -> bool:
    left_value = _value(row, left)
    right_value = _value(row, right)
    return bool(pd.notna(left_value) and pd.notna(right_value) and left_value < right_value)


def _positive(row: pd.Series, column: str) -> bool:
    value = _value(row, column)
    return bool(pd.notna(value) and value > 0)


def _negative(row: pd.Series, column: str) -> bool:
    value = _value(row, column)
    return bool(pd.notna(value) and value < 0)


def _is_flat_time(timestamp) -> bool:
    if not isinstance(timestamp, pd.Timestamp):
        return False
    return int(timestamp.hour) == 22 and int(timestamp.minute) >= 45


def _validate_ohlcv(data: pd.DataFrame) -> None:
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")


generate_signal.required_history_candles = REQUIRED_HISTORY_CANDLES
generate_signal.prepare_backtest_data = build_v50_features
generate_mtf_signal.required_history_candles = REQUIRED_HISTORY_CANDLES
generate_mtf_signal.prepare_backtest_data = prepare_mtf_backtest_data
