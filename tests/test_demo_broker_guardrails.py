import pytest

from src.broker.demo_broker_guardrails import (
    assert_allow_live_false,
    assert_demo_only,
    assert_execution_disabled,
    assert_no_real_order_method_available,
)


def test_demo_broker_guardrails_accept_safe_config():
    config = {"demo_only": True, "allow_live": False, "execution_enabled": False}

    assert_demo_only(config)
    assert_allow_live_false(config)
    assert_execution_disabled(config)


def test_demo_broker_guardrails_reject_unsafe_flags():
    with pytest.raises(PermissionError, match="demo_only"):
        assert_demo_only({"demo_only": False})
    with pytest.raises(PermissionError, match="allow_live"):
        assert_allow_live_false({"allow_live": True})
    with pytest.raises(PermissionError, match="execution_enabled"):
        assert_execution_disabled({"execution_enabled": True})


def test_demo_broker_guardrails_reject_order_methods():
    class UnsafeClient:
        def place_order(self):
            return None

    with pytest.raises(PermissionError, match="place_order"):
        assert_no_real_order_method_available(UnsafeClient())
