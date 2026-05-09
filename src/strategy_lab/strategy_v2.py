"""
Strategy Lab v2: existing strategy with a session filter.

This strategy keeps the current signal logic but only allows setups during
London and New York sessions. It is a research wrapper, not execution code.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from src.analysis.session_analysis import classify_hour_to_session
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal, generate_signal as generate_existing_signal


STRATEGY_NAME = "session_filtered_strategy"
ALLOWED_SESSIONS = ("London", "New York")


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate a signal only when the latest candle is in an allowed session."""
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    timestamp = _get_timestamp(df)
    session_name = classify_hour_to_session(timestamp.hour)

    if session_name not in ALLOWED_SESSIONS:
        return TradingSignal(
            timestamp=timestamp,
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="NO_TRADE",
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            risk_reward=None,
            confidence=0.0,
            reason=f"Session filtered out: {session_name}",
        )

    signal = generate_existing_signal(df, config)

    return TradingSignal(
        timestamp=signal.timestamp,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        side=signal.side,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        risk_reward=signal.risk_reward,
        confidence=signal.confidence,
        reason=f"{signal.reason} | Session={session_name}",
    )


def _get_timestamp(df: pd.DataFrame) -> datetime:
    """Return the latest index timestamp if available."""
    latest_index = df.index[-1]

    if isinstance(latest_index, pd.Timestamp):
        return latest_index.to_pydatetime()

    return datetime.now(UTC)
