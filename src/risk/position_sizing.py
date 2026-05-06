"""
Position sizing utilities.

This module calculates position size based on:
- account balance
- risk percentage
- entry price
- stop loss price
- value per point

For XAU/USD, the exact value per point depends on the broker contract specification.
This module keeps it configurable and testable.
"""

from __future__ import annotations


def calculate_risk_amount(account_balance: float, risk_percent: float) -> float:
    """
    Calculate monetary risk amount.

    Example:
    account_balance = 1000
    risk_percent = 0.01
    risk amount = 10
    """
    if account_balance <= 0:
        raise ValueError("account_balance must be greater than 0")

    if risk_percent <= 0:
        raise ValueError("risk_percent must be greater than 0")

    if risk_percent > 1:
        raise ValueError("risk_percent must be expressed as decimal, e.g. 0.01 for 1%")

    return account_balance * risk_percent


def calculate_stop_distance(entry_price: float, stop_loss: float) -> float:
    """Calculate absolute stop loss distance."""
    if entry_price <= 0:
        raise ValueError("entry_price must be greater than 0")

    if stop_loss <= 0:
        raise ValueError("stop_loss must be greater than 0")

    distance = abs(entry_price - stop_loss)

    if distance <= 0:
        raise ValueError("stop distance must be greater than 0")

    return distance


def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    value_per_point: float = 1.0,
) -> float:
    """
    Calculate position size.

    Formula:
    position_size = risk_amount / (stop_distance * value_per_point)

    value_per_point must be configured according to the broker/contract.
    """
    if value_per_point <= 0:
        raise ValueError("value_per_point must be greater than 0")

    risk_amount = calculate_risk_amount(account_balance, risk_percent)
    stop_distance = calculate_stop_distance(entry_price, stop_loss)

    return risk_amount / (stop_distance * value_per_point)


def calculate_risk_reward(entry_price: float, stop_loss: float, take_profit: float) -> float:
    """Calculate risk/reward ratio."""
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)

    if risk <= 0:
        raise ValueError("risk must be greater than 0")

    return reward / risk
