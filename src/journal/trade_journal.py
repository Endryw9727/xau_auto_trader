"""
Trade journal utilities.

This module saves backtest and paper trading results into SQLite.

It converts trade DataFrames into database Trade records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from src.database.db import get_session_factory, init_database, save_signal, save_trade
from src.database.models import Signal, Trade


def save_trades_dataframe_to_db(
    trades: pd.DataFrame,
    db_path: str | Path = "data/database/trading.db",
    mode: str = "backtest",
    default_symbol: str = "XAUUSD",
    default_timeframe: str = "15m",
    default_strategy_name: str = "default",
    default_risk_percent: float = 0.0,
    default_risk_amount: float = 0.0,
    deduplicate: bool = True,
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

        if deduplicate and _find_existing_trade_id(trade, db_path) is not None:
            continue

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
    deduplicate: bool = True,
) -> int:
    """
    Save a generated TradingSignal to SQLite.

    Returns the inserted or existing signal ID.
    """
    init_database(db_path)

    if deduplicate:
        existing_signal_id = _find_existing_signal_id(
            signal=signal,
            db_path=db_path,
            approved_by_risk_manager=approved_by_risk_manager,
            blocked_reason=blocked_reason,
        )

        if existing_signal_id is not None:
            return existing_signal_id

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


def _find_existing_signal_id(
    signal,
    db_path: str | Path,
    approved_by_risk_manager: bool,
    blocked_reason: str | None,
) -> int | None:
    """Return an existing matching signal ID to avoid exact duplicate rows."""
    SessionLocal = get_session_factory(db_path)

    with SessionLocal() as session:
        statement = (
            select(Signal.id)
            .where(
                Signal.timestamp == signal.timestamp,
                Signal.symbol == signal.symbol,
                Signal.timeframe == signal.timeframe,
                Signal.side == signal.side,
                _optional_equal(Signal.entry_price, signal.entry_price),
                _optional_equal(Signal.stop_loss, signal.stop_loss),
                _optional_equal(Signal.take_profit, signal.take_profit),
                _optional_equal(Signal.confidence, signal.confidence),
                _optional_equal(Signal.risk_reward, signal.risk_reward),
                _optional_equal(Signal.reason, signal.reason),
                Signal.approved_by_risk_manager == approved_by_risk_manager,
                _optional_equal(Signal.blocked_reason, blocked_reason),
            )
            .limit(1)
        )

        existing_id = session.scalar(statement)

    return int(existing_id) if existing_id is not None else None


def _find_existing_trade_id(trade: Trade, db_path: str | Path) -> int | None:
    """Return an existing matching trade ID to avoid exact duplicate rows."""
    SessionLocal = get_session_factory(db_path)

    with SessionLocal() as session:
        statement = (
            select(Trade.id)
            .where(
                Trade.timestamp_open == trade.timestamp_open,
                _optional_equal(Trade.timestamp_close, trade.timestamp_close),
                Trade.symbol == trade.symbol,
                Trade.side == trade.side,
                Trade.timeframe == trade.timeframe,
                Trade.entry_price == trade.entry_price,
                Trade.stop_loss == trade.stop_loss,
                Trade.take_profit == trade.take_profit,
                _optional_equal(Trade.exit_price, trade.exit_price),
                Trade.position_size == trade.position_size,
                Trade.risk_percent == trade.risk_percent,
                Trade.risk_amount == trade.risk_amount,
                _optional_equal(Trade.result, trade.result),
                _optional_equal(Trade.profit_loss, trade.profit_loss),
                _optional_equal(Trade.risk_reward, trade.risk_reward),
                Trade.strategy_name == trade.strategy_name,
                Trade.mode == trade.mode,
                _optional_equal(Trade.reason_entry, trade.reason_entry),
                _optional_equal(Trade.reason_exit, trade.reason_exit),
            )
            .limit(1)
        )

        existing_id = session.scalar(statement)

    return int(existing_id) if existing_id is not None else None


def _optional_equal(column, value):
    """Build a SQLAlchemy equality condition that handles NULL values."""
    if value is None or pd.isna(value):
        return column.is_(None)

    return column == value
