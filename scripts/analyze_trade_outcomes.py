"""
Analyze backtest trade outcomes against FeatureEngine market features.

Usage:
    python scripts/analyze_trade_outcomes.py

This is research/backtest analysis only. It does not execute live trades.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.trade_outcome_analysis import analyze_trade_outcomes


TRADES_PATH = Path("reports/backtests/trades.csv")
FEATURES_PATH = Path("reports/features/xauusd_features.csv")
OUTPUT_DIR = Path("reports/analysis")

OUTPUT_FILES = {
    "trade_feature_dataset": "trade_feature_dataset.csv",
    "outcome_by_session": "outcome_by_session.csv",
    "outcome_by_trend_regime": "outcome_by_trend_regime.csv",
    "outcome_by_volatility_regime": "outcome_by_volatility_regime.csv",
    "outcome_by_candle_regime": "outcome_by_candle_regime.csv",
    "outcome_by_side": "outcome_by_side.csv",
    "outcome_by_adx_bucket": "outcome_by_adx_bucket.csv",
    "outcome_by_rsi_bucket": "outcome_by_rsi_bucket.csv",
    "outcome_by_williams_r_bucket": "outcome_by_williams_r_bucket.csv",
    "outcome_by_distance_from_ema20_bucket": "outcome_by_distance_from_ema20_bucket.csv",
    "outcome_by_atr_ratio_bucket": "outcome_by_atr_ratio_bucket.csv",
}


def main() -> None:
    """Run trade outcome analysis and export CSV reports."""
    print("=" * 60)
    print("XAU Auto Trader - Trade Outcome Analysis")
    print("=" * 60)

    if not TRADES_PATH.exists():
        print(f"Trades CSV not found: {TRADES_PATH}")
        print("Run this first:")
        print("python -m src.main")
        return

    if not FEATURES_PATH.exists():
        print(f"Features CSV not found: {FEATURES_PATH}")
        print("Run this first:")
        print("python scripts/analyze_features.py")
        return

    trades = pd.read_csv(TRADES_PATH)
    features = pd.read_csv(FEATURES_PATH)

    results = analyze_trade_outcomes(trades, features)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for key, filename in OUTPUT_FILES.items():
        if key in results:
            output_path = OUTPUT_DIR / filename
            results[key].to_csv(output_path, index=False)
            print(f"Exported: {output_path}")

    print("")
    print("Main outcome tables:")
    for key in [
        "outcome_by_session",
        "outcome_by_trend_regime",
        "outcome_by_volatility_regime",
        "outcome_by_candle_regime",
        "outcome_by_adx_bucket",
        "outcome_by_rsi_bucket",
    ]:
        if key in results:
            _print_sorted_table(key, results[key])

    print("")
    print("Important: this is research/backtest analysis only, not live trading.")


def _print_sorted_table(name: str, table: pd.DataFrame) -> None:
    """Print a compact sorted outcome table."""
    print("")
    print(name)

    if table.empty:
        print("No rows")
        return

    sort_columns = [column for column in ["profit_factor", "net_profit"] if column in table.columns]
    sorted_table = table.sort_values(sort_columns, ascending=[False] * len(sort_columns), na_position="last")
    print(sorted_table.to_string(index=False))


if __name__ == "__main__":
    main()
