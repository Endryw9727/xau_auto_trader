"""
WebSocket client for real-time market data.

Supports multiple broker/data provider WebSocket APIs:
- OANDA Streaming API (placeholder)
- IG Streaming API (placeholder)
- Polygon.io WebSocket (placeholder)
- Yahoo Finance delayed (fallback)

Usage:
    from src.data_feed.websocket_client import WebSocketDataFeed
    feed = WebSocketDataFeed(provider="oanda", symbols=["XAUUSD"])
    feed.start()
    price = feed.get_latest_price("XAUUSD")
    feed.stop()
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable

import pandas as pd
import requests

@dataclass(frozen=True)
class PriceTick:
    """A single price tick from WebSocket."""

    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp: pd.Timestamp
    volume: int | None = None

class WebSocketDataFeed:
    """Real-time WebSocket data feed with fallback to REST polling."""

    def __init__(
        self,
        provider: str = "yahoo_fallback",
        symbols: list[str] | None = None,
        poll_interval: float = 5.0,
    ):
        self.provider = provider
        self.symbols = symbols or ["XAUUSD"]
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_prices: dict[str, PriceTick] = {}
        self._callbacks: list[Callable[[PriceTick], None]] = []
        self._lock = threading.Lock()

    def register_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Register a callback for price updates."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start(self) -> None:
        """Start the data feed."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the data feed."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def get_latest_price(self, symbol: str) -> PriceTick | None:
        """Get the latest price for a symbol."""
        with self._lock:
            return self._latest_prices.get(symbol.upper())

    def get_all_prices(self) -> dict[str, PriceTick]:
        """Get all latest prices."""
        with self._lock:
            return dict(self._latest_prices)

    def _run(self) -> None:
        """Main loop for price updates."""
        while self._running:
            try:
                if self.provider == "yahoo_fallback":
                    self._fetch_yahoo()
                elif self.provider == "oanda":
                    self._fetch_oanda()
                elif self.provider == "polygon":
                    self._fetch_polygon()
                else:
                    self._fetch_yahoo()
            except Exception as e:
                print(f"Data feed error: {e}")

            time.sleep(self.poll_interval)

    def _fetch_yahoo(self) -> None:
        """Fetch prices from Yahoo Finance (REST fallback)."""
        import yfinance as yf

        for symbol in self.symbols:
            try:
                # Map trading symbols to Yahoo symbols
                yahoo_symbol = self._to_yahoo_symbol(symbol)
                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info

                if "bid" in info and "ask" in info:
                    bid = info.get("bid", 0)
                    ask = info.get("ask", 0)
                    mid = (bid + ask) / 2 if bid and ask else info.get("regularMarketPrice", 0)
                else:
                    hist = ticker.history(period="1d", interval="1m")
                    if not hist.empty:
                        last = hist.iloc[-1]
                        mid = last["Close"]
                        bid = mid * 0.9999
                        ask = mid * 1.0001
                    else:
                        continue

                tick = PriceTick(
                    symbol=symbol,
                    bid=round(bid, 2),
                    ask=round(ask, 2),
                    mid=round(mid, 2),
                    timestamp=pd.Timestamp.now(),
                    volume=info.get("volume", None),
                )

                with self._lock:
                    self._latest_prices[symbol.upper()] = tick

                for cb in self._callbacks:
                    try:
                        cb(tick)
                    except Exception:
                        pass

            except Exception as e:
                print(f"Error fetching {symbol}: {e}")

    def _fetch_oanda(self) -> None:
        """Placeholder for OANDA streaming API."""
        # TODO: Implement OANDA REST/streaming API
        # Requires: OANDA_API_KEY, OANDA_ACCOUNT_ID
        pass

    def _fetch_polygon(self) -> None:
        """Placeholder for Polygon.io WebSocket."""
        # TODO: Implement Polygon.io WebSocket
        # Requires: POLYGON_API_KEY
        pass

    @staticmethod
    def _to_yahoo_symbol(symbol: str) -> str:
        """Convert trading symbol to Yahoo Finance symbol."""
        mapping = {
            "XAUUSD": "GC=F",  # Gold futures
            "EURUSD": "EURUSD=X",
            "GBPUSD": "GBPUSD=X",
            "USDJPY": "USDJPY=X",
            "BTCUSD": "BTC-USD",
            "SPX500": "^GSPC",
            "US30": "^DJI",
            "NAS100": "^IXIC",
        }
        return mapping.get(symbol.upper(), symbol)


class LivePaperTradingEngine:
    """Paper trading engine that uses real-time price data."""

    def __init__(
        self,
        data_feed: WebSocketDataFeed,
        check_interval: float = 1.0,
    ):
        self.data_feed = data_feed
        self.check_interval = check_interval
        self._open_trades: list[dict] = []
        self._trade_history: list[dict] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start live paper trading monitoring."""
        if self._running:
            return

        self._running = True
        self.data_feed.register_callback(self._on_price_update)
        self.data_feed.start()

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop live paper trading."""
        self._running = False
        self.data_feed.unregister_callback(self._on_price_update)
        self.data_feed.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def place_trade(self, trade: dict) -> None:
        """Place a paper trade to be monitored."""
        self._open_trades.append(trade)

    def get_open_trades(self) -> list[dict]:
        """Get currently open trades."""
        return list(self._open_trades)

    def get_trade_history(self) -> list[dict]:
        """Get closed trade history."""
        return list(self._trade_history)

    def _on_price_update(self, tick: PriceTick) -> None:
        """Handle price updates."""
        # Check SL/TP for open trades
        for trade in list(self._open_trades):
            if trade.get("symbol") != tick.symbol:
                continue

            side = trade.get("side")
            sl = trade.get("stop_loss")
            tp = trade.get("take_profit")

            if side == "BUY":
                if tick.bid <= sl:
                    self._close_trade(trade, tick.bid, "SL_HIT")
                elif tick.bid >= tp:
                    self._close_trade(trade, tick.bid, "TP_HIT")
            elif side == "SELL":
                if tick.ask >= sl:
                    self._close_trade(trade, tick.ask, "SL_HIT")
                elif tick.ask <= tp:
                    self._close_trade(trade, tick.ask, "TP_HIT")

    def _close_trade(self, trade: dict, exit_price: float, reason: str) -> None:
        """Close a trade."""
        entry = trade.get("entry", 0)
        side = trade.get("side")
        units = trade.get("units", 1)

        if side == "BUY":
            pnl = (exit_price - entry) * units
        else:
            pnl = (entry - exit_price) * units

        trade["exit_price"] = exit_price
        trade["exit_time"] = pd.Timestamp.now().isoformat()
        trade["exit_reason"] = reason
        trade["pnl"] = pnl

        self._open_trades.remove(trade)
        self._trade_history.append(trade)

        print(f"Paper trade closed: {trade.get('id')} | {reason} | P&L: {pnl:.2f}")

    def _monitor_loop(self) -> None:
        """Monitor loop for trade management."""
        while self._running:
            time.sleep(self.check_interval)
