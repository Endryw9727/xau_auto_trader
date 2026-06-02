"""
Test Telegram notifications.

Usage:
    python scripts/test_telegram.py

Requires in .env:
    TELEGRAM_BOT_TOKEN=your_token
    TELEGRAM_CHAT_ID=your_chat_id
"""

from __future__ import annotations

from src.telegram.telegram_notifier import TelegramNotifier, load_telegram_config


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — Telegram Test")
    print("=" * 70)
    print()

    config = load_telegram_config()
    print(f"Enabled: {config.enabled}")
    print(f"Bot token: {'✓ Set' if config.bot_token else '✗ Missing'}")
    print(f"Chat ID: {'✓ Set' if config.chat_id else '✗ Missing'}")
    print()

    if not config.enabled:
        print("❌ Telegram not configured. Add to .env:")
        print("   TELEGRAM_BOT_TOKEN=your_bot_token")
        print("   TELEGRAM_CHAT_ID=your_chat_id")
        return

    notifier = TelegramNotifier(config)

    print("📨 Sending test messages...")
    print()

    # Test signal
    result = notifier.notify_signal(
        side="BUY",
        entry=2350.50,
        stop_loss=2340.00,
        take_profit=2375.00,
        risk_reward=2.5,
        smc_score=0.7,
        macro_score=0.3,
        ai_recommendation="STRONG_BUY",
    )
    print(f"Signal: {'✅ Sent' if result.get('sent') else '❌ Failed'} {result.get('reason', '')}")

    # Test AI reasoning
    result = notifier.notify_ai_reasoning(
        score=0.82,
        confidence=0.85,
        recommendation="STRONG_BUY",
        warnings=["Low ADX on M5", "Asia session"],
    )
    print(f"AI: {'✅ Sent' if result.get('sent') else '❌ Failed'} {result.get('reason', '')}")

    # Test macro
    result = notifier.notify_macro_change(
        old_regime="NEUTRAL",
        new_regime="BULLISH",
        macro_score=0.55,
        explanation="DXY breaking down, VIX elevated",
    )
    print(f"Macro: {'✅ Sent' if result.get('sent') else '❌ Failed'} {result.get('reason', '')}")

    # Test risk
    result = notifier.notify_risk_warning(
        level="WARNING",
        message="Consecutive losses: 2",
        balance=950.00,
        daily_loss=50.00,
    )
    print(f"Risk: {'✅ Sent' if result.get('sent') else '❌ Failed'} {result.get('reason', '')}")

    # Test daily
    result = notifier.notify_daily_summary(
        trades_today=3,
        wins=2,
        losses=1,
        pnl=25.50,
        balance=1025.50,
    )
    print(f"Daily: {'✅ Sent' if result.get('sent') else '❌ Failed'} {result.get('reason', '')}")

    print()
    print("=" * 70)
    print("Test complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
