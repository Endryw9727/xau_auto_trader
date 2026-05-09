"""
Strategy Lab utilities.

This module compares multiple backtest configurations on the same dataset.
It does not run live trading.
It does not connect to brokers.
It is only for research/backtesting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, run_backtest


@dataclass(frozen=True)
class StrategyVariant:
    """Single strategy/config variant to test."""

    name: str
    allowed_sessions: list[str]
    risk_per_trade: float
    min_risk_reward: float
    warmup_candles: int = 220


@dataclass(frozen=True)
class StrategyLabResult:
    """Compact result for a strategy variant."""

    name: str
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    profit_factor: float
    expectancy: float
    net_profit: float
    final_balance: float
    max_drawdown: float
    allowed_sessions: str
    risk_per_trade: float
    min_risk_reward: float


def default_strategy_variants() -> list[StrategyVariant]:
    """
    Return default variants to compare.

    These are not optimized parameters.
    They are controlled experiments.
    """
    base_sessions = ["Asia", "New York", "Off Session"]

    return [
        StrategyVariant(
            name="session_filtered_rr2",
            allowed_sessions=base_sessions,
            risk_per_trade=0.005,
            min_risk_reward=2.0,
        ),
        StrategyVariant(
            name="session_filtered_rr25",
            allowed_sessions=base_sessions,
            risk_per_trade=0.005,
            min_risk_reward=2.5,
        ),
        StrategyVariant(
            name="session_filtered_rr3",
            allowed_sessions=base_sessions,
            risk_per_trade=0.005,
            min_risk_reward=3.0,
        ),
        StrategyVariant(
            name="asia_newyork_rr2",
            allowed_sessions=["Asia", "New York"],
            risk_per_trade=0.005,
            min_risk_reward=2.0,
        ),
        StrategyVariant(
            name="offsession_newyork_rr2",
            allowed_sessions=["Off Session", "New York"],
            risk_per_trade=0.005,
            min_risk_reward=2.0,
        ),
        StrategyVariant(
            name="offsession_only_rr2",
            allowed_sessions=["Off Session"],
            risk_per_trade=0.005,
            min_risk_reward=2.0,
        ),
        StrategyVariant(
            name="low_risk_session_filtered_rr2",
            allowed_sessions=base_sessions,
            risk_per_trade=0.0025,
            min_risk_reward=2.0,
        ),
    ]


def run_strategy_variant(
    data: pd.DataFrame,
    variant: StrategyVariant,
    initial_balance: float = 1000.0,
) -> StrategyLabResult:
    """Run a single strategy variant and return compact metrics."""
    config = BacktestConfig(
        initial_balance=initial_balance,
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

    return StrategyLabResult(
        name=variant.name,
        total_trades=metrics.total_trades,
        wins=metrics.wins,
        losses=metrics.losses,
        breakeven=metrics.breakeven,
        win_rate=metrics.win_rate,
        profit_factor=metrics.profit_factor,
        expectancy=metrics.expectancy,
        net_profit=metrics.net_profit,
        final_balance=result.final_balance,
        max_drawdown=metrics.max_drawdown,
        allowed_sessions=", ".join(variant.allowed_sessions),
        risk_per_trade=variant.risk_per_trade,
        min_risk_reward=variant.min_risk_reward,
    )


def run_strategy_lab(
    data: pd.DataFrame,
    variants: list[StrategyVariant] | None = None,
    initial_balance: float = 1000.0,
) -> pd.DataFrame:
    """Run all variants and return a sorted comparison DataFrame."""
    if variants is None:
        variants = default_strategy_variants()

    rows = []

    for variant in variants:
        result = run_strategy_variant(
            data=data,
            variant=variant,
            initial_balance=initial_balance,
        )
        rows.append(asdict(result))

    results = pd.DataFrame(rows)

    if results.empty:
        return results

    return results.sort_values(
        by=["profit_factor", "net_profit"],
        ascending=[False, False],
    )


def export_strategy_lab_results(
    results: pd.DataFrame,
    output_path: str | Path = "reports/strategy_lab/results.csv",
) -> Path:
    """Export strategy lab results to CSV."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output, index=False)
    return output
