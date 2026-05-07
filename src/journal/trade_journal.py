"""
Trade journal utilities.

This module saves backtest and paper trading results into SQLite.

It converts trade DataFrames into database Trade records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.database.db import init_database, save_trade
from src.database.models import Trade


def save_trades_dataframe_to_db(
    trades: pd.DataFrame,
    db_path: str | Path = "data/database/trading.db",
    mode: str = "backtest",
    default_symbol: str = "XAUUSD",
    default_timeframe: str = "15m",
    default_strategy_name: str = "default",
    default_risk_percent: float = 0.0,
    default_risk_amount: float = 0.0,
) -> int:
    """
    Save a trades DataFrame to the SQLite database.

    Returns the number of inserted trades.
    """
    init_database(db_path)

    if trades.empty:
        return 0

    inserted = 0

    for _, row in trades.iterrows():
        trade = Trade(
            timestamp_open=_parse_datetime(row.get("timestamp_open")),
            timestamp_close=_parse_optional_datetime(row.get("timestamp_close")),
            symbol=str(row.get("symbol", default_symbol)),
            side=str(row.get("side")),
            timeframe=str(row.get("timeframe", default_timeframe)),
            entry_price=float(row.get("entry_price")),
            stop_loss=float(row.get("stop_loss")),
            take_profit=float(row.get("take_profit")),
            exit_price=_parse_optional_float(row.get("exit_price")),
            position_size=float(row.get("position_size")),
            risk_percent=_parse_float_or_default(row.get("risk_percent"), default_risk_percent),
            risk_amount=_parse_float_or_default(row.get("risk_amount"), default_risk_amount),
            result=str(row.get("result")) if row.get("result") is not None else None,
            profit_loss=_parse_optional_float(row.get("profit_loss")),
            risk_reward=_parse_optional_float(row.get("risk_reward")),
            strategy_name=str(row.get("strategy_name", default_strategy_name)),
            mode=mode,
            reason_entry=_parse_optional_string(row.get("reason_entry")),
            reason_exit=_parse_optional_string(row.get("reason_exit")),
        )

        save_trade(trade, db_path)
        inserted += 1

    return inserted


def _parse_datetime(value) -> datetime:
    """Parse timestamp-like value into datetime."""
    if isinstance(value, datetime):
        return value

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if value is None or pd.isna(value):
        return datetime.now(UTC)

    return pd.to_datetime(value).to_pydatetime()


def _parse_optional_datetime(value) -> datetime | None:
    """Parse optional timestamp-like value."""
    if value is None or pd.isna(value):
        return None

    return _parse_datetime(value)


def _parse_optional_float(value) -> float | None:
    """Parse optional float value."""
    if value is None or pd.isna(value):
        return None

    return float(value)


def _parse_float_or_default(value, default: float) -> float:
    """Parse float or return default."""
    if value is None or pd.isna(value):
        return float(default)

    return float(value)


def _parse_optional_string(value) -> str | None:
    """Parse optional string."""
    if value is None or pd.isna(value):
        return None

    return str(value)


def save_signal_to_db(
    signal,
    db_path: str | Path = "data/database/trading.db",
    approved_by_risk_manager: bool = False,
    blocked_reason: str | None = None,
) -> int:
    """
    Save a generated TradingSignal to SQLite.

    Returns the inserted signal ID.
    """
    from src.database.models import Signal
    from src.database.db import save_signal

    init_database(db_path)

    db_signal = Signal(
        timestamp=signal.timestamp,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        side=signal.side,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        confidence=signal.confidence,
        risk_reward=signal.risk_reward,
        reason=signal.reason,
        approved_by_risk_manager=approved_by_risk_manager,
        blocked_reason=blocked_reason,
    )

    saved = save_signal(db_signal, db_path)
    return int(saved.id)
