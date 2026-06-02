"""Tests for advanced order types."""
import pytest

from src.execution.advanced_orders import (
    AdvancedOrderBuilder, BracketConfig, OCOConfig, OrderExpiryManager,
    ScaleConfig, TrailingStopConfig,
)
from src.broker.broker_interface import BrokerOrder


def test_trailing_stop_order():
    config = TrailingStopConfig(
        enabled=True, type="atr_multiplier", distance=1.5, step=1.0,
    )
    order = AdvancedOrderBuilder.trailing_stop_order(
        symbol="XAUUSD", side="BUY", units=1.0,
        entry_price=2350.0, current_price=2350.0,
        atr=10.0, config=config,
    )
    assert order.symbol == "XAUUSD"
    assert order.trailing_stop_distance == 15.0  # 10 * 1.5
    assert order.stop_loss is not None


def test_bracket_order():
    config = BracketConfig(
        enabled=True, entry_price=None, entry_type="MARKET",
        sl_distance=15.0, tp_distance=30.0,
    )
    order = AdvancedOrderBuilder.bracket_order(
        symbol="XAUUSD", side="BUY", units=1.0,
        current_price=2350.0, config=config,
    )
    assert order.stop_loss == 2335.0  # 2350 - 15
    assert order.take_profit == 2380.0  # 2350 + 30


def test_oco_order_pair():
    config = OCOConfig(
        enabled=True, limit_price=2345.0, stop_price=2355.0,
        limit_units=1.0, stop_units=1.0,
    )
    orders = AdvancedOrderBuilder.oco_order_pair(
        symbol="XAUUSD", side="BUY", current_price=2350.0, config=config,
    )
    assert len(orders) == 2
    assert orders[0].order_type == "LIMIT"
    assert orders[1].order_type == "STOP"


def test_scale_orders():
    config = ScaleConfig(
        enabled=True, levels=[2340.0, 2345.0, 2350.0],
        units_per_level=[0.3, 0.3, 0.4], type="scale_in",
    )
    orders = AdvancedOrderBuilder.scale_orders(
        symbol="XAUUSD", side="BUY", current_price=2350.0, config=config,
    )
    assert len(orders) == 3
    assert orders[0].entry_price == 2340.0


def test_order_expiry_gtd():
    order = BrokerOrder(symbol="XAUUSD", side="BUY", order_type="LIMIT", units=1.0)
    from datetime import datetime, timedelta
    expiry = (datetime.now() + timedelta(hours=2)).isoformat()
    expired = OrderExpiryManager.set_gtd_expiry(order, expiry)
    assert expired.time_in_force == "GTD"
    assert expired.expiry == expiry
