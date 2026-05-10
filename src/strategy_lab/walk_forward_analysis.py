"""
Walk-forward period analysis for selected Strategy Lab strategies.

This module is research/backtest only. It runs configured strategies on
calendar periods and exports per-period robustness diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import BacktestMetrics, metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.lab import StrategySpec, get_default_strategy_specs


WALK_FORWARD_REPORT_PATH = Path("reports/strategy_lab/walk_forward_analysis.csv")
PERIOD_CHOICES = ("yearly", "half", "quarter", "month")
WALK_FORWARD_COLUMNS = [
    "strategy_name",
    "period_start",
    "period_end",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "average_trade",
    "max_consecutive_losses",
]
WALK_FORWARD_SUMMARY_COLUMNS = [
    "strategy_name",
    "total_periods",
    "positive_periods",
    "negative_periods",
    "average_profit_factor",
    "total_net_profit",
    "worst_period_net_profit",
    "worst_period_drawdown",
]


@dataclass(frozen=True)
class PeriodSlice:
    """A calendar period and its market data."""

    period_start: pd.Timestamp
    period_end: pd.Timestamp
    data: pd.DataFrame


def get_walk_forward_strategy_specs() -> list[StrategySpec]:
    """Return all Strategy Lab strategies for walk-forward analysis."""
    specs = []

    for spec in get_default_strategy_specs():
        if spec.name == strategy_v50_pine.MTF_STRATEGY_NAME:
            specs.append(replace(spec, signal_generator=_without_prepare_backtest_data(spec.signal_generator)))
        else:
            specs.append(spec)

    return specs


def split_into_periods(df: pd.DataFrame, period: str) -> list[PeriodSlice]:
    """Split a datetime-indexed DataFrame into yearly, half-yearly, quarterly, or monthly slices."""
    if period not in PERIOD_CHOICES:
        raise ValueError(f"period must be one of: {', '.join(PERIOD_CHOICES)}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")

    if df.empty:
        return []

    sorted_df = df.sort_index()
    keys = pd.Series(_period_keys(sorted_df.index, period), index=sorted_df.index)
    slices: list[PeriodSlice] = []

    for _, period_df in sorted_df.groupby(keys, sort=True):
        if period_df.empty:
            continue

        slices.append(
            PeriodSlice(
                period_start=pd.Timestamp(period_df.index.min()),
                period_end=pd.Timestamp(period_df.index.max()),
                data=period_df.copy(),
            )
        )

    return slices


def run_walk_forward_analysis(
    df: pd.DataFrame,
    period: str,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    strategies: list[StrategySpec] | None = None,
    strategy_datasets: dict[str, pd.DataFrame] | None = None,
    output_path: str | Path = WALK_FORWARD_REPORT_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run selected strategies across calendar periods and export a CSV report."""
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if strategies is None:
        strategies = get_walk_forward_strategy_specs()

    base_df = _ensure_datetime_index(df)
    period_slices = split_into_periods(base_df, period)
    strategy_datasets = {
        strategy_name: _ensure_datetime_index(dataset)
        for strategy_name, dataset in (strategy_datasets or {}).items()
    }
    rows = []

    for period_slice in period_slices:
        if show_progress:
            print(f"Period {period_slice.period_start.date()} -> {period_slice.period_end.date()}")

        for spec in strategies:
            if show_progress:
                print(f"  Running {spec.name}")

            result = _run_period_strategy(
                _get_period_data_for_strategy(period_slice, spec, strategy_datasets),
                strategy_config,
                backtest_config,
                spec,
            )
            rows.append(_result_row(spec.name, period_slice, result.metrics))

    analysis = pd.DataFrame(rows, columns=WALK_FORWARD_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(output_path, index=False)

    return analysis


def summarize_walk_forward_results(analysis: pd.DataFrame) -> pd.DataFrame:
    """Summarize period-analysis results by strategy."""
    if analysis.empty:
        return pd.DataFrame(columns=WALK_FORWARD_SUMMARY_COLUMNS)

    rows = []
    for strategy_name, group in analysis.groupby("strategy_name", sort=True):
        rows.append(
            {
                "strategy_name": strategy_name,
                "total_periods": len(group),
                "positive_periods": int((group["net_profit"] > 0).sum()),
                "negative_periods": int((group["net_profit"] < 0).sum()),
                "average_profit_factor": float(group["profit_factor"].mean()),
                "total_net_profit": float(group["net_profit"].sum()),
                "worst_period_net_profit": float(group["net_profit"].min()),
                "worst_period_drawdown": float(group["max_drawdown"].max()),
            }
        )

    return pd.DataFrame(rows, columns=WALK_FORWARD_SUMMARY_COLUMNS)


def _run_period_strategy(
    df: pd.DataFrame,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
    spec: StrategySpec,
) -> BacktestResult:
    period_backtest_config = _apply_strategy_overrides(backtest_config, spec)

    if len(df) <= period_backtest_config.warmup_candles:
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics=_empty_metrics(),
            final_balance=period_backtest_config.initial_balance,
        )

    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=period_backtest_config,
        save_signals=False,
        signal_generator=spec.signal_generator,
        strategy_name=spec.name,
    )


def _result_row(strategy_name: str, period_slice: PeriodSlice, metrics: BacktestMetrics) -> dict:
    metrics_dict = metrics_to_dict(metrics)

    return {
        "strategy_name": strategy_name,
        "period_start": period_slice.period_start,
        "period_end": period_slice.period_end,
        "total_trades": metrics_dict["total_trades"],
        "wins": metrics_dict["wins"],
        "losses": metrics_dict["losses"],
        "win_rate": metrics_dict["win_rate"],
        "profit_factor": metrics_dict["profit_factor"],
        "net_profit": metrics_dict["net_profit"],
        "max_drawdown": metrics_dict["max_drawdown"],
        "expectancy": metrics_dict["expectancy"],
        "average_trade": metrics_dict["expectancy"],
        "max_consecutive_losses": metrics_dict["max_consecutive_losses"],
    }


def _apply_strategy_overrides(config: BacktestConfig, spec: StrategySpec) -> BacktestConfig:
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


def _get_period_data_for_strategy(
    period_slice: PeriodSlice,
    spec: StrategySpec,
    strategy_datasets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    strategy_data = strategy_datasets.get(spec.name)
    if strategy_data is None:
        return period_slice.data

    return strategy_data.loc[
        (strategy_data.index >= period_slice.period_start)
        & (strategy_data.index <= period_slice.period_end)
    ].copy()


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.sort_index()

    if "time" in df.columns:
        result = df.copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        result = result.dropna(subset=["time"])
        result = result.set_index("time", drop=False)
        return result.sort_index()

    raise ValueError("DataFrame must have a DatetimeIndex or a time column")


def _without_prepare_backtest_data(signal_generator):
    def _signal_generator(df: pd.DataFrame, config: StrategyConfig | None = None):
        return signal_generator(df, config)

    required_history = getattr(signal_generator, "required_history_candles", None)
    if required_history is not None:
        _signal_generator.required_history_candles = required_history

    return _signal_generator


def _period_keys(index: pd.DatetimeIndex, period: str) -> list[tuple[int, int]]:
    if period == "yearly":
        return [(timestamp.year, 1) for timestamp in index]

    if period == "half":
        return [
            (timestamp.year, 1 if timestamp.month <= 6 else 2)
            for timestamp in index
        ]

    if period == "quarter":
        return [(timestamp.year, timestamp.quarter) for timestamp in index]

    return [(timestamp.year, timestamp.month) for timestamp in index]


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
