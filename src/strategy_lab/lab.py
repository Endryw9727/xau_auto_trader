"""
Strategy Lab runner.

The lab compares multiple research strategies on the same OHLCV dataset and
exports a CSV comparison. It does not perform live trading.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v1, strategy_v2, strategy_v3


SignalGenerator = Callable[[pd.DataFrame, StrategyConfig], TradingSignal]
DEFAULT_REPORT_DIR = Path("reports/strategy_lab")
COMPARISON_FILENAME = "strategy_comparison.csv"


@dataclass(frozen=True)
class StrategySpec:
    """Strategy metadata used by the lab."""

    name: str
    version: str
    signal_generator: SignalGenerator
    description: str


@dataclass(frozen=True)
class StrategyLabResult:
    """Strategy Lab output."""

    comparison: pd.DataFrame
    results: dict[str, BacktestResult]
    report_path: Path


def get_default_strategy_specs() -> list[StrategySpec]:
    """Return the initial Strategy Lab strategy set."""
    return [
        StrategySpec(
            name=strategy_v1.STRATEGY_NAME,
            version="strategy_v1",
            signal_generator=strategy_v1.generate_signal,
            description="Current existing strategy baseline.",
        ),
        StrategySpec(
            name=strategy_v2.STRATEGY_NAME,
            version="strategy_v2",
            signal_generator=strategy_v2.generate_signal,
            description="Existing strategy filtered to London and New York sessions.",
        ),
        StrategySpec(
            name=strategy_v3.STRATEGY_NAME,
            version="strategy_v3",
            signal_generator=strategy_v3.generate_signal,
            description="Simple MTF momentum pullback placeholder.",
        ),
    ]


def run_strategy_lab(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    strategies: list[StrategySpec] | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
) -> StrategyLabResult:
    """
    Run all Strategy Lab strategies and export a comparison CSV.

    Signals are not saved to SQLite from the lab, so repeated comparisons do
    not pollute the local journal.
    """
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if strategies is None:
        strategies = get_default_strategy_specs()

    results: dict[str, BacktestResult] = {}
    comparison_rows: list[dict] = []

    for spec in strategies:
        result = run_backtest(
            df=df,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
            save_signals=False,
            signal_generator=spec.signal_generator,
        )

        results[spec.name] = result
        metrics = metrics_to_dict(result.metrics)
        comparison_rows.append(
            {
                "strategy_name": spec.name,
                "strategy_version": spec.version,
                "description": spec.description,
                "final_balance": result.final_balance,
                **metrics,
            }
        )

    comparison = pd.DataFrame(comparison_rows)
    report_path = export_strategy_comparison_report(comparison, output_dir)

    return StrategyLabResult(
        comparison=comparison,
        results=results,
        report_path=report_path,
    )


def export_strategy_comparison_report(
    comparison: pd.DataFrame,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
) -> Path:
    """Export the Strategy Lab comparison CSV."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    report_path = output_path / COMPARISON_FILENAME
    comparison.to_csv(report_path, index=False)

    return report_path
