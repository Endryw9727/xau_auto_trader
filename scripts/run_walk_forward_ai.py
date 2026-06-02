"""
Run Walk-Forward Analysis with AI-driven strategy selection.

Usage:
    python scripts/run_walk_forward_ai.py
"""

from __future__ import annotations

from pathlib import Path

from src.data_feed.market_data import load_csv_data
from src.lab.walk_forward_ai import export_walk_forward_report, run_walk_forward_analysis

CSV_PATH = Path("data/raw/xauusd.csv")


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — Walk-Forward Analysis with AI Selection")
    print("=" * 70)
    print()

    if not CSV_PATH.exists():
        print(f"❌ CSV not found: {CSV_PATH}")
        return

    print(f"📁 Loading: {CSV_PATH}")
    df = load_csv_data(CSV_PATH)
    print(f"   Candles: {len(df)}")
    print()

    print("📊 Running walk-forward analysis...")
    print("   This may take a few minutes depending on data size...")
    print()

    results = run_walk_forward_analysis(
        df=df,
        window_size=1000,
        step_size=500,
    )

    if not results:
        print("❌ No results generated")
        return

    print(f"✅ Completed {len(results)} windows")
    print()

    # Summary by regime
    from collections import defaultdict
    regime_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "profit": 0.0})

    for r in results:
        regime_stats[r.regime]["trades"] += r.trades
        regime_stats[r.regime]["profit"] += r.net_profit

    print("=" * 70)
    print("RESULTS BY REGIME")
    print("=" * 70)
    for regime, stats in regime_stats.items():
        print(f"\n{regime}:")
        print(f"   Trades: {stats['trades']}")
        print(f"   Net Profit: {stats['profit']:+.2f}")

    # Export
    raw_path, summary_path = export_walk_forward_report(results)
    print("\n📁 Reports exported:")
    print(f"   {raw_path}")
    print(f"   {summary_path}")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
