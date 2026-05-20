"""Telegram report model for Control Room.

The v1 reporter is safety-first: it does not require tokens and it does not
block the Control Room if Telegram is disabled or not configured.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class ControlRoomTelegramReport:
    """Telegram-ready report payload."""

    title: str
    status: str
    message: str
    severity: str


def build_telegram_report(config: Any, market: dict, account: dict, risk: dict, signals: dict, shadow: dict) -> ControlRoomTelegramReport:
    """Build a concise report payload without sending it."""
    status = risk.get("status", "OK")
    severity = "STOP" if status == "STOP" else "WARNING" if status != "OK" or market.get("status") != "OK" else "INFO"
    message = (
        f"symbol={config.symbol}; market={market.get('status')}; account={account.get('status')}; "
        f"risk={risk.get('status')}; signals={signals.get('total_signals', 0)}; shadow={shadow.get('status')}"
    )
    return ControlRoomTelegramReport(
        title="XAU Control Room",
        status=str(status),
        message=message,
        severity=severity,
    )


def maybe_emit_telegram_report(config: Any, report: ControlRoomTelegramReport) -> dict:
    """Return safe Telegram emission status."""
    if not config.telegram_enabled:
        return {"status": "OK", "reason": "telegram_enabled=false; no Telegram report emitted", "telegram_sent": False}
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"status": "WARNING", "reason": "Telegram enabled but token/chat_id missing", "telegram_sent": False}
    return {
        "status": "WARNING",
        "reason": "Telegram transport is intentionally not active in Control Room v1",
        "telegram_sent": False,
        "title": report.title,
        "severity": report.severity,
    }
