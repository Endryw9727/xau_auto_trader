"""
Telegram notifier daemon.

Monitors trade database and sends notifications for new trades,
warnings, and daily summaries.

Usage:
    python scripts/run_telegram_notifier.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

from src.journal.trade_journal import get_all_trades
from src.settings import load_settings
from src.telegram.telegram_notifier import TelegramNotifier, load_telegram_config

CHECK_INTERVAL_MINUTES = int(os.getenv("TELEGRAM_CHECK_INTERVAL_MINUTES", "5"))


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — Telegram Notifier Daemon")
    print("=" * 70)

    config = load_telegram_config()
    if not config.enabled:
        print("❌ Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        sys.exit(1)

    notifier = TelegramNotifier(config)
    print(f"✅ Telegram bot connected. Check interval: {CHECK_INTERVAL_MINUTES} min")
    print("   Press Ctrl+C to stop")
    print()

    last_trade_count = 0
    last_summary_date = None

    try:
        while True:
            try:
                trades = get_all_trades()
                current_count = len(trades)

                # Notify new trades
                if current_count > last_trade_count:
                    new_trades = trades.iloc[last_trade_count:]
                    for _, trade in new_trades.iterrows():
                        notifier.notify_signal(
                            side=trade.get("side", "UNKNOWN"),
                            entry=trade.get("entry", 0),
                            stop_loss=trade.get("stop_loss", 0),
                            take_profit=trade.get("take_profit", 0),
                            risk_reward=trade.get("risk_reward", 2.0),
                        )
                    print(f"[{pd.Timestamp.now()}] Notified {len(new_trades)} new trades")

                last_trade_count = current_count

                # Daily summary
                now = pd.Timestamp.now()
                if last_summary_date != now.date() and now.hour == 22:
                    today_trades = trades[pd.to_datetime(trades.get("timestamp", pd.Series())).dt.date == now.date()]
                    if not today_trades.empty:
                        wins = len(today_trades[today_trades.get("outcome", 0) > 0])
                        losses = len(today_trades[today_trades.get("outcome", 0) < 0])
                        pnl = today_trades.get("outcome", pd.Series([0])).sum()
                        balance = trades.iloc[-1].get("balance", 1000) if not trades.empty else 1000

                        notifier.notify_daily_summary(
                            trades_today=len(today_trades),
                            wins=wins,
                            losses=losses,
                            pnl=pnl,
                            balance=balance,
                        )
                        last_summary_date = now.date()
                        print(f"[{now}] Sent daily summary")

            except Exception as e:
                print(f"[{pd.Timestamp.now()}] Error: {e}")

            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    except KeyboardInterrupt:
        print("\n🛑 Stopping Telegram notifier...")
        sys.exit(0)


if __name__ == "__main__":
    main()
