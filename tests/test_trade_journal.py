from datetime import datetime

import pandas as pd

from src.database.db import get_all_trades, init_database
from src.journal.trade_journal import save_trades_dataframe_to_db


def test_save_trades_dataframe_to_db(tmp_path):
    db_path = tmp_path / "journal_test.db"
    init_database(db_path)

    trades = pd.DataFrame(
        [
            {
                "timestamp_open": datetime(2026, 1, 1, 9, 0),
                "timestamp_close": datetime(2026, 1, 1, 9, 15),
                "symbol": "XAUUSD",
                "side": "BUY",
                "timeframe": "15m",
                "entry_price": 2350.0,
                "stop_loss": 2345.0,
                "take_profit": 2360.0,
                "exit_price": 2360.0,
                "position_size": 1.0,
                "risk_percent": 0.005,
                "risk_amount": 5.0,
                "result": "WIN",
                "profit_loss": 10.0,
                "risk_reward": 2.0,
                "strategy_name": "test_strategy",
                "reason_entry": "Test entry",
                "reason_exit": "Take profit hit",
            }
        ]
    )

    inserted = save_trades_dataframe_to_db(trades, db_path=db_path, mode="backtest")
    saved_trades = get_all_trades(db_path)

    assert inserted == 1
    assert len(saved_trades) == 1
    assert saved_trades[0].symbol == "XAUUSD"
    assert saved_trades[0].side == "BUY"
    assert saved_trades[0].result == "WIN"
    assert saved_trades[0].profit_loss == 10.0


def test_save_empty_dataframe_returns_zero(tmp_path):
    db_path = tmp_path / "journal_test.db"

    inserted = save_trades_dataframe_to_db(pd.DataFrame(), db_path=db_path)

    assert inserted == 0


def test_save_signal_to_db(tmp_path):
    from datetime import datetime
    from src.database.db import get_all_signals
    from src.journal.trade_journal import save_signal_to_db
    from src.strategy.signals import TradingSignal

    db_path = tmp_path / "journal_signal_test.db"

    signal = TradingSignal(
        timestamp=datetime(2026, 1, 1, 9, 0),
        symbol="XAUUSD",
        timeframe="15m",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        risk_reward=2.0,
        confidence=80.0,
        reason="Test signal",
    )

    signal_id = save_signal_to_db(
        signal,
        db_path=db_path,
        approved_by_risk_manager=True,
        blocked_reason=None,
    )

    saved_signals = get_all_signals(db_path)

    assert signal_id is not None
    assert len(saved_signals) == 1
    assert saved_signals[0].symbol == "XAUUSD"
    assert saved_signals[0].side == "BUY"
    assert saved_signals[0].approved_by_risk_manager is True
