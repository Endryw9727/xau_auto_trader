"""
Protected live broker interface.

This module is intentionally safe by default.

It does NOT connect to any real broker yet.
It does NOT send real orders.

Purpose:
- define the future live broker interface
- prevent accidental live trading
- block every order unless live_mode=True
- make safety testable
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP"]


class LiveTradingDisabledError(RuntimeError):
    """Raised when live trading is attempted while disabled."""


@dataclass(frozen=True)
class LiveBrokerConfig:
    """Live broker safety configuration."""

    live_mode: bool = False
    broker_name: str = "UNCONFIGURED"
    account_id: str | None = None
    allow_market_orders: bool = False
    allow_limit_orders: bool = False
    max_order_risk_percent: float = 0.01


@dataclass(frozen=True)
class LiveOrderRequest:
    """Future live order request."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    entry_price: float | None
    stop_loss: float
    take_profit: float
    position_size: float
    risk_percent: float


@dataclass(frozen=True)
class LiveOrderResponse:
    """Future live order response."""

    accepted: bool
    message: str
    broker_order_id: str | None = None


class ProtectedLiveBroker:
    """
    Protected live broker.

    Every real execution method is blocked unless live_mode=True.

    Even when live_mode=True, this first version still does not send orders.
    Real broker integration must be implemented later and tested separately.
    """

    def __init__(self, config: LiveBrokerConfig | None = None) -> None:
        self.config = config or LiveBrokerConfig()

    def submit_order(self, request: LiveOrderRequest) -> LiveOrderResponse:
        """
        Submit a live order request.

        Current behavior:
        - blocks if live_mode=False
        - validates basic safety
        - still refuses real execution because no broker is connected yet
        """
        self._ensure_live_mode_enabled()
        self._validate_order_request(request)

        return LiveOrderResponse(
            accepted=False,
            message="Live broker integration not implemented. No real order was sent.",
            broker_order_id=None,
        )

    def cancel_order(self, broker_order_id: str) -> LiveOrderResponse:
        """Cancel a future live order."""
        self._ensure_live_mode_enabled()

        if not broker_order_id:
            raise ValueError("broker_order_id cannot be empty")

        return LiveOrderResponse(
            accepted=False,
            message="Live cancel integration not implemented. No real cancel request was sent.",
            broker_order_id=broker_order_id,
        )

    def close_position(self, broker_position_id: str) -> LiveOrderResponse:
        """Close a future live position."""
        self._ensure_live_mode_enabled()

        if not broker_position_id:
            raise ValueError("broker_position_id cannot be empty")

        return LiveOrderResponse(
            accepted=False,
            message="Live close integration not implemented. No real close request was sent.",
            broker_order_id=broker_position_id,
        )

    def _ensure_live_mode_enabled(self) -> None:
        """Block execution if live mode is disabled."""
        if not self.config.live_mode:
            raise LiveTradingDisabledError(
                "Live trading is disabled. Set live_mode=True only after backtest, paper trading, "
                "broker integration tests, and manual approval."
            )

    def _validate_order_request(self, request: LiveOrderRequest) -> None:
        """Validate live order safety rules."""
        if request.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

        if request.order_type not in {"MARKET", "LIMIT", "STOP"}:
            raise ValueError("order_type must be MARKET, LIMIT, or STOP")

        if request.order_type == "MARKET" and not self.config.allow_market_orders:
            raise ValueError("Market orders are not allowed by config")

        if request.order_type == "LIMIT" and not self.config.allow_limit_orders:
            raise ValueError("Limit orders are not allowed by config")

        if request.stop_loss <= 0:
            raise ValueError("stop_loss must be greater than 0")

        if request.take_profit <= 0:
            raise ValueError("take_profit must be greater than 0")

        if request.position_size <= 0:
            raise ValueError("position_size must be greater than 0")

        if request.risk_percent <= 0:
            raise ValueError("risk_percent must be greater than 0")

        if request.risk_percent > self.config.max_order_risk_percent:
            raise ValueError("risk_percent exceeds max allowed live risk")
