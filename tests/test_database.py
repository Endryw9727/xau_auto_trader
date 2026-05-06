from datetime import UTC, datetime
from pathlib import Path

from src.database.db import (
    count_records,
    get_all_signals,
    get_all_trades,
    init_database,
    save_signal,
    save_trade,
)
from src.database.models import Signal, Trade


def test_init_database_creates_file(tmp_path):
    db_path = tmp_path / "trading_test.db"

    init_database(db_path)

    assert db_path.exists()


def test_save_and_read_signal(tmp_path):
    db_path = tmp_path / "trading_test.db"
    init_database(db_path)

    signal = Signal(
        symbol="XAUUSD",
        timeframe="15m",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        confidence=75.0,
        risk_reward=2.0,
        reason="Test signal",
        approved_by_risk_manager=True,
    )

    saved = save_signal(signal, db_path)
    signals = get_all_signals(db_path)

    assert saved.id is not None
    assert len(signals) == 1
    assert signals[0].symbol == "XAUUSD"
    assert signals[0].side == "BUY"


def test_save_and_read_trade(tmp_path):
    db_path = tmp_path / "trading_test.db"
    init_database(db_path)

    trade = Trade(
        timestamp_open=datetime.now(UTC),
        timestamp_close=None,
        symbol="XAUUSD",
        side="BUY",
        timeframe="15m",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        exit_price=None,
        position_size=0.02,
        risk_percent=0.005,
        risk_amount=5.0,
        result="OPEN",
        profit_loss=None,
        risk_reward=2.0,
        strategy_name="test_strategy",
        mode="backtest",
        reason_entry="Test entry",
        reason_exit=None,
    )

    saved = save_trade(trade, db_path)
    trades = get_all_trades(db_path)

    assert saved.id is not None
    assert len(trades) == 1
    assert trades[0].symbol == "XAUUSD"
    assert trades[0].side == "BUY"
    assert trades[0].result == "OPEN"
