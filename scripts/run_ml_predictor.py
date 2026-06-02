"""
Demo script: Train and test ML trade predictor.

Usage:
    python scripts/run_ml_predictor.py

Requires trade history in reports/backtests/trades.csv
or will use mock data for demonstration.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ml.regime_detector import detect_regime
from src.ml.trade_predictor import TradePredictor
from src.data_feed.market_data import load_csv_data

TRADES_PATH = Path("reports/backtests/trades.csv")
DATA_PATH = Path("data/raw/xauusd.csv")


def generate_mock_trades(n: int = 100) -> pd.DataFrame:
    """Generate mock trade history for demo."""
    import random
    random.seed(42)

    data = []
    for i in range(n):
        side = random.choice(["BUY", "SELL"])
        won = random.random() > 0.45  # 55% win rate
        outcome = random.uniform(5, 25) if won else random.uniform(-25, -5)

        data.append({
            "id": f"trade_{i}",
            "side": side,
            "entry": 2350 + random.uniform(-50, 50),
            "stop_loss": 2340 + random.uniform(-50, 50),
            "take_profit": 2370 + random.uniform(-50, 50),
            "risk_reward": random.uniform(1.5, 3.5),
            "outcome": outcome,
            "outcome_label": "win" if won else "loss",
            "adx_at_entry": random.uniform(15, 35),
            "rsi_at_entry": random.uniform(30, 70),
            "ema_distance_pct": random.uniform(-0.02, 0.02),
            "atr_pct": random.uniform(0.1, 0.5),
            "macro_score": random.uniform(-0.5, 0.5),
            "dxy_correlation": random.uniform(-0.9, -0.3),
            "smc_score": random.uniform(0, 1),
            "fvg_aligned": random.choice([0, 1]),
            "ob_nearby": random.choice([0, 1]),
            "sweep_confirmed": random.choice([0, 1]),
            "session": random.choice(["London", "New York", "Asia", "Off Session"]),
            "trend_aligned": random.choice([0, 1]),
            "structure_bos": random.choice([0, 1]),
        })

    return pd.DataFrame(data)


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — ML Trade Predictor Demo")
    print("=" * 70)
    print()

    # Load or generate trade history
    if TRADES_PATH.exists():
        print(f"📁 Loading trade history: {TRADES_PATH}")
        trades = pd.read_csv(TRADES_PATH)
    else:
        print("📁 No trade history found. Generating mock data for demo...")
        trades = generate_mock_trades(200)
        print(f"   Generated {len(trades)} mock trades")
    print()

    # Train predictor
    print("🧠 Training trade predictor...")
    predictor = TradePredictor(model_type="auto")
    train_result = predictor.train(trades)

    if "error" in train_result:
        print(f"   ❌ Training failed: {train_result['error']}")
        return

    print(f"   Model type: {train_result['model_type']}")
    print(f"   Accuracy: {train_result['accuracy']:.1%}")
    print(f"   Train samples: {train_result['train_samples']}")
    if "feature_importance" in train_result:
        print("   Feature importance:")
        for feat, imp in list(train_result["feature_importance"].items())[:5]:
            print(f"      {feat}: {imp:.3f}")
    print()

    # Predict on a sample setup
    print("🔮 Predicting outcome for sample trade setup...")
    sample_setup = {
        "adx_at_entry": 28.0,
        "rsi_at_entry": 45.0,
        "ema_distance_pct": 0.01,
        "atr_pct": 0.25,
        "risk_reward": 2.5,
        "macro_score": 0.4,
        "dxy_correlation": -0.75,
        "smc_score": 0.6,
        "fvg_aligned": 1,
        "ob_nearby": 1,
        "sweep_confirmed": 1,
        "session": "London",
        "trend_aligned": 1,
        "structure_bos": 1,
    }

    prediction = predictor.predict(sample_setup)
    print(f"   Will win: {'YES' if prediction.will_win else 'NO'}")
    print(f"   Probability: {prediction.probability:.1%}")
    print(f"   Confidence: {prediction.confidence}")
    print(f"   Model: {prediction.model_type}")
    print()

    # Regime detection
    if DATA_PATH.exists():
        print("📊 Detecting market regime...")
        df = load_csv_data(DATA_PATH)
        regime = detect_regime(df)
        print(f"   Regime: {regime.regime}")
        print(f"   ADX: {regime.adx}")
        print(f"   ATR%: {regime.atr_pct}")
        print(f"   Trend: {regime.trend_strength}")
        print(f"   Volatility: {regime.volatility_regime}")
        print(f"   Recommendation: {regime.recommendation}")
    else:
        print("   No market data available for regime detection")

    print()
    print("=" * 70)
    print("Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
