"""
Run MTF Momentum Pullback parameter sweep.

This is research/backtesting only.
No broker.
No API keys.
No live trading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.backtester import BacktestConfig, run_backtest
from src.data_feed.market_data import load_csv_data


DATA_PATH = Path("data/raw/xauusd.csv")
OUTPUT_PATH = Path("reports/strategy_lab/mtf_sweep.csv")


@dataclass(frozen=True)
class MtfSweepVariant:
    name: str
    allowed_sessions: list[str]
    risk_per_trade: float
    min_risk_reward: float
    warmup_candles: int = 220


def build_variants() -> list[MtfSweepVariant]:
    """Build controlled MTF sweep variants."""
    session_sets = {
        "all_no_london": ["Asia", "New York", "Off Session"],
        "asia_newyork": ["Asia", "New York"],
        "off_newyork": ["Off Session", "New York"],
        "off_only": ["Off Session"],
        "asia_only": ["Asia"],
        "newyork_only": ["New York"],
    }

    risk_values = [0.0025, 0.005]
    rr_values = [2.0, 2.5, 3.0]

    variants: list[MtfSweepVariant] = []

    for session_name, sessions in session_sets.items():
        for risk in risk_values:
            for rr in rr_values:
                variants.append(
                    MtfSweepVariant(
                        name=f"mtf_{session_name}_risk{risk}_rr{rr}",
                        allowed_sessions=sessions,
                        risk_per_trade=risk,
                        min_risk_reward=rr,
                    )
                )

    return variants


def run_variant(data: pd.DataFrame, variant: MtfSweepVariant) -> dict:
    """Run one variant."""
    config = BacktestConfig(
        initial_balance=1000.0,
        risk_per_trade=variant.risk_per_trade,
        min_risk_reward=variant.min_risk_reward,
        warmup_candles=variant.warmup_candles,
        allowed_sessions=variant.allowed_sessions,
    )

    result = run_backtest(
        data,
        backtest_config=config,
        save_trades_to_db=False,
        save_signals_to_db=False,
    )

    metrics = result.metrics

    row = {
        "name": variant.name,
        "total_trades": metrics.total_trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "breakeven": metrics.breakeven,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "expectancy": metrics.expectancy,
        "net_profit": metrics.net_profit,
        "final_balance": result.final_balance,
        "max_drawdown": metrics.max_drawdown,
        "allowed_sessions": ", ".join(variant.allowed_sessions),
        "risk_per_trade": variant.risk_per_trade,
        "min_risk_reward": variant.min_risk_reward,
    }

    return row


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing file: {DATA_PATH}")

    print("=" * 80)
    print("XAU Auto Trader - MTF Sweep")
    print("=" * 80)

    data = load_csv_data(DATA_PATH)

    print(f"Loaded candles: {len(data)}")
    print(f"From: {data.index.min()}")
    print(f"To:   {data.index.max()}")
    print("")

    variants = build_variants()
    rows = []

    for index, variant in enumerate(variants, start=1):
        print(f"[{index}/{len(variants)}] Running {variant.name}")
        rows.append(run_variant(data, variant))

    results = pd.DataFrame(rows)

    results = results.sort_values(
        by=["profit_factor", "net_profit"],
        ascending=[False, False],
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT_PATH, index=False)

    print("")
    print("Top MTF Sweep Results")
    print("=" * 80)

    columns = [
        "name",
        "total_trades",
        "win_rate",
        "profit_factor",
        "net_profit",
        "max_drawdown",
        "expectancy",
        "risk_per_trade",
        "min_risk_reward",
        "allowed_sessions",
    ]

    print(results[columns].head(15).to_string(index=False))

    print("")
    print(f"Exported: {OUTPUT_PATH}")
    print("Important: research/backtest only, not live trading.")


if __name__ == "__main__":
    main()
