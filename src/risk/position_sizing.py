"""
Position sizing utilities.

This module calculates lot size or units based on risk parameters.
It does not execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class PositionSizeResult:
    """Result of a position size calculation."""

    units: float
    risk_amount: float
    risk_per_unit: float
    is_valid: bool
    reason: str

def calculate_position_size(
    account_balance: float,
    risk_per_trade: float,
    entry_price: float,
    stop_loss: float,
    value_per_point: float = 1.0,
) -> PositionSizeResult:
    """
    Calculate position size based on risk.

    Parameters:
    - account_balance: current account balance
    - risk_per_trade: risk fraction (e.g. 0.005 = 0.5%)
    - entry_price: planned entry price
    - stop_loss: planned stop loss price
    - value_per_point: monetary value per price point

    Returns:
    - PositionSizeResult with units, risk amount, and validity flag.
    """
    if account_balance <= 0:
        return PositionSizeResult(
            units=0.0,
            risk_amount=0.0,
            risk_per_unit=0.0,
            is_valid=False,
            reason="Account balance must be greater than 0",
        )

    if risk_per_trade <= 0 or risk_per_trade > 1:
        return PositionSizeResult(
            units=0.0,
            risk_amount=0.0,
            risk_per_unit=0.0,
            is_valid=False,
            reason="risk_per_trade must be between 0 and 1",
        )

    risk_distance = abs(entry_price - stop_loss)

    if risk_distance <= 0:
        return PositionSizeResult(
            units=0.0,
            risk_amount=0.0,
            risk_per_unit=0.0,
            is_valid=False,
            reason="Stop loss distance must be greater than 0",
        )

    risk_amount = account_balance * risk_per_trade
    risk_per_unit = risk_distance * value_per_point
    units = risk_amount / risk_per_unit

    return PositionSizeResult(
        units=units,
        risk_amount=risk_amount,
        risk_per_unit=risk_per_unit,
        is_valid=True,
        reason="Position size calculated successfully",
    )
