"""
Abstract broker interface for real trading.

All real broker implementations must inherit from this interface
and pass through the SafetyGate before executing any order.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

TradeSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP", "OCO", "BRACKET"]

@dataclass(frozen=True)
class BrokerOrder:
    """Standardized order for any broker."""

    symbol: str
    side: TradeSide
    order_type: OrderType
    units: float
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_distance: float | None = None
    trailing_stop_step: float | None = None
    time_in_force: str = "GTC"  # GTC, IOC, FOK, GTD
    expiry: str | None = None
    client_comment: str = ""

@dataclass(frozen=True)
class BrokerPosition:
    """Standardized position from any broker."""

    position_id: str
    symbol: str
    side: TradeSide
    units: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop: float | None = None
    open_time: str = ""

@dataclass(frozen=True)
class BrokerAccount:
    """Standardized account info from any broker."""

    account_id: str
    balance: float
    equity: float
    margin_used: float
    margin_available: float
    open_positions: int
    currency: str = "USD"


class BaseBrokerInterface(ABC):
    """Abstract base class for all broker implementations."""

    def __init__(self, name: str, paper_mode: bool = True):
        self.name = name
        self.paper_mode = paper_mode
        self.connected = False

    @abstractmethod
    def connect(self) -> dict[str, Any]:
        """Connect to broker API."""
        pass

    @abstractmethod
    def disconnect(self) -> dict[str, Any]:
        """Disconnect from broker API."""
        pass

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        """Get account information."""
        pass

    @abstractmethod
    def get_price(self, symbol: str) -> dict[str, float]:
        """Get current price (bid/ask/mid)."""
        pass

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> dict[str, Any]:
        """Place an order. Must check SafetyGate for real orders."""
        pass

    @abstractmethod
    def close_position(self, position_id: str) -> dict[str, Any]:
        """Close an open position."""
        pass

    @abstractmethod
    def modify_position(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop: float | None = None,
    ) -> dict[str, Any]:
        """Modify an open position (SL/TP/trailing)."""
        pass

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions."""
        pass

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]:
        """Get all pending orders."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a pending order."""
        pass
