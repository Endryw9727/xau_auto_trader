"""
Reusable V50 signal filters for research strategies.

The filters wrap v50_pine_technical_strategy signal generation and can only
return analytical BUY / SELL / NO_TRADE signals for backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_pine


@dataclass(frozen=True)
class V50EdgeFilterVariant:
    """One V50 technical signal-filter variant."""

    variant_name: str
    allowed_sides: tuple[str, ...] | None = None
    allowed_sessions: tuple[str, ...] | None = None
    blocked_sessions: tuple[str, ...] = ()
    long_allowed_sessions: tuple[str, ...] | None = None
    short_allowed_sessions: tuple[str, ...] | None = None
    blocked_side_sessions: tuple[tuple[str, str], ...] = ()


def make_v50_edge_filter_signal_generator(variant: V50EdgeFilterVariant):
    """Create a signal generator that blocks V50 signals by variant rules."""
    def _signal_generator(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
        signal = strategy_v50_pine.generate_signal(df, config)
        if signal.side not in {"BUY", "SELL"}:
            return signal

        session = _normalize_session(_extract_reason_field(signal.reason, "session"))
        blocked_reason = _blocked_reason(signal.side, session, variant)
        if blocked_reason is None:
            return signal

        return TradingSignal(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            side="NO_TRADE",
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_reward=signal.risk_reward,
            confidence=0.0,
            reason=f"V50 edge filter blocked | variant={variant.variant_name} | {blocked_reason}",
        )

    _signal_generator.required_history_candles = strategy_v50_pine.REQUIRED_HISTORY_CANDLES
    _signal_generator.prepare_backtest_data = strategy_v50_pine.build_v50_features
    return _signal_generator


def _blocked_reason(
    side: str,
    session: str,
    variant: V50EdgeFilterVariant,
) -> str | None:
    if variant.allowed_sides is not None and side not in variant.allowed_sides:
        return f"side={side} not allowed"

    if variant.allowed_sessions is not None and session not in variant.allowed_sessions:
        return f"session={session} not allowed"

    if session in variant.blocked_sessions:
        return f"session={session} blocked"

    if variant.long_allowed_sessions is not None and side == "BUY" and session not in variant.long_allowed_sessions:
        return f"long session={session} not allowed"

    if variant.short_allowed_sessions is not None and side == "SELL" and session not in variant.short_allowed_sessions:
        return f"short session={session} not allowed"

    if (side, session) in variant.blocked_side_sessions:
        return f"side={side} session={session} blocked"

    return None


def _extract_reason_field(reason: str, field_name: str) -> str | None:
    pattern = re.compile(rf"(?:^|\|\s*){re.escape(field_name)}\s*=\s*([^|]+)", re.IGNORECASE)
    match = pattern.search(reason or "")
    if match is None:
        return None
    return match.group(1).strip() or None


def _normalize_session(session: str | None) -> str:
    if session is None:
        return "UNKNOWN"
    return session.strip().upper()
