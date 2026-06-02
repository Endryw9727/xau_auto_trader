"""
Interactive Brokers TWS API client.

Supports:
- Connection to TWS/IB Gateway
- Market data
- Order placement (market, limit, stop, bracket)
- Position management
- Trailing stop orders

Requires ib_insync library and running TWS/IB Gateway.
"""

from __future__ import annotations

import os
from typing import Any

from src.broker.broker_interface import BaseBrokerInterface, BrokerAccount, BrokerOrder, BrokerPosition
from src.broker.safety_gate import SafetyGate

IB_GATEWAY_HOST = os.getenv("IB_GATEWAY_HOST", "127.0.0.1")
IB_GATEWAY_PORT = int(os.getenv("IB_GATEWAY_PORT", "7497"))  # 7497 paper, 7496 live
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))


class IBClient(BaseBrokerInterface):
    """Interactive Brokers TWS API client with safety gate."""

    def __init__(self, paper_mode: bool = True):
        super().__init__("InteractiveBrokers", paper_mode=paper_mode)
        self.host = IB_GATEWAY_HOST
        self.port = IB_GATEWAY_PORT if paper_mode else 7496
        self.client_id = IB_CLIENT_ID
        self.safety_gate = SafetyGate()
        self._ib = None
        self._contract_cache: dict[str, Any] = {}

    def connect(self) -> dict[str, Any]:
        """Connect to TWS/IB Gateway."""
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id)
            self.connected = True
            return {
                "success": True,
                "server_version": self._ib.client.serverVersion(),
                "connection_time": str(self._ib.client.connTime),
            }
        except ImportError:
            return {"success": False, "error": "ib_insync not installed. Run: pip install ib_insync"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict[str, Any]:
        if self._ib:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self.connected = False
        return {"success": True}

    def get_account(self) -> BrokerAccount:
        """Get IB account summary."""
        if not self._ib:
            raise RuntimeError("Not connected")

        account_values = self._ib.accountValues()
        summary = {av.tag: av.value for av in account_values if av.currency == "USD"}

        return BrokerAccount(
            account_id=summary.get("AccountCode", "UNKNOWN"),
            balance=float(summary.get("CashBalance", 0)),
            equity=float(summary.get("NetLiquidation", 0)),
            margin_used=float(summary.get("InitMarginReq", 0)),
            margin_available=float(summary.get("AvailableFunds", 0)),
            open_positions=len(self._ib.positions()),
            currency="USD",
        )

    def get_price(self, symbol: str) -> dict[str, float]:
        """Get current market price."""
        if not self._ib:
            raise RuntimeError("Not connected")

        contract = self._get_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(1)

        return {
            "bid": ticker.bid or 0.0,
            "ask": ticker.ask or 0.0,
            "mid": (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else ticker.last or 0.0,
            "spread": (ticker.ask - ticker.bid) if ticker.bid and ticker.ask else 0.0,
        }

    def place_order(self, order: BrokerOrder) -> dict[str, Any]:
        """Place an order through IB with safety gate."""
        if not self.paper_mode:
            safety = self.safety_gate.check_can_trade(order.symbol, order.units)
            self.safety_gate.record_trade_attempt(
                order.symbol, order.side, order.units, 0.0,
                safety["allowed"], safety["reason"],
            )
            if not safety["allowed"]:
                return {"success": False, "error": safety["reason"], "safety_blocked": True}

        if not self._ib:
            return {"success": False, "error": "Not connected to TWS"}

        try:
            from ib_insync import MarketOrder, LimitOrder, StopOrder, BracketOrder, TrailingStopOrder

            contract = self._get_contract(order.symbol)
            action = "BUY" if order.side == "BUY" else "SELL"

            if order.order_type == "MARKET":
                ib_order = MarketOrder(action, order.units)
            elif order.order_type == "LIMIT" and order.entry_price:
                ib_order = LimitOrder(action, order.units, order.entry_price)
            elif order.order_type == "STOP" and order.entry_price:
                ib_order = StopOrder(action, order.units, order.entry_price)
            elif order.order_type == "BRACKET":
                ib_order = BracketOrder(
                    action,
                    order.units,
                    limitPrice=order.entry_price or 0,
                    takeProfitPrice=order.take_profit or 0,
                    stopLossPrice=order.stop_loss or 0,
                )
            elif order.order_type == "OCO":
                # IB uses child orders for OCO
                parent = MarketOrder(action, order.units)
                parent.transmit = False
                take_profit = LimitOrder(
                    "SELL" if action == "BUY" else "BUY",
                    order.units,
                    order.take_profit or 0,
                )
                take_profit.parentId = parent.orderId
                stop_loss = StopOrder(
                    "SELL" if action == "BUY" else "BUY",
                    order.units,
                    order.stop_loss or 0,
                )
                stop_loss.parentId = parent.orderId
                stop_loss.transmit = True

                trade = self._ib.placeOrder(contract, parent)
                self._ib.placeOrder(contract, take_profit)
                self._ib.placeOrder(contract, stop_loss)

                if not self.paper_mode:
                    self.safety_gate.register_executed_trade(0.0)

                return {"success": True, "order_id": trade.order.orderId, "broker": "IB"}
            else:
                ib_order = MarketOrder(action, order.units)

            # Add trailing stop if specified
            if order.trailing_stop_distance and order.order_type not in ("BRACKET", "OCO"):
                ib_order = TrailingStopOrder(
                    action,
                    order.units,
                    trailingPercent=order.trailing_stop_distance,
                )

            trade = self._ib.placeOrder(contract, ib_order)

            if not self.paper_mode:
                self.safety_gate.register_executed_trade(0.0)

            return {
                "success": True,
                "order_id": trade.order.orderId,
                "broker": "InteractiveBrokers",
                "paper_mode": self.paper_mode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_position(self, position_id: str) -> dict[str, Any]:
        """Close a position by symbol."""
        if not self._ib:
            return {"success": False, "error": "Not connected"}

        try:
            positions = self._ib.positions()
            for pos in positions:
                if pos.contract.symbol == position_id or pos.contract.symbol == self._to_ib_symbol(position_id):
                    action = "SELL" if pos.position > 0 else "BUY"
                    from ib_insync import MarketOrder
                    order = MarketOrder(action, abs(pos.position))
                    self._ib.placeOrder(pos.contract, order)
                    return {"success": True, "broker": "IB"}
            return {"success": False, "error": "Position not found"}
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
        if not self._ib:
            return {"success": False, "error": "Not connected"}

        try:
            # Cancel existing stop orders and place new ones
            trades = self._ib.trades()
            for trade in trades:
                if trade.contract.symbol == position_id:
                    if stop_loss or take_profit or trailing_stop:
                        self._ib.cancelOrder(trade.order)

            contract = self._get_contract(position_id)
            # Place new stop order
            if stop_loss:
                from ib_insync import StopOrder
                action = "SELL"  # Simplified, should determine from position
                order = StopOrder(action, 1, stop_loss)
                self._ib.placeOrder(contract, order)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions."""
        if not self._ib:
            return []

        positions = []
        for pos in self._ib.positions():
            side = "BUY" if pos.position > 0 else "SELL"
            positions.append(BrokerPosition(
                position_id=f"{pos.contract.symbol}_{side}",
                symbol=self._from_ib_symbol(pos.contract.symbol),
                side=side,
                units=abs(pos.position),
                entry_price=float(pos.avgCost) if hasattr(pos, "avgCost") else 0.0,
                current_price=0.0,
                unrealized_pnl=0.0,
            ))
        return positions

    def get_orders(self) -> list[dict[str, Any]]:
        """Get pending orders."""
        if not self._ib:
            return []
        return [{"order_id": t.order.orderId, "status": t.orderStatus.status} for t in self._ib.trades()]

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an order."""
        if not self._ib:
            return {"success": False, "error": "Not connected"}

        try:
            for trade in self._ib.trades():
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    return {"success": True}
            return {"success": False, "error": "Order not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_contract(self, symbol: str):
        """Get or create IB contract for symbol."""
        if symbol in self._contract_cache:
            return self._contract_cache[symbol]

        from ib_insync import Forex, ContFuture, Crypto

        ib_symbol = self._to_ib_symbol(symbol)

        if symbol.upper() in {"EURUSD", "GBPUSD", "USDJPY"}:
            contract = Forex(ib_symbol)
        elif symbol.upper() == "XAUUSD":
            # Gold futures on COMEX
            from ib_insync import Future
            contract = Future("GC", "202512", "COMEX")
        elif symbol.upper() == "BTCUSD":
            contract = Crypto("BTC", "PAXOS")
        else:
            contract = Forex(ib_symbol)

        self._ib.qualifyContracts(contract)
        self._contract_cache[symbol] = contract
        return contract

    @staticmethod
    def _to_ib_symbol(symbol: str) -> str:
        """Convert to IB symbol format."""
        mapping = {
            "EURUSD": "EURUSD",
            "GBPUSD": "GBPUSD",
            "USDJPY": "USDJPY",
        }
        return mapping.get(symbol.upper(), symbol)

    @staticmethod
    def _from_ib_symbol(ib_symbol: str) -> str:
        return ib_symbol
