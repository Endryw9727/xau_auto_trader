"""
Guardrails for the demo broker.

This module provides safety checks for demo trading.
It ensures no real orders are sent and all trades are simulated.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class GuardrailsConfig:
    """Configuration for demo broker guardrails."""

    allow_real_orders: bool = False
    max_demo_trades_per_day: int = 10
    require_stop_loss: bool = True

class DemoBrokerGuardrails:
    """Guardrails to prevent accidental live trading."""

    def __init__(self, config: GuardrailsConfig):
        self.config = config
        self.daily_trade_count = 0

    def check_order(self, side: str, entry: float, stop_loss: float | None) -> dict:
        """Check if an order passes all guardrails."""
        if self.config.allow_real_orders:
            return {"allowed": False, "reason": "Real orders are not allowed in demo mode"}

        if self.config.require_stop_loss and stop_loss is None:
            return {"allowed": False, "reason": "Stop loss is required"}

        if self.daily_trade_count >= self.config.max_demo_trades_per_day:
            return {"allowed": False, "reason": f"Max demo trades per day reached ({self.config.max_demo_trades_per_day})"}

        return {"allowed": True, "reason": "Guardrails passed"}

    def register_trade(self) -> None:
        """Register a demo trade."""
        self.daily_trade_count += 1

    def reset_daily_count(self) -> None:
        """Reset daily trade count."""
        self.daily_trade_count = 0
