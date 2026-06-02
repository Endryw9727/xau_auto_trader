"""
Telegram notifier for XAU Auto Trader.

Sends notifications about:
- New trade signals
- AI reasoning results
- Macro regime changes
- Risk warnings
- Daily P&L summary

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
Does NOT execute trades — only sends notifications.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

@dataclass(frozen=True)
class TelegramConfig:
    """Telegram bot configuration."""

    enabled: bool
    bot_token: str
    chat_id: str
    notify_signals: bool = True
    notify_ai_reasoning: bool = True
    notify_macro_changes: bool = True
    notify_risk_warnings: bool = True
    notify_daily_summary: bool = True


def load_telegram_config() -> TelegramConfig:
    """Load Telegram config from environment variables."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    enabled = bool(token and chat_id)

    return TelegramConfig(
        enabled=enabled,
        bot_token=token,
        chat_id=chat_id,
        notify_signals=_get_bool_env("TELEGRAM_NOTIFY_SIGNALS", True),
        notify_ai_reasoning=_get_bool_env("TELEGRAM_NOTIFY_AI", True),
        notify_macro_changes=_get_bool_env("TELEGRAM_NOTIFY_MACRO", True),
        notify_risk_warnings=_get_bool_env("TELEGRAM_NOTIFY_RISK", True),
        notify_daily_summary=_get_bool_env("TELEGRAM_NOTIFY_DAILY", True),
    )


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"true", "1", "yes", "y", "on"}


class TelegramNotifier:
    """Telegram notification sender."""

    def __init__(self, config: TelegramConfig | None = None):
        self.config = config or load_telegram_config()

    def send_message(self, message: str, parse_mode: str = "HTML") -> dict:
        """Send a message to Telegram."""
        if not self.config.enabled:
            return {"sent": False, "reason": "Telegram not configured"}

        url = TELEGRAM_API_URL.format(token=self.config.bot_token)
        payload = {
            "chat_id": self.config.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return {"sent": True, "message_id": response.json().get("result", {}).get("message_id")}
        except Exception as e:
            return {"sent": False, "reason": str(e)}

    def notify_signal(
        self,
        side: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        risk_reward: float,
        smc_score: float = 0.0,
        macro_score: float = 0.0,
        ai_recommendation: str = "",
    ) -> dict:
        """Notify about a new trade signal."""
        if not self.config.notify_signals:
            return {"sent": False, "reason": "Signal notifications disabled"}

        emoji = "🟢" if side == "BUY" else "🔴"
        message = f"""<b>{emoji} XAU/USD SIGNAL: {side}</b>

📊 <b>Entry:</b> {entry:.2f}
🛑 <b>Stop:</b> {stop_loss:.2f}
🎯 <b>Target:</b> {take_profit:.2f}
📈 <b>R:R:</b> 1:{risk_reward:.2f}

🏗️ <b>SMC Score:</b> {smc_score:.2f}
🌍 <b>Macro Score:</b> {macro_score:+.2f}
🤖 <b>AI Rec:</b> {ai_recommendation}

⚠️ <i>This is a research signal. Not financial advice.</i>
"""
        return self.send_message(message)

    def notify_ai_reasoning(
        self,
        score: float,
        confidence: float,
        recommendation: str,
        warnings: list[str],
    ) -> dict:
        """Notify about AI reasoning result."""
        if not self.config.notify_ai_reasoning:
            return {"sent": False, "reason": "AI notifications disabled"}

        emoji = "✅" if recommendation.startswith("STRONG") else ("⚠️" if recommendation.startswith("WEAK") else "🚫")
        warning_text = "\n".join(f"• {w}" for w in warnings[:5]) if warnings else "None"

        message = f"""<b>{emoji} AI REASONING UPDATE</b>

🎯 <b>Score:</b> {score:.2f}/1.00
📊 <b>Confidence:</b> {confidence:.0%}
💡 <b>Recommendation:</b> {recommendation}

⚠️ <b>Warnings:</b>
{warning_text}
"""
        return self.send_message(message)

    def notify_macro_change(
        self,
        old_regime: str,
        new_regime: str,
        macro_score: float,
        explanation: str,
    ) -> dict:
        """Notify about macro regime change."""
        if not self.config.notify_macro_changes:
            return {"sent": False, "reason": "Macro notifications disabled"}

        message = f"""<b>🌍 MACRO REGIME CHANGE</b>

{old_regime} → <b>{new_regime}</b>
📊 <b>Score:</b> {macro_score:+.2f}

{explanation}
"""
        return self.send_message(message)

    def notify_risk_warning(
        self,
        level: str,
        message: str,
        balance: float,
        daily_loss: float,
    ) -> dict:
        """Notify about risk warning."""
        if not self.config.notify_risk_warnings:
            return {"sent": False, "reason": "Risk notifications disabled"}

        emoji = "🔴" if level == "CRITICAL" else "🟡"
        message_text = f"""<b>{emoji} RISK WARNING: {level}</b>

{message}

💰 <b>Balance:</b> {balance:.2f}
📉 <b>Daily Loss:</b> {daily_loss:.2f}
"""
        return self.send_message(message_text)

    def notify_daily_summary(
        self,
        trades_today: int,
        wins: int,
        losses: int,
        pnl: float,
        balance: float,
    ) -> dict:
        """Send daily P&L summary."""
        if not self.config.notify_daily_summary:
            return {"sent": False, "reason": "Daily summary disabled"}

        emoji = "🟢" if pnl >= 0 else "🔴"
        message = f"""<b>{emoji} DAILY SUMMARY</b>

📊 <b>Trades:</b> {trades_today}
✅ <b>Wins:</b> {wins}
❌ <b>Losses:</b> {losses}
💰 <b>P&L:</b> {pnl:+.2f}
🏦 <b>Balance:</b> {balance:.2f}
"""
        return self.send_message(message)
