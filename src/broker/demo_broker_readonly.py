"""
Demo broker in read-only mode.

This module simulates broker operations without executing real trades.
It is used for paper trading and testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TradeSide = Literal["BUY", "SELL"]

@dataclass(frozen=True)
class DemoOrder:
    """A demo order."""

    id: str
    side: TradeSide
    symbol: str
    entry: float
    stop_loss: float | None
    take_profit: float | None
    units: float
    status: str

@dataclass(frozen=True)
class DemoPosition:
    """A demo position."""

    order_id: str
    side: TradeSide
    symbol: str
    entry: float
    current_price: float
    unrealized_pnl: float

class DemoBrokerReadOnly:
    """Read-only demo broker for paper trading simulation."""

    def __init__(self, initial_balance: float = 1000.0):
        self.balance = initial_balance
        self.orders: list[DemoOrder] = []
        self.positions: list[DemoPosition] = []
        self.order_counter = 0

    def place_order(
        self,
        side: TradeSide,
        symbol: str,
        entry: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        units: float = 1.0,
    ) -> DemoOrder:
        """Place a demo order (simulated, not real)."""
        self.order_counter += 1
        order = DemoOrder(
            id=f"demo_{self.order_counter}",
            side=side,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            units=units,
            status="PENDING",
        )
        self.orders.append(order)
        return order

    def get_positions(self) -> list[DemoPosition]:
        """Get current demo positions."""
        return self.positions

    def close_position(self, order_id: str, exit_price: float) -> dict:
        """Close a demo position."""
        position = next((p for p in self.positions if p.order_id == order_id), None)
        if position is None:
            return {"success": False, "reason": "Position not found"}

        if position.side == "BUY":
            pnl = (exit_price - position.entry) * position.side_units
        else:
            pnl = (position.entry - exit_price) * position.side_units

        self.balance += pnl
        self.positions = [p for p in self.positions if p.order_id != order_id]

        return {"success": True, "pnl": pnl, "balance": self.balance}

    def get_balance(self) -> float:
        """Get current demo balance."""
        return self.balance
