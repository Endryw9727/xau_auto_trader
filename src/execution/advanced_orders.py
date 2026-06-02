"""
Advanced order types for professional trading.

Supports:
- Trailing Stop Loss (fixed distance or ATR-based)
- OCO (One Cancels Other) orders
- Bracket Orders (entry + SL + TP)
- Time-based order expiry
- Scale-in / Scale-out orders

All orders pass through the safety gate for real trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.broker.broker_interface import BrokerOrder, TradeSide

TrailingType = Literal["fixed_points", "atr_multiplier", "percentage"]

@dataclass(frozen=True)
class TrailingStopConfig:
    """Configuration for trailing stop loss."""

    enabled: bool
    type: TrailingType
    distance: float  # Points, ATR multiplier, or percentage
    step: float = 1.0  # Minimum price movement to adjust stop
    activation_level: float | None = None  # Profit level to activate trailing
    max_distance: float | None = None  # Maximum distance from current price

@dataclass(frozen=True)
class OCOConfig:
    """One-Cancels-Other order pair."""

    enabled: bool
    limit_price: float | None  # Limit entry price
    stop_price: float | None  # Stop entry price
    limit_units: float
    stop_units: float
    shared_sl: float | None = None
    shared_tp: float | None = None

@dataclass(frozen=True)
class BracketConfig:
    """Bracket order: entry + stop loss + take profit."""

    enabled: bool
    entry_price: float | None  # None = market order
    entry_type: Literal["MARKET", "LIMIT", "STOP"]
    sl_distance: float  # Distance from entry
    tp_distance: float  # Distance from entry
    trailing_sl: TrailingStopConfig | None = None

@dataclass(frozen=True)
class ScaleConfig:
    """Scale-in or scale-out configuration."""

    enabled: bool
    levels: list[float]  # Price levels for scaling
    units_per_level: list[float]  # Units at each level
    type: Literal["scale_in", "scale_out"]


class AdvancedOrderBuilder:
    """Builder for advanced order types."""

    @staticmethod
    def trailing_stop_order(
        symbol: str,
        side: TradeSide,
        units: float,
        entry_price: float | None,
        current_price: float,
        atr: float,
        config: TrailingStopConfig,
    ) -> BrokerOrder:
        """
        Build a market or limit order with trailing stop.

        Parameters:
        - symbol: trading symbol
        - side: BUY or SELL
        - units: position size
        - entry_price: entry price (None for market)
        - current_price: current market price
        - atr: current ATR value
        - config: trailing stop configuration
        """
        if not config.enabled:
            raise ValueError("Trailing stop not enabled in config")

        # Calculate initial stop distance
        if config.type == "fixed_points":
            stop_distance = config.distance
        elif config.type == "atr_multiplier":
            stop_distance = atr * config.distance
        elif config.type == "percentage":
            stop_distance = current_price * (config.distance / 100)
        else:
            stop_distance = config.distance

        # Initial stop loss
        if side == "BUY":
            initial_sl = (entry_price or current_price) - stop_distance
        else:
            initial_sl = (entry_price or current_price) + stop_distance

        return BrokerOrder(
            symbol=symbol,
            side=side,
            order_type="MARKET" if entry_price is None else "LIMIT",
            units=units,
            entry_price=entry_price,
            stop_loss=round(initial_sl, 2),
            trailing_stop_distance=round(stop_distance, 2),
            trailing_stop_step=config.step,
            client_comment=f"TrailingStop_{config.type}_{config.distance}",
        )

    @staticmethod
    def bracket_order(
        symbol: str,
        side: TradeSide,
        units: float,
        current_price: float,
        config: BracketConfig,
    ) -> BrokerOrder:
        """
        Build a bracket order with entry, SL, and TP.

        Parameters:
        - symbol: trading symbol
        - side: BUY or SELL
        - units: position size
        - current_price: current market price
        - config: bracket configuration
        """
        if not config.enabled:
            raise ValueError("Bracket order not enabled")

        entry = config.entry_price or current_price

        if side == "BUY":
            sl = entry - config.sl_distance
            tp = entry + config.tp_distance
        else:
            sl = entry + config.sl_distance
            tp = entry - config.tp_distance

        order = BrokerOrder(
            symbol=symbol,
            side=side,
            order_type=config.entry_type,
            units=units,
            entry_price=config.entry_price,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            client_comment="BracketOrder",
        )

        # Add trailing stop if configured
        if config.trailing_sl and config.trailing_sl.enabled:
            order = AdvancedOrderBuilder._add_trailing_to_order(order, config.trailing_sl)

        return order

    @staticmethod
    def oco_order_pair(
        symbol: str,
        side: TradeSide,
        current_price: float,
        config: OCOConfig,
    ) -> list[BrokerOrder]:
        """
        Build an OCO order pair.

        Returns two orders: limit entry and stop entry.
        When one fills, the other must be cancelled.
        """
        if not config.enabled:
            raise ValueError("OCO not enabled")

        orders = []

        if config.limit_price:
            orders.append(BrokerOrder(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                units=config.limit_units,
                entry_price=config.limit_price,
                stop_loss=config.shared_sl,
                take_profit=config.shared_tp,
                client_comment="OCO_LIMIT",
            ))

        if config.stop_price:
            orders.append(BrokerOrder(
                symbol=symbol,
                side=side,
                order_type="STOP",
                units=config.stop_units,
                entry_price=config.stop_price,
                stop_loss=config.shared_sl,
                take_profit=config.shared_tp,
                client_comment="OCO_STOP",
            ))

        return orders

    @staticmethod
    def scale_orders(
        symbol: str,
        side: TradeSide,
        current_price: float,
        config: ScaleConfig,
    ) -> list[BrokerOrder]:
        """
        Build scale-in or scale-out orders.

        Parameters:
        - symbol: trading symbol
        - side: BUY or SELL
        - current_price: current market price
        - config: scale configuration
        """
        if not config.enabled:
            raise ValueError("Scale orders not enabled")

        if len(config.levels) != len(config.units_per_level):
            raise ValueError("levels and units_per_level must have same length")

        orders = []
        for level, units in zip(config.levels, config.units_per_level):
            order_type = "LIMIT" if config.type == "scale_in" else "MARKET"
            orders.append(BrokerOrder(
                symbol=symbol,
                side=side,
                order_type=order_type,
                units=units,
                entry_price=round(level, 2) if config.type == "scale_in" else None,
                client_comment=f"Scale_{config.type}_{level}",
            ))

        return orders

    @staticmethod
    def _add_trailing_to_order(order: BrokerOrder, config: TrailingStopConfig) -> BrokerOrder:
        """Add trailing stop parameters to an existing order."""
        return BrokerOrder(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            units=order.units,
            entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            trailing_stop_distance=config.distance,
            trailing_stop_step=config.step,
            time_in_force=order.time_in_force,
            expiry=order.expiry,
            client_comment=f"{order.client_comment}_TRAILING",
        )


class OrderExpiryManager:
    """Manages order expiry and time-based cancellations."""

    @staticmethod
    def set_gtd_expiry(order: BrokerOrder, expiry_datetime: str) -> BrokerOrder:
        """Set Good-Till-Date expiry on an order."""
        return BrokerOrder(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            units=order.units,
            entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            trailing_stop_distance=order.trailing_stop_distance,
            trailing_stop_step=order.trailing_stop_step,
            time_in_force="GTD",
            expiry=expiry_datetime,
            client_comment=order.client_comment,
        )

    @staticmethod
    def set_session_expiry(order: BrokerOrder) -> BrokerOrder:
        """Set order to expire at end of trading session."""
        from datetime import datetime, timedelta
        expiry = (datetime.now() + timedelta(hours=8)).isoformat()
        return OrderExpiryManager.set_gtd_expiry(order, expiry)
