"""Tests for WebSocket data feed."""
import pandas as pd
import pytest

from src.data_feed.websocket_client import WebSocketDataFeed, PriceTick, LivePaperTradingEngine


def test_price_tick_creation():
    tick = PriceTick(
        symbol="XAUUSD",
        bid=2350.50,
        ask=2350.70,
        mid=2350.60,
        timestamp=pd.Timestamp.now(),
        volume=1000,
    )
    assert tick.symbol == "XAUUSD"
    assert tick.mid == 2350.60


def test_websocket_feed_init():
    feed = WebSocketDataFeed(symbols=["XAUUSD", "EURUSD"])
    assert feed.symbols == ["XAUUSD", "EURUSD"]
    assert feed.provider == "yahoo_fallback"
    assert feed.poll_interval == 5.0


def test_websocket_to_yahoo_symbol():
    assert WebSocketDataFeed._to_yahoo_symbol("XAUUSD") == "GC=F"
    assert WebSocketDataFeed._to_yahoo_symbol("EURUSD") == "EURUSD=X"
    assert WebSocketDataFeed._to_yahoo_symbol("BTCUSD") == "BTC-USD"
    assert WebSocketDataFeed._to_yahoo_symbol("SPX500") == "^GSPC"


def test_live_paper_engine_init():
    feed = WebSocketDataFeed(symbols=["XAUUSD"])
    engine = LivePaperTradingEngine(feed)
    assert engine.data_feed == feed
    assert engine.get_open_trades() == []


def test_live_paper_trade_lifecycle():
    feed = WebSocketDataFeed(symbols=["XAUUSD"])
    engine = LivePaperTradingEngine(feed)

    trade = {
        "id": "test_1",
        "symbol": "XAUUSD",
        "side": "BUY",
        "entry": 2350.0,
        "stop_loss": 2340.0,
        "take_profit": 2370.0,
        "units": 1.0,
    }
    engine.place_trade(trade)
    assert len(engine.get_open_trades()) == 1

    # Simulate price hitting TP
    tick = PriceTick(
        symbol="XAUUSD",
        bid=2375.0,
        ask=2375.2,
        mid=2375.1,
        timestamp=pd.Timestamp.now(),
    )
    engine._on_price_update(tick)

    # Trade should be closed
    assert len(engine.get_open_trades()) == 0
    history = engine.get_trade_history()
    assert len(history) == 1
    assert history[0]["exit_reason"] == "TP_HIT"
