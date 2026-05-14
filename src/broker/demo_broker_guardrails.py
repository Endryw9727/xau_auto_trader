"""Guardrails for demo broker read-only research code."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FORBIDDEN_ORDER_METHODS = {
    "buy",
    "sell",
    "place_order",
    "send_order",
    "execute_order",
    "submit_order",
    "close_position",
    "modify_order",
    "cancel_order",
    "order_send",
}


def assert_demo_only(config: Any) -> None:
    """Raise if the config is not explicitly demo-only."""
    if _get_bool(config, "demo_only") is not True:
        raise PermissionError("Demo broker read-only mode requires demo_only=true.")


def assert_execution_disabled(config: Any) -> None:
    """Raise if execution is enabled."""
    if _get_bool(config, "execution_enabled") is not False:
        raise PermissionError("Demo broker read-only mode requires execution_enabled=false.")


def assert_allow_live_false(config: Any) -> None:
    """Raise if live permission is enabled."""
    if _get_bool(config, "allow_live") is not False:
        raise PermissionError("Demo broker read-only mode requires allow_live=false.")


def assert_no_real_order_method_available(client_or_class: Any) -> None:
    """Raise if an object exposes an active order-sending method."""
    for method_name in FORBIDDEN_ORDER_METHODS:
        method = getattr(client_or_class, method_name, None)
        if callable(method):
            raise PermissionError(f"Order method is forbidden in read-only mode: {method_name}")


def _get_bool(config: Any, field: str) -> bool | None:
    """Read a boolean field from a mapping or object."""
    if isinstance(config, Mapping):
        value = config.get(field)
    else:
        value = getattr(config, field, None)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value
