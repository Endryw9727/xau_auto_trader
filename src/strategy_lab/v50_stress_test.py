"""
Stress tests for final V50 strategy candidates.

The module runs backtests and trade-level perturbations only. It does not
execute trades or connect to brokers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import BacktestMetrics, calculate_metrics, metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_candidates, strategy_v50_proxy_candidate


DEFAULT_V50_STRESS_TEST_PATH = Path("reports/strategy_lab/v50_stress_test.csv")
FINAL_CANDIDATE_GENERATORS = {
    strategy_v50_candidates.FINAL_LOW_RISK_STRATEGY_NAME: strategy_v50_candidates.generate_final_low_risk_signal,
    strategy_v50_candidates.FINAL_BALANCED_STRATEGY_NAME: strategy_v50_candidates.generate_final_balanced_signal,
    strategy_v50_candidates.FINAL_GROWTH_STRATEGY_NAME: strategy_v50_candidates.generate_final_growth_signal,
    strategy_v50_proxy_candidate.STRATEGY_NAME: strategy_v50_proxy_candidate.generate_signal,
}
STRESS_TEST_COLUMNS = [
    "strategy_name",
    "scenario",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
]


@dataclass(frozen=True)
class StressScenario:
    """One stress-test scenario."""

    name: str
    slippage_points: float | None = None
    commission_per_trade: float | None = None
    pnl_multiplier: float | None = None
    remove_best_pct: float | None = None


def build_v50_stress_scenarios() -> list[StressScenario]:
    """Return realistic stress scenarios in a stable order."""
    return [
        StressScenario("base"),
        StressScenario("spread_slippage_light", slippage_points=0.05),
        StressScenario("spread_slippage_medium", slippage_points=0.15),
        StressScenario("spread_slippage_heavy", slippage_points=0.30),
        StressScenario("simulated_commission", commission_per_trade=1.0),
        StressScenario("pnl_minus_10pct", pnl_multiplier=0.90),
        StressScenario("pnl_minus_20pct", pnl_multiplier=0.80),
        StressScenario("remove_best_5pct", remove_best_pct=0.05),
        StressScenario("remove_best_10pct", remove_best_pct=0.10),
    ]


def run_v50_stress_test(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_V50_STRESS_TEST_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run stress tests for all final V50 candidates and export a CSV report."""
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    scenarios = build_v50_stress_scenarios()
    rows = []

    for strategy_name, signal_generator in FINAL_CANDIDATE_GENERATORS.items():
        if show_progress:
            print(f"Running final candidate: {strategy_name}")

        base_result = run_v50_candidate_backtest(
            df=df,
            strategy_name=strategy_name,
            signal_generator=signal_generator,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
        )

        for scenario in scenarios:
            if show_progress:
                print(f"  Scenario: {scenario.name}")

            result = _stress_result(
                df=df,
                strategy_name=strategy_name,
                signal_generator=signal_generator,
                strategy_config=strategy_config,
                backtest_config=backtest_config,
                base_result=base_result,
                scenario=scenario,
            )
            rows.append(_stress_row(strategy_name, scenario.name, result.metrics))

    report = pd.DataFrame(rows, columns=STRESS_TEST_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_v50_candidate_backtest(
    df: pd.DataFrame,
    strategy_name: str,
    signal_generator,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one final candidate through the regular backtester."""
    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=signal_generator,
        strategy_name=strategy_name,
    )


def apply_trade_stress(
    result: BacktestResult,
    scenario: StressScenario,
    initial_balance: float,
) -> BacktestResult:
    """Apply a trade-level stress scenario and recalculate metrics."""
    trades = result.trades.copy()

    if scenario.pnl_multiplier is not None:
        trades = _scale_trade_pnl(trades, scenario.pnl_multiplier)

    if scenario.remove_best_pct is not None:
        trades = _remove_best_trades(trades, scenario.remove_best_pct)

    metrics = calculate_metrics(trades, initial_balance) if not trades.empty else _empty_metrics()
    return BacktestResult(
        trades=trades,
        metrics=metrics,
        final_balance=initial_balance + metrics.net_profit,
    )


def _stress_result(
    df: pd.DataFrame,
    strategy_name: str,
    signal_generator: Callable[[pd.DataFrame, StrategyConfig], TradingSignal],
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
    base_result: BacktestResult,
    scenario: StressScenario,
) -> BacktestResult:
    if scenario.slippage_points is not None or scenario.commission_per_trade is not None:
        stressed_config = replace(
            backtest_config,
            slippage_points=(
                scenario.slippage_points
                if scenario.slippage_points is not None
                else backtest_config.slippage_points
            ),
            commission_per_trade=(
                scenario.commission_per_trade
                if scenario.commission_per_trade is not None
                else backtest_config.commission_per_trade
            ),
        )
        return run_v50_candidate_backtest(
            df=df,
            strategy_name=strategy_name,
            signal_generator=signal_generator,
            strategy_config=strategy_config,
            backtest_config=stressed_config,
        )

    return apply_trade_stress(base_result, scenario, backtest_config.initial_balance)


def _stress_row(strategy_name: str, scenario_name: str, metrics: BacktestMetrics) -> dict:
    metrics_dict = metrics_to_dict(metrics)
    max_drawdown = float(metrics_dict["max_drawdown"])
    net_profit = float(metrics_dict["net_profit"])

    return {
        "strategy_name": strategy_name,
        "scenario": scenario_name,
        "total_trades": metrics_dict["total_trades"],
        "wins": metrics_dict["wins"],
        "losses": metrics_dict["losses"],
        "win_rate": metrics_dict["win_rate"],
        "profit_factor": metrics_dict["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics_dict["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics_dict["max_consecutive_losses"],
    }


def _scale_trade_pnl(trades: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    stressed = trades.copy()
    for column in ["pnl", "profit_loss"]:
        if column in stressed.columns:
            stressed[column] = pd.to_numeric(stressed[column], errors="coerce").fillna(0.0) * multiplier
    return stressed


def _remove_best_trades(trades: pd.DataFrame, pct: float) -> pd.DataFrame:
    if trades.empty or "profit_loss" not in trades.columns:
        return trades.copy()

    remove_count = max(1, int(len(trades) * pct))
    pnl = pd.to_numeric(trades["profit_loss"], errors="coerce").fillna(0.0)
    drop_index = pnl.sort_values(ascending=False).head(remove_count).index
    return trades.drop(index=drop_index).sort_index().reset_index(drop=True)


def _empty_metrics() -> BacktestMetrics:
    return BacktestMetrics(
        total_trades=0,
        wins=0,
        losses=0,
        breakeven=0,
        win_rate=0.0,
        net_profit=0.0,
        profit_factor=0.0,
        average_win=0.0,
        average_loss=0.0,
        expectancy=0.0,
        max_drawdown=0.0,
        max_consecutive_wins=0,
        max_consecutive_losses=0,
    )
