"""
Monte Carlo reshuffling for final V50 strategy candidates.

The simulation reshuffles already simulated backtest trades. It is
research-only and does not execute trades.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting.backtester import BacktestConfig, run_backtest
from src.backtesting.metrics import calculate_max_drawdown, metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab.v50_stress_test import FINAL_CANDIDATE_GENERATORS


DEFAULT_V50_MONTE_CARLO_PATH = Path("reports/strategy_lab/v50_monte_carlo.csv")
MONTE_CARLO_COLUMNS = [
    "strategy_name",
    "iterations",
    "total_trades",
    "base_net_profit",
    "base_profit_factor",
    "base_max_drawdown",
    "median_final_profit",
    "median_max_drawdown",
    "worst_5pct_drawdown",
    "worst_drawdown",
    "probability_of_loss",
    "probability_drawdown_over_20_percent",
]


def run_v50_monte_carlo(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    iterations: int = 500,
    seed: int = 42,
    output_path: str | Path = DEFAULT_V50_MONTE_CARLO_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run Monte Carlo reshuffling for final V50 candidates and export a CSV."""
    if iterations <= 0:
        raise ValueError("iterations must be positive")

    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    rows = []
    for offset, (strategy_name, signal_generator) in enumerate(FINAL_CANDIDATE_GENERATORS.items()):
        if show_progress:
            print(f"Running Monte Carlo candidate: {strategy_name}")

        result = run_backtest(
            df=df,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
            save_signals=False,
            save_trades_to_db=False,
            save_signals_to_db=False,
            signal_generator=signal_generator,
            strategy_name=strategy_name,
        )
        pnl = pd.to_numeric(result.trades.get("profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        rows.append(
            monte_carlo_summary_row(
                strategy_name=strategy_name,
                pnl=pnl.to_numpy(dtype=float),
                base_metrics=metrics_to_dict(result.metrics),
                initial_balance=backtest_config.initial_balance,
                iterations=iterations,
                seed=seed + offset,
            )
        )

    report = pd.DataFrame(rows, columns=MONTE_CARLO_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def monte_carlo_summary_row(
    strategy_name: str,
    pnl: np.ndarray,
    base_metrics: dict,
    initial_balance: float,
    iterations: int = 500,
    seed: int = 42,
) -> dict:
    """Build one Monte Carlo summary row from a P&L array."""
    final_profits, drawdowns = simulate_trade_reshuffles(
        pnl=pnl,
        initial_balance=initial_balance,
        iterations=iterations,
        seed=seed,
    )
    drawdown_threshold = initial_balance * 0.20

    return {
        "strategy_name": strategy_name,
        "iterations": iterations,
        "total_trades": int(len(pnl)),
        "base_net_profit": float(base_metrics.get("net_profit", 0.0)),
        "base_profit_factor": float(base_metrics.get("profit_factor", 0.0)),
        "base_max_drawdown": float(base_metrics.get("max_drawdown", 0.0)),
        "median_final_profit": _percentile(final_profits, 50),
        "median_max_drawdown": _percentile(drawdowns, 50),
        "worst_5pct_drawdown": _percentile(drawdowns, 95),
        "worst_drawdown": float(drawdowns.max()) if len(drawdowns) else 0.0,
        "probability_of_loss": float((final_profits < 0).mean() * 100.0) if len(final_profits) else 0.0,
        "probability_drawdown_over_20_percent": (
            float((drawdowns > drawdown_threshold).mean() * 100.0) if len(drawdowns) else 0.0
        ),
    }


def simulate_trade_reshuffles(
    pnl: np.ndarray,
    initial_balance: float,
    iterations: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return final profit and max drawdown arrays from shuffled trade order."""
    if len(pnl) == 0:
        return np.zeros(iterations), np.zeros(iterations)

    rng = np.random.default_rng(seed)
    final_profits = np.zeros(iterations)
    drawdowns = np.zeros(iterations)

    for index in range(iterations):
        shuffled = rng.permutation(pnl)
        equity_curve = pd.Series(initial_balance + shuffled.cumsum())
        final_profits[index] = float(shuffled.sum())
        drawdowns[index] = calculate_max_drawdown(equity_curve)

    return final_profits, drawdowns


def _percentile(values: np.ndarray, percentile: float) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.percentile(values, percentile))
