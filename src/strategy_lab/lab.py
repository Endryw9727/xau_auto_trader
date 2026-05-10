"""
Strategy Lab runner.

The lab compares multiple research strategies on the same OHLCV dataset and
exports a CSV comparison. It does not perform live trading.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
import time

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v1, strategy_v2, strategy_v3, strategy_v4, strategy_v5, strategy_v6


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
    risk_per_trade: float | None = None
    min_risk_reward: float | None = None
    allowed_sessions: list[str] | None = None


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
        StrategySpec(
            name=strategy_v4.STRATEGY_NAME,
            version="strategy_v4",
            signal_generator=strategy_v4.generate_signal,
            description="Strict Off Session MTF momentum pullback research variant.",
            risk_per_trade=strategy_v4.REQUIRED_RISK_PER_TRADE,
            min_risk_reward=strategy_v4.REQUIRED_MIN_RISK_REWARD,
            allowed_sessions=strategy_v4.REQUIRED_ALLOWED_SESSIONS,
        ),
        StrategySpec(
            name=strategy_v5.STRATEGY_NAME,
            version="strategy_v5",
            signal_generator=strategy_v5.generate_signal,
            description="MTF momentum pullback filtered by FeatureEngine regimes.",
        ),
        StrategySpec(
            name=strategy_v6.STRATEGY_NAME,
            version="strategy_v6",
            signal_generator=strategy_v6.generate_signal,
            description="Relaxed Off Session + Asia feature-filtered candidate from controlled sweep.",
            risk_per_trade=strategy_v6.REQUIRED_RISK_PER_TRADE,
            min_risk_reward=strategy_v6.REQUIRED_MIN_RISK_REWARD,
            allowed_sessions=strategy_v6.REQUIRED_ALLOWED_SESSIONS,
        ),
    ]


def run_strategy_lab(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    strategies: list[StrategySpec] | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    show_progress: bool = False,
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
    started_at = time.perf_counter()

    for spec in strategies:
        strategy_started_at = time.perf_counter()
        if show_progress:
            print(f"Running strategy: {spec.name}")

        strategy_backtest_config = _apply_strategy_overrides(backtest_config, spec)
        result = run_backtest(
            df=df,
            strategy_config=strategy_config,
            backtest_config=strategy_backtest_config,
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
                "risk_per_trade": strategy_backtest_config.risk_per_trade,
                "min_risk_reward": strategy_backtest_config.min_risk_reward,
                "allowed_sessions": _format_allowed_sessions(strategy_backtest_config.allowed_sessions),
                "final_balance": result.final_balance,
                **metrics,
            }
        )

        if show_progress:
            elapsed = time.perf_counter() - strategy_started_at
            print(f"Completed strategy: {spec.name} in {elapsed:.2f}s")

    comparison = pd.DataFrame(comparison_rows)
    report_path = export_strategy_comparison_report(comparison, output_dir)

    if show_progress:
        elapsed = time.perf_counter() - started_at
        print(f"Strategy Lab total time: {elapsed:.2f}s")

    return StrategyLabResult(
        comparison=comparison,
        results=results,
        report_path=report_path,
    )


def _apply_strategy_overrides(config: BacktestConfig, spec: StrategySpec) -> BacktestConfig:
    """Apply per-strategy research constraints without mutating the base config."""
    updates = {}

    if spec.risk_per_trade is not None:
        updates["risk_per_trade"] = spec.risk_per_trade

    if spec.min_risk_reward is not None:
        updates["min_risk_reward"] = spec.min_risk_reward

    if spec.allowed_sessions is not None:
        updates["allowed_sessions"] = spec.allowed_sessions

    if not updates:
        return config

    return replace(config, **updates)


def _format_allowed_sessions(allowed_sessions: list[str] | None) -> str:
    """Format allowed sessions for the comparison CSV."""
    if allowed_sessions is None:
        return "All"

    return ", ".join(allowed_sessions)


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
