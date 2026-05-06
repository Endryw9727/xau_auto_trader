"""
Risk manager.

The risk manager decides whether a signal can be approved or must be blocked.

It does not execute trades.
It protects the system from:
- missing stop loss
- excessive risk
- poor risk/reward
- too many open trades
- daily loss limit
- too many consecutive losses
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.risk.position_sizing import calculate_position_size, calculate_risk_amount


DecisionStatus = Literal["APPROVED", "BLOCKED"]


@dataclass(frozen=True)
class RiskConfig:
    """Risk management configuration."""

    account_balance: float = 1000.0
    risk_per_trade: float = 0.005
    max_risk_per_trade: float = 0.01
    max_daily_loss: float = 0.02
    max_open_trades: int = 2
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0


@dataclass(frozen=True)
class AccountState:
    """Current account/trading state."""

    current_daily_pnl: float = 0.0
    open_trades_count: int = 0
    consecutive_losses: int = 0


@dataclass(frozen=True)
class RiskDecision:
    """Risk manager decision."""

    status: DecisionStatus
    approved: bool
    reason: str
    position_size: float | None
    risk_amount: float | None
    risk_percent: float | None


@dataclass(frozen=True)
class SignalForRisk:
    """
    Minimal signal structure required by the risk manager.

    This avoids coupling the risk layer too tightly to strategy classes.
    """

    side: str
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None


def evaluate_signal_risk(
    signal: SignalForRisk,
    config: RiskConfig | None = None,
    account_state: AccountState | None = None,
) -> RiskDecision:
    """
    Evaluate whether a signal is allowed by risk rules.

    Returns APPROVED only if all checks pass.
    """
    if config is None:
        config = RiskConfig()

    if account_state is None:
        account_state = AccountState()

    if signal.side not in {"BUY", "SELL"}:
        return _blocked("Signal side is not tradable")

    if signal.entry_price is None:
        return _blocked("Missing entry price")

    if signal.stop_loss is None:
        return _blocked("Missing stop loss")

    if signal.take_profit is None:
        return _blocked("Missing take profit")

    if signal.risk_reward is None:
        return _blocked("Missing risk/reward")

    if signal.risk_reward < config.min_risk_reward:
        return _blocked(f"Risk/reward below minimum: {signal.risk_reward:.2f} < {config.min_risk_reward:.2f}")

    if config.risk_per_trade <= 0:
        return _blocked("risk_per_trade must be greater than 0")

    if config.risk_per_trade > config.max_risk_per_trade:
        return _blocked("Risk per trade exceeds max allowed risk")

    max_daily_loss_amount = config.account_balance * config.max_daily_loss

    if account_state.current_daily_pnl <= -max_daily_loss_amount:
        return _blocked("Daily loss limit reached")

    if account_state.open_trades_count >= config.max_open_trades:
        return _blocked("Maximum open trades reached")

    if account_state.consecutive_losses >= config.max_consecutive_losses:
        return _blocked("Maximum consecutive losses reached")

    try:
        position_size = calculate_position_size(
            account_balance=config.account_balance,
            risk_percent=config.risk_per_trade,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            value_per_point=config.value_per_point,
        )
        risk_amount = calculate_risk_amount(config.account_balance, config.risk_per_trade)
    except ValueError as exc:
        return _blocked(str(exc))

    return RiskDecision(
        status="APPROVED",
        approved=True,
        reason="Signal approved by risk manager",
        position_size=position_size,
        risk_amount=risk_amount,
        risk_percent=config.risk_per_trade,
    )


def from_trading_signal(signal) -> SignalForRisk:
    """
    Convert any signal-like object into SignalForRisk.

    The object must expose:
    side, entry_price, stop_loss, take_profit, risk_reward
    """
    return SignalForRisk(
        side=signal.side,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        risk_reward=signal.risk_reward,
    )


def _blocked(reason: str) -> RiskDecision:
    """Return a blocked risk decision."""
    return RiskDecision(
        status="BLOCKED",
        approved=False,
        reason=reason,
        position_size=None,
        risk_amount=None,
        risk_percent=None,
    )
