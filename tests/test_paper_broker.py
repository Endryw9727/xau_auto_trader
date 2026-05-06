from datetime import datetime

import pandas as pd
import pytest

from src.execution.paper_broker import PaperBroker


def make_candle(high: float, low: float, close: float) -> pd.Series:
    return pd.Series(
        {
            "High": high,
            "Low": low,
            "Close": close,
        }
    )


def test_open_buy_position():
    broker = PaperBroker(initial_balance=1000.0)

    position = broker.open_position(
        symbol="XAUUSD",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    assert position.id == 1
    assert position.side == "BUY"
    assert len(broker.open_positions) == 1


def test_buy_position_hits_take_profit():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2361.0, low=2351.0, close=2360.0)
    closed = broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))

    assert len(closed) == 1
    assert closed[0].result == "WIN"
    assert closed[0].profit_loss == 10.0
    assert broker.balance == 1010.0
    assert len(broker.open_positions) == 0


def test_buy_position_hits_stop_loss():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2352.0, low=2344.0, close=2345.0)
    closed = broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))

    assert len(closed) == 1
    assert closed[0].result == "LOSS"
    assert closed[0].profit_loss == -5.0
    assert broker.balance == 995.0


def test_sell_position_hits_take_profit():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="SELL",
        entry_price=2350.0,
        stop_loss=2355.0,
        take_profit=2340.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2349.0, low=2339.0, close=2340.0)
    closed = broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))

    assert len(closed) == 1
    assert closed[0].result == "WIN"
    assert closed[0].profit_loss == 10.0
    assert broker.balance == 1010.0


def test_sell_position_hits_stop_loss():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="SELL",
        entry_price=2350.0,
        stop_loss=2355.0,
        take_profit=2340.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2356.0, low=2348.0, close=2355.0)
    closed = broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))

    assert len(closed) == 1
    assert closed[0].result == "LOSS"
    assert closed[0].profit_loss == -5.0
    assert broker.balance == 995.0


def test_close_all_at_market():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2354.0, low=2350.0, close=2353.0)
    closed = broker.close_all_at_market(candle, datetime(2026, 1, 1, 9, 15))

    assert len(closed) == 1
    assert closed[0].profit_loss == 3.0
    assert broker.balance == 1003.0


def test_missing_candle_columns_raise_error():
    broker = PaperBroker(initial_balance=1000.0)
    candle = pd.Series({"Close": 2350.0})

    with pytest.raises(ValueError):
        broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))


def test_closed_trades_dataframe():
    broker = PaperBroker(initial_balance=1000.0)

    broker.open_position(
        symbol="XAUUSD",
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=1.0,
        opened_at=datetime(2026, 1, 1, 9, 0),
    )

    candle = make_candle(high=2361.0, low=2351.0, close=2360.0)
    broker.update_with_candle(candle, datetime(2026, 1, 1, 9, 15))

    df = broker.get_closed_trades_dataframe()

    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "XAUUSD"
