"""
Safety gate for real broker connections.

This module provides a mandatory approval mechanism before any real
order can be sent to a broker. It requires explicit user confirmation
and logs all attempts.

Rules:
- LIVE_MODE must be explicitly enabled in .env
- User must provide explicit approval per session
- All orders are logged before sending
- Paper mode is always available as fallback
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SAFETY_LOG_PATH = Path("reports/safety/real_trading_attempts.log")

@dataclass(frozen=True)
class SafetyApproval:
    """Represents an explicit safety approval for real trading."""

    approved: bool
    timestamp: str
    user: str
    reason: str
    session_hash: str
    max_risk_per_day: float
    max_trades_per_day: int
    allowed_symbols: list[str]


class SafetyGate:
    """
    Mandatory safety gate for real broker connections.

    Prevents accidental live trading by requiring:
    1. LIVE_MODE=true in environment
    2. Explicit user approval file or interactive confirmation
    3. Daily risk limits configured
    """

    def __init__(
        self,
        require_approval_file: bool = True,
        approval_file_path: Path = Path(".LIVE_TRADING_APPROVED"),
    ):
        self.require_approval_file = require_approval_file
        self.approval_file_path = approval_file_path
        self._approval: SafetyApproval | None = None
        self._daily_trade_count = 0
        self._daily_risk_used = 0.0
        self._session_start = datetime.now().isoformat()

    def check_can_trade(self, symbol: str, risk_amount: float) -> dict[str, Any]:
        """
        Check if real trading is allowed for a specific order.

        Returns dict with allowed=True only if ALL safety checks pass.
        """
        # Check 1: LIVE_MODE environment variable
        live_mode = os.getenv("LIVE_MODE", "false").lower()
        if live_mode not in {"true", "1", "yes"}:
            return {
                "allowed": False,
                "reason": "LIVE_MODE is not enabled in environment",
                "suggestion": "Set LIVE_MODE=true in .env and restart",
            }

        # Check 2: Explicit approval
        if self._approval is None:
            if self.require_approval_file and not self.approval_file_path.exists():
                return {
                    "allowed": False,
                    "reason": f"Approval file not found: {self.approval_file_path}",
                    "suggestion": "Create this file to explicitly approve live trading",
                }
            # Try to load approval
            self._load_approval()
            if self._approval is None or not self._approval.approved:
                return {
                    "allowed": False,
                    "reason": "No valid approval found",
                    "suggestion": "Run safety approval workflow",
                }

        # Check 3: Symbol allowed
        if symbol not in self._approval.allowed_symbols:
            return {
                "allowed": False,
                "reason": f"Symbol {symbol} not in approved list: {self._approval.allowed_symbols}",
            }

        # Check 4: Daily trade limit
        if self._daily_trade_count >= self._approval.max_trades_per_day:
            return {
                "allowed": False,
                "reason": f"Daily trade limit reached ({self._approval.max_trades_per_day})",
            }

        # Check 5: Daily risk limit
        if self._daily_risk_used + risk_amount > self._approval.max_risk_per_day:
            return {
                "allowed": False,
                "reason": f"Daily risk limit would be exceeded ({self._daily_risk_used:.2f} + {risk_amount:.2f} > {self._approval.max_risk_per_day:.2f})",
            }

        return {"allowed": True, "reason": "All safety checks passed"}

    def record_trade_attempt(self, symbol: str, side: str, units: float, risk: float, allowed: bool, reason: str) -> None:
        """Log a trade attempt for audit purposes."""
        SAFETY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "units": units,
            "risk": risk,
            "allowed": allowed,
            "reason": reason,
            "session_hash": self._session_hash(),
        }
        with open(SAFETY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def register_executed_trade(self, risk_amount: float) -> None:
        """Register an executed trade for daily limits."""
        self._daily_trade_count += 1
        self._daily_risk_used += risk_amount

    def _load_approval(self) -> None:
        """Load approval from file or environment."""
        if not self.approval_file_path.exists():
            return

        try:
            with open(self.approval_file_path, "r") as f:
                data = json.load(f)
            self._approval = SafetyApproval(**data)
        except (json.JSONDecodeError, TypeError):
            self._approval = None

    def _session_hash(self) -> str:
        """Generate a hash for this session."""
        content = f"{self._session_start}:{os.getenv('LIVE_MODE')}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def generate_approval_file(
        user: str,
        max_risk_per_day: float = 100.0,
        max_trades_per_day: int = 5,
        allowed_symbols: list[str] | None = None,
        path: Path = Path(".LIVE_TRADING_APPROVED"),
    ) -> Path:
        """
        Generate an approval file for live trading.

        This should be called interactively with user confirmation.
        """
        if allowed_symbols is None:
            allowed_symbols = ["XAUUSD"]

        approval = SafetyApproval(
            approved=True,
            timestamp=datetime.now().isoformat(),
            user=user,
            reason="Explicit manual approval for live trading",
            session_hash="",
            max_risk_per_day=max_risk_per_day,
            max_trades_per_day=max_trades_per_day,
            allowed_symbols=allowed_symbols,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "approved": approval.approved,
                "timestamp": approval.timestamp,
                "user": approval.user,
                "reason": approval.reason,
                "session_hash": approval.session_hash,
                "max_risk_per_day": approval.max_risk_per_day,
                "max_trades_per_day": approval.max_trades_per_day,
                "allowed_symbols": approval.allowed_symbols,
            }, f, indent=2)

        return path
