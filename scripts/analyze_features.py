"""
Build and export FeatureEngine output from local XAU/USD CSV data.

Usage:
    python scripts/analyze_features.py

This is research/backtest analysis only. It does not execute live trades.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.features.feature_engine import build_features


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
OUTPUT_PATH = Path("reports/features/xauusd_features.csv")


def main() -> None:
    """Build features from local CSV and export them to reports/features."""
    print("=" * 60)
    print("XAU Auto Trader - Feature Analysis")
    print("=" * 60)

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Create this file first:")
        print("data/raw/xauusd.csv")
        return

    data = load_csv_data(RAW_DATA_PATH)
    features = build_features(data)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(OUTPUT_PATH, index=True)

    print(f"Rows: {len(features)}")
    print(f"Columns: {len(features.columns)}")
    print("")
    print("Feature columns:")
    for column in features.columns:
        print(f"- {column}")

    print("")
    print("NaN counts:")
    nan_counts = features.isna().sum()
    for column, count in nan_counts[nan_counts > 0].items():
        print(f"- {column}: {int(count)}")

    if int(nan_counts.sum()) == 0:
        print("- none")

    print("")
    print(f"Features exported: {OUTPUT_PATH}")
    print("Important: this is research/backtest analysis only, not live trading.")


if __name__ == "__main__":
    main()
