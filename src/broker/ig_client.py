"""
IG REST API client.

Supports:
- Account info
- Price streaming
- Order placement
- Position management
- Working orders (limits/stops)

Requires IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD in .env
Uses IG demo environment by default.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from src.broker.broker_interface import BaseBrokerInterface, BrokerAccount, BrokerOrder, BrokerPosition
from src.broker.safety_gate import SafetyGate

IG_DEMO_URL = "https://demo-api.ig.com/gateway/deal"
IG_LIVE_URL = "https://api.ig.com/gateway/deal"


class IGClient(BaseBrokerInterface):
    """IG REST API client with safety gate."""

    def __init__(self, paper_mode: bool = True):
        super().__init__("IG", paper_mode=paper_mode)
        self.api_key = os.getenv("IG_API_KEY", "")
        self.identifier = os.getenv("IG_IDENTIFIER", "")
        self.password = os.getenv("IG_PASSWORD", "")
        self.base_url = IG_DEMO_URL if paper_mode else IG_LIVE_URL
        self.safety_gate = SafetyGate()
        self._session = requests.Session()
        self._auth_token = ""

    def connect(self) -> dict[str, Any]:
        """Authenticate with IG API."""
        if not all([self.api_key, self.identifier, self.password]):
            return {"success": False, "error": "IG credentials not set in .env"}

        headers = {
            "X-IG-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Version": "2",
        }
        payload = {
            "identifier": self.identifier,
            "password": self.password,
        }

        try:
            response = self._session.post(
                f"{self.base_url}/session",
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            self._auth_token = data.get("oauthToken", {}).get("access_token", "")
            self._session.headers.update({
                "Authorization": f"Bearer {self._auth_token}",
                "X-IG-API-KEY": self.api_key,
            })
            self.connected = True
            return {"success": True, "account_type": data.get("accountType", "UNKNOWN")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict[str, Any]:
        self.connected = False
        self._auth_token = ""
        return {"success": True}

    def get_account(self) -> BrokerAccount:
        """Get IG account info."""
        url = f"{self.base_url}/accounts"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # IG returns list of accounts, use first
        account = data.get("accounts", [{}])[0]
        balance_data = account.get("balance", {})

        return BrokerAccount(
            account_id=account.get("accountId", ""),
            balance=float(balance_data.get("balance", 0)),
            equity=float(balance_data.get("available", 0)),
            margin_used=float(balance_data.get("deposit", 0)),
            margin_available=float(balance_data.get("available", 0)),
            open_positions=0,  # Would need separate fetch
            currency=account.get("currency", "USD"),
        )

    def get_price(self, symbol: str) -> dict[str, float]:
        """Get current price for an epic."""
        epic = self._to_ig_epic(symbol)
        url = f"{self.base_url}/markets/{epic}"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        snapshot = data.get("snapshot", {})

        return {
            "bid": float(snapshot.get("bid", 0)),
            "ask": float(snapshot.get("offer", 0)),
            "mid": (float(snapshot.get("bid", 0)) + float(snapshot.get("offer", 0))) / 2,
            "spread": float(snapshot.get("offer", 0)) - float(snapshot.get("bid", 0)),
        }

    def place_order(self, order: BrokerOrder) -> dict[str, Any]:
        """Place an order through IG with safety gate."""
        if not self.paper_mode:
            safety = self.safety_gate.check_can_trade(order.symbol, order.units)
            self.safety_gate.record_trade_attempt(
                order.symbol, order.side, order.units, 0.0,
                safety["allowed"], safety["reason"],
            )
            if not safety["allowed"]:
                return {"success": False, "error": safety["reason"], "safety_blocked": True}

        epic = self._to_ig_epic(order.symbol)
        direction = "BUY" if order.side == "BUY" else "SELL"

        payload: dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": order.units,
            "orderType": order.order_type,
            "timeInForce": order.time_in_force,
        }

        if order.entry_price and order.order_type in ("LIMIT", "STOP"):
            payload["level"] = order.entry_price
        if order.stop_loss:
            payload["stopLevel"] = order.stop_loss
        if order.take_profit:
            payload["profitLevel"] = order.take_profit
        if order.trailing_stop_distance:
            payload["trailingStop"] = True
            payload["trailingStopDistance"] = order.trailing_stop_distance
            payload["trailingStopIncrement"] = order.trailing_stop_step or 1.0

        url = f"{self.base_url}/positions/otc"

        try:
            response = self._session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if not self.paper_mode:
                self.safety_gate.register_executed_trade(0.0)

            return {
                "success": True,
                "deal_ref": result.get("dealReference"),
                "broker": "IG",
                "paper_mode": self.paper_mode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_position(self, position_id: str) -> dict[str, Any]:
        """Close a position by deal ID."""
        url = f"{self.base_url}/positions/otc"
        # IG requires fetching position first to determine direction
        positions = self.get_positions()
        pos = next((p for p in positions if p.position_id == position_id), None)
        if not pos:
            return {"success": False, "error": "Position not found"}

        epic = self._to_ig_epic(pos.symbol)
        direction = "SELL" if pos.side == "BUY" else "BUY"

        payload = {
            "epic": epic,
            "direction": direction,
            "size": pos.units,
            "orderType": "MARKET",
        }

        try:
            response = self._session.delete(url, json=payload, timeout=10)
            response.raise_for_status()
            return {"success": True, "broker": "IG"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def modify_position(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop: float | None = None,
    ) -> dict[str, Any]:
        """Modify stops on a position."""
        url = f"{self.base_url}/positions/otc/{position_id}"
        payload: dict[str, Any] = {}
        if stop_loss:
            payload["stopLevel"] = stop_loss
        if take_profit:
            payload["profitLevel"] = take_profit
        if trailing_stop:
            payload["trailingStop"] = True
            payload["trailingStopDistance"] = trailing_stop

        try:
            response = self._session.put(url, json=payload, timeout=10)
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> list[BrokerPosition]:
        """Get open positions."""
        url = f"{self.base_url}/positions"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        positions = []
        for pos in data.get("positions", []):
            market = pos.get("market", {})
            position = pos.get("position", {})
            positions.append(BrokerPosition(
                position_id=position.get("dealId", ""),
                symbol=self._from_ig_epic(market.get("epic", "")),
                side="BUY" if position.get("direction") == "BUY" else "SELL",
                units=float(position.get("size", 0)),
                entry_price=float(position.get("openLevel", 0)),
                current_price=float(market.get("bid", 0)),
                unrealized_pnl=float(position.get("unrealisedPnl", 0)),
            ))
        return positions

    def get_orders(self) -> list[dict[str, Any]]:
        """Get working orders."""
        url = f"{self.base_url}/workingorders"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("workingOrders", [])

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a working order."""
        url = f"{self.base_url}/workingorders/otc/{order_id}"
        try:
            response = self._session.delete(url, timeout=10)
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _to_ig_epic(symbol: str) -> str:
        """Map symbol to IG epic."""
        mapping = {
            "XAUUSD": "CS.D.CFDGOLD.CFDGC.IP",
            "EURUSD": "CS.D.EURUSD.CFD.IP",
            "GBPUSD": "CS.D.GBPUSD.CFD.IP",
            "USDJPY": "CS.D.USDJPY.CFD.IP",
            "BTCUSD": "CS.D.BITCOIN.CFD.IP",
        }
        return mapping.get(symbol.upper(), symbol)

    @staticmethod
    def _from_ig_epic(epic: str) -> str:
        """Map epic back to symbol."""
        reverse = {
            "CS.D.CFDGOLD.CFDGC.IP": "XAUUSD",
            "CS.D.EURUSD.CFD.IP": "EURUSD",
            "CS.D.GBPUSD.CFD.IP": "GBPUSD",
            "CS.D.USDJPY.CFD.IP": "USDJPY",
            "CS.D.BITCOIN.CFD.IP": "BTCUSD",
        }
        return reverse.get(epic, epic)
