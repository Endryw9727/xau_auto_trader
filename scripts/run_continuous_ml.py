"""
Continuous ML training daemon.

Runs indefinitely, checking for retraining triggers every N minutes.

Usage:
    python scripts/run_continuous_ml.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

from src.data_feed.market_data import load_csv_data
from src.journal.trade_journal import get_all_trades
from src.ml.continuous_trainer import ContinuousTrainer
from src.settings import load_settings

CHECK_INTERVAL_MINUTES = int(os.getenv("ML_CHECK_INTERVAL_MINUTES", "30"))
DATA_PATH = Path("data/raw/xauusd.csv")


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — Continuous ML Training Daemon")
    print("=" * 70)
    print(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
    print()

    settings = load_settings()
    trainer = ContinuousTrainer(
        retrain_threshold=50,
        performance_drop_threshold=0.15,
        regime_shift_threshold=0.30,
        model_type="auto",
    )

    print("🧠 ML Trainer initialized. Waiting for training triggers...")
    print("   Press Ctrl+C to stop")
    print()

    try:
        while True:
            try:
                # Load trade history
                trades = get_all_trades(mode="paper")
                if trades.empty:
                    trades = get_all_trades(mode="backtest")

                if trades.empty:
                    print(f"[{pd.Timestamp.now()}] No trade history found. Skipping...")
                    time.sleep(CHECK_INTERVAL_MINUTES * 60)
                    continue

                # Load market data for regime detection
                market_df = None
                if DATA_PATH.exists():
                    market_df = load_csv_data(DATA_PATH)

                print(f"[{pd.Timestamp.now()}] Checking retraining triggers...")
                print(f"   Trades in history: {len(trades)}")

                result = trainer.check_and_retrain(trades, market_df)

                if result.get("retrained"):
                    print(f"   ✅ Model retrained!")
                    print(f"   Version: {result.get('version')}")
                    print(f"   Accuracy: {result.get('accuracy', 0):.1%}")
                    print(f"   Model path: {result.get('model_path')}")
                else:
                    print(f"   ℹ️  {result.get('reason', 'No retraining needed')}")

                # Print drift status
                drift = trainer.get_drift_status()
                if drift.get("status") == "ok":
                    print(f"   Drift: {drift.get('accuracy_trend', 'unknown')}")

            except Exception as e:
                print(f"   ❌ Error: {e}")

            print()
            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    except KeyboardInterrupt:
        print("\n🛑 Stopping ML training daemon...")
        sys.exit(0)


if __name__ == "__main__":
    main()
