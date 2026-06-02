"""
Risk manager for XAU/USD trading.

This module enforces risk rules before any trade can be accepted.
It does not execute trades. It only validates trade proposals.

Rules enforced:
- max risk per trade
- max daily loss
- max open trades
- max consecutive losses
- minimum risk/reward ratio
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.risk.position_sizing import PositionSizeResult, calculate_position_size

TradeSide = Literal["BUY", "SELL"]

@dataclass(frozen=True)
class RiskConfig:
    """Risk management configuration."""

    risk_per_trade: float = 0.005
    max_risk_per_trade: float = 0.01
    max_daily_loss: float = 0.02
    max_open_trades: int = 2
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0

@dataclass(frozen=True)
class TradeProposal:
    """A proposed trade to be validated by the risk manager."""

    side: TradeSide
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    timestamp: pd.Timestamp

@dataclass(frozen=True)
class RiskCheckResult:
    """Result of a risk validation check."""

    allowed: bool
    reason: str
    position_size: PositionSizeResult | None = None

class RiskManager:
    """
    Risk manager that validates trade proposals against risk rules.

    This class is stateful: it tracks open trades, daily loss, and consecutive losses.
    """

    def __init__(self, config: RiskConfig, initial_balance: float):
        self.config = config
        self.balance = initial_balance
        self.open_trades: list[dict] = []
        self.daily_loss = 0.0
        self.consecutive_losses = 0
        self.trade_history: list[dict] = []

    def reset_daily_stats(self) -> None:
        """Reset daily tracking stats."""
        self.daily_loss = 0.0

    def can_open_trade(self, proposal: TradeProposal) -> RiskCheckResult:
        """
        Validate a trade proposal against all risk rules.

        Returns a RiskCheckResult with allowed=True only if all rules pass.
        """
        if len(self.open_trades) >= self.config.max_open_trades:
            return RiskCheckResult(
                allowed=False,
                reason=f"Max open trades reached ({self.config.max_open_trades})",
            )

        if self.consecutive_losses >= self.config.max_consecutive_losses:
            return RiskCheckResult(
                allowed=False,
                reason=f"Max consecutive losses reached ({self.config.max_consecutive_losses})",
            )

        if self.daily_loss >= self.balance * self.config.max_daily_loss:
            return RiskCheckResult(
                allowed=False,
                reason=f"Max daily loss reached ({self.config.max_daily_loss * 100:.1f}%)",
            )

        if proposal.risk_reward < self.config.min_risk_reward:
            return RiskCheckResult(
                allowed=False,
                reason=f"Risk/reward too low ({proposal.risk_reward:.2f} < {self.config.min_risk_reward})",
            )

        position_size = calculate_position_size(
            account_balance=self.balance,
            risk_per_trade=self.config.risk_per_trade,
            entry_price=proposal.entry,
            stop_loss=proposal.stop_loss,
            value_per_point=self.config.value_per_point,
        )

        if not position_size.is_valid:
            return RiskCheckResult(
                allowed=False,
                reason=f"Position sizing failed: {position_size.reason}",
            )

        if position_size.risk_amount > self.balance * self.config.max_risk_per_trade:
            return RiskCheckResult(
                allowed=False,
                reason=f"Risk amount exceeds max per trade ({self.config.max_risk_per_trade * 100:.1f}%)",
            )

        return RiskCheckResult(
            allowed=True,
            reason="All risk checks passed",
            position_size=position_size,
        )

    def register_trade(self, trade: dict) -> None:
        """Register an accepted trade in the manager state."""
        self.open_trades.append(trade)

    def close_trade(self, trade_id: str, outcome: float) -> None:
        """
        Close a trade and update stats.

        Parameters:
        - trade_id: identifier of the trade to close
        - outcome: profit (positive) or loss (negative)
        """
        trade = next((t for t in self.open_trades if t.get("id") == trade_id), None)

        if trade is None:
            raise ValueError(f"Trade {trade_id} not found in open trades")

        self.open_trades.remove(trade)
        self.trade_history.append({**trade, "outcome": outcome})

        if outcome < 0:
            self.daily_loss += abs(outcome)
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.balance += outcome

    def get_stats(self) -> dict:
        """Return current risk manager stats."""
        return {
            "balance": self.balance,
            "open_trades": len(self.open_trades),
            "daily_loss": self.daily_loss,
            "consecutive_losses": self.consecutive_losses,
            "total_trades": len(self.trade_history),
        }
