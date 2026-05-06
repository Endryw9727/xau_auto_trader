import pytest

from src.execution.live_broker import (
    LiveBrokerConfig,
    LiveOrderRequest,
    LiveTradingDisabledError,
    ProtectedLiveBroker,
)


def make_order_request() -> LiveOrderRequest:
    return LiveOrderRequest(
        symbol="XAUUSD",
        side="BUY",
        order_type="MARKET",
        entry_price=None,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=0.01,
        risk_percent=0.005,
    )


def test_live_broker_blocks_orders_when_live_mode_false():
    broker = ProtectedLiveBroker(LiveBrokerConfig(live_mode=False))
    request = make_order_request()

    with pytest.raises(LiveTradingDisabledError):
        broker.submit_order(request)


def test_live_broker_blocks_cancel_when_live_mode_false():
    broker = ProtectedLiveBroker(LiveBrokerConfig(live_mode=False))

    with pytest.raises(LiveTradingDisabledError):
        broker.cancel_order("order-123")


def test_live_broker_blocks_close_when_live_mode_false():
    broker = ProtectedLiveBroker(LiveBrokerConfig(live_mode=False))

    with pytest.raises(LiveTradingDisabledError):
        broker.close_position("position-123")


def test_live_broker_refuses_unimplemented_execution_when_live_mode_true():
    broker = ProtectedLiveBroker(
        LiveBrokerConfig(
            live_mode=True,
            allow_market_orders=True,
            max_order_risk_percent=0.01,
        )
    )
    request = make_order_request()

    response = broker.submit_order(request)

    assert response.accepted is False
    assert "not implemented" in response.message


def test_live_broker_rejects_market_orders_if_not_allowed():
    broker = ProtectedLiveBroker(
        LiveBrokerConfig(
            live_mode=True,
            allow_market_orders=False,
        )
    )
    request = make_order_request()

    with pytest.raises(ValueError):
        broker.submit_order(request)


def test_live_broker_rejects_excessive_risk():
    broker = ProtectedLiveBroker(
        LiveBrokerConfig(
            live_mode=True,
            allow_market_orders=True,
            max_order_risk_percent=0.01,
        )
    )
    request = LiveOrderRequest(
        symbol="XAUUSD",
        side="BUY",
        order_type="MARKET",
        entry_price=None,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=0.01,
        risk_percent=0.02,
    )

    with pytest.raises(ValueError):
        broker.submit_order(request)


def test_live_broker_rejects_invalid_position_size():
    broker = ProtectedLiveBroker(
        LiveBrokerConfig(
            live_mode=True,
            allow_market_orders=True,
        )
    )
    request = LiveOrderRequest(
        symbol="XAUUSD",
        side="BUY",
        order_type="MARKET",
        entry_price=None,
        stop_loss=2345.0,
        take_profit=2360.0,
        position_size=0.0,
        risk_percent=0.005,
    )

    with pytest.raises(ValueError):
        broker.submit_order(request)
