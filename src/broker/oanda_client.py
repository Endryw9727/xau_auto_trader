"""
OANDA REST API client.

Supports:
- Account info
- Price streaming
- Order placement (market, limit, stop, OCO)
- Position management
- Trailing stop modification

Requires OANDA_API_KEY and OANDA_ACCOUNT_ID in .env
Paper trading uses OANDA practice environment by default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from src.broker.broker_interface import BaseBrokerInterface, BrokerAccount, BrokerOrder, BrokerPosition
from src.broker.safety_gate import SafetyGate

OANDA_PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"
OANDA_LIVE_URL = "https://api-fxtrade.oanda.com/v3"


class OandaClient(BaseBrokerInterface):
    """OANDA REST API client with safety gate."""

    def __init__(self, paper_mode: bool = True):
        super().__init__("OANDA", paper_mode=paper_mode)
        self.api_key = os.getenv("OANDA_API_KEY", "")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        self.base_url = OANDA_PRACTICE_URL if paper_mode else OANDA_LIVE_URL
        self.safety_gate = SafetyGate()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def connect(self) -> dict[str, Any]:
        """Test connection by fetching account info."""
        if not self.api_key or not self.account_id:
            return {"success": False, "error": "OANDA_API_KEY or OANDA_ACCOUNT_ID not set"}

        try:
            url = f"{self.base_url}/accounts/{self.account_id}/summary"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            self.connected = True
            return {"success": True, "account": response.json().get("account", {})}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict[str, Any]:
        self.connected = False
        return {"success": True}

    def get_account(self) -> BrokerAccount:
        """Fetch account summary from OANDA."""
        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()["account"]

        return BrokerAccount(
            account_id=self.account_id,
            balance=float(data.get("balance", 0)),
            equity=float(data.get("NAV", data.get("balance", 0))),
            margin_used=float(data.get("marginUsed", 0)),
            margin_available=float(data.get("marginAvailable", 0)),
            open_positions=int(data.get("openPositionCount", 0)),
            currency=data.get("currency", "USD"),
        )

    def get_price(self, symbol: str) -> dict[str, float]:
        """Get current price for an instrument."""
        oanda_symbol = self._to_oanda_symbol(symbol)
        url = f"{self.base_url}/accounts/{self.account_id}/pricing?instruments={oanda_symbol}"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        price = response.json()["prices"][0]

        return {
            "bid": float(price["bid"]),
            "ask": float(price["ask"]),
            "mid": (float(price["bid"]) + float(price["ask"])) / 2,
            "spread": float(price["ask"]) - float(price["bid"]),
        }

    def place_order(self, order: BrokerOrder) -> dict[str, Any]:
        """Place an order through OANDA API with safety gate."""
        # Safety check for real trading
        if not self.paper_mode:
            safety = self.safety_gate.check_can_trade(order.symbol, order.units)
            self.safety_gate.record_trade_attempt(
                order.symbol, order.side, order.units, 0.0,
                safety["allowed"], safety["reason"],
            )
            if not safety["allowed"]:
                return {"success": False, "error": safety["reason"], "safety_blocked": True}

        oanda_symbol = self._to_oanda_symbol(order.symbol)

        payload: dict[str, Any] = {
            "order": {
                "type": order.order_type,
                "instrument": oanda_symbol,
                "units": str(order.units) if order.side == "BUY" else str(-order.units),
            }
        }

        if order.stop_loss:
            payload["order"]["stopLossOnFill"] = {"price": str(order.stop_loss)}
        if order.take_profit:
            payload["order"]["takeProfitOnFill"] = {"price": str(order.take_profit)}
        if order.trailing_stop_distance:
            payload["order"]["trailingStopLossOnFill"] = {
                "distance": str(order.trailing_stop_distance),
                "step": str(order.trailing_stop_step or 1.0),
            }

        if order.order_type == "LIMIT" and order.entry_price:
            payload["order"]["price"] = str(order.entry_price)
        elif order.order_type == "STOP" and order.entry_price:
            payload["order"]["price"] = str(order.entry_price)

        url = f"{self.base_url}/accounts/{self.account_id}/orders"

        try:
            response = self._session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if not self.paper_mode:
                self.safety_gate.register_executed_trade(0.0)

            return {
                "success": True,
                "order_id": result.get("orderCreateTransaction", {}).get("id"),
                "broker": "OANDA",
                "paper_mode": self.paper_mode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_position(self, position_id: str) -> dict[str, Any]:
        """Close a position by instrument (OANDA uses instrument, not position ID)."""
        oanda_symbol = self._to_oanda_symbol(position_id)
        url = f"{self.base_url}/accounts/{self.account_id}/positions/{oanda_symbol}/close"

        # Determine direction from current position
        positions = self.get_positions()
        pos = next((p for p in positions if p.symbol == position_id), None)
        if not pos:
            return {"success": False, "error": "Position not found"}

        payload = {"longUnits": "ALL"} if pos.side == "BUY" else {"shortUnits": "ALL"}

        try:
            response = self._session.put(url, json=payload, timeout=10)
            response.raise_for_status()
            return {"success": True, "broker": "OANDA"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def modify_position(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop: float | None = None,
    ) -> dict[str, Any]:
        """Modify stops on an open position."""
        oanda_symbol = self._to_oanda_symbol(position_id)
        url = f"{self.base_url}/accounts/{self.account_id}/positions/{oanda_symbol}/clientExtensions"

        extensions: dict[str, Any] = {}
        if stop_loss:
            extensions["stopLoss"] = {"price": str(stop_loss)}
        if take_profit:
            extensions["takeProfit"] = {"price": str(take_profit)}
        if trailing_stop:
            extensions["trailingStopLoss"] = {"distance": str(trailing_stop)}

        try:
            response = self._session.put(url, json=extensions, timeout=10)
            response.raise_for_status()
            return {"success": True, "broker": "OANDA"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions."""
        url = f"{self.base_url}/accounts/{self.account_id}/openPositions"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        positions = []
        for pos in data.get("positions", []):
            instrument = self._from_oanda_symbol(pos["instrument"])
            long_units = float(pos.get("long", {}).get("units", 0))
            short_units = float(pos.get("short", {}).get("units", 0))

            if long_units > 0:
                positions.append(BrokerPosition(
                    position_id=f"{instrument}_LONG",
                    symbol=instrument,
                    side="BUY",
                    units=long_units,
                    entry_price=float(pos.get("long", {}).get("averagePrice", 0)),
                    current_price=0.0,  # Would need separate price fetch
                    unrealized_pnl=float(pos.get("long", {}).get("unrealizedPL", 0)),
                ))
            elif short_units < 0:
                positions.append(BrokerPosition(
                    position_id=f"{instrument}_SHORT",
                    symbol=instrument,
                    side="SELL",
                    units=abs(short_units),
                    entry_price=float(pos.get("short", {}).get("averagePrice", 0)),
                    current_price=0.0,
                    unrealized_pnl=float(pos.get("short", {}).get("unrealizedPL", 0)),
                ))

        return positions

    def get_orders(self) -> list[dict[str, Any]]:
        """Get pending orders."""
        url = f"{self.base_url}/accounts/{self.account_id}/pendingOrders"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("orders", [])

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a pending order."""
        url = f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}/cancel"
        try:
            response = self._session.put(url, timeout=10)
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _to_oanda_symbol(symbol: str) -> str:
        """Convert trading symbol to OANDA format."""
        mapping = {
            "XAUUSD": "XAU_USD",
            "EURUSD": "EUR_USD",
            "GBPUSD": "GBP_USD",
            "USDJPY": "USD_JPY",
            "BTCUSD": "BTC_USD",
        }
        return mapping.get(symbol.upper(), symbol.replace("/", "_"))

    @staticmethod
    def _from_oanda_symbol(oanda_symbol: str) -> str:
        """Convert OANDA symbol to trading format."""
        return oanda_symbol.replace("_", "")
