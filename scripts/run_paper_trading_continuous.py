"""
Continuous paper trading daemon with real-time data feed.

Usage:
    python scripts/run_paper_trading_continuous.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

from src.data_feed.market_data import load_csv_data
from src.data_feed.websocket_client import WebSocketDataFeed
from src.paper.paper_trading_v2 import PaperTradingEngineV2
from src.settings import load_settings
from src.telegram.telegram_notifier import TelegramNotifier

CYCLE_INTERVAL_SECONDS = int(os.getenv("PAPER_CYCLE_INTERVAL", "60"))
DATA_PATH = Path("data/raw/xauusd.csv")


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — Continuous Paper Trading Daemon")
    print("=" * 70)
    print(f"Cycle interval: {CYCLE_INTERVAL_SECONDS} seconds")
    print()

    settings = load_settings()
    engine = PaperTradingEngineV2(settings)
    notifier = TelegramNotifier()

    # Start real-time data feed
    print("📡 Starting real-time data feed...")
    feed = WebSocketDataFeed(
        provider="yahoo_fallback",
        symbols=[settings.trading.symbol],
        poll_interval=5.0,
    )
    feed.start()

    print("🤖 Paper trading engine ready.")
    print("   Press Ctrl+C to stop")
    print()

    try:
        while True:
            try:
                timestamp = pd.Timestamp.now()
                print(f"[{timestamp}] Running trading cycle...")

                # Load latest data
                if DATA_PATH.exists():
                    df = load_csv_data(DATA_PATH)
                else:
                    print("   ⚠️  No data available. Skipping...")
                    time.sleep(CYCLE_INTERVAL_SECONDS)
                    continue

                # Run cycle
                result = engine.run_cycle(df=df)

                # Notify if trade executed
                if result.get("action") == "PAPER_TRADE_EXECUTED":
                    print(f"   ✅ Trade executed: {result['side']} @ {result['entry']:.2f}")
                    notifier.notify_signal(
                        side=result["side"],
                        entry=result["entry"],
                        stop_loss=result["stop_loss"],
                        take_profit=result["take_profit"],
                        risk_reward=result.get("risk_reward", 2.0),
                        smc_score=result.get("smc_score", 0.0),
                        macro_score=result.get("macro_score", 0.0),
                        ai_recommendation=result.get("ai_recommendation", ""),
                    )
                elif result.get("action", "").startswith("BLOCKED"):
                    print(f"   🚫 Trade blocked: {result.get('reason', 'Unknown')}")
                elif "error" in result:
                    print(f"   ❌ Error: {result['error']}")
                else:
                    print(f"   ℹ️  {result.get('action', 'No action')}")

                # Print stats
                stats = engine.get_stats()
                print(f"   Balance: {stats['balance']:.2f} | Open: {stats['open_trades']} | Total: {stats['total_trades']}")

            except Exception as e:
                print(f"   ❌ Cycle error: {e}")

            print()
            time.sleep(CYCLE_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n🛑 Stopping paper trading daemon...")
        feed.stop()
        engine.export_trades()
        sys.exit(0)


if __name__ == "__main__":
    main()
