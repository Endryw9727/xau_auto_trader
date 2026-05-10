"""
V50 technical edge-filter sweep helpers.

This module builds research-only variants of v50_pine_technical_strategy by
blocking selected signal sides and V50 sessions before the backtester opens a
trade.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import BacktestMetrics, metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.strategy_diagnostics import build_strategy_diagnostics
from src.strategy_lab.v50_edge_filters import (
    V50EdgeFilterVariant,
    make_v50_edge_filter_signal_generator,
)
from src.strategy_lab.walk_forward_analysis import PERIOD_CHOICES, split_into_periods


DEFAULT_V50_EDGE_SWEEP_PATH = Path("reports/strategy_lab/v50_edge_filter_sweep.csv")
DEFAULT_V50_EDGE_WALK_FORWARD_PATH = Path("reports/strategy_lab/v50_edge_filter_sweep_walk_forward.csv")
BASE_STRATEGY_NAME = strategy_v50_pine.STRATEGY_NAME
VARIANT_NAMES = (
    "v50_base",
    "v50_long_only",
    "v50_no_asia_london",
    "v50_london_only",
    "v50_london_and_newyork",
    "v50_long_no_asia_london",
    "v50_long_london_only",
    "v50_short_london_only",
    "v50_long_all_short_london_only",
    "v50_no_short_asia_london",
)
SWEEP_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
]
WALK_FORWARD_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_periods",
    "active_periods",
    "no_trade_periods",
    "positive_periods",
    "negative_periods",
    "average_profit_factor",
    "median_profit_factor",
    "total_net_profit",
    "worst_period_net_profit",
    "worst_period_drawdown",
    "stability_score",
]


def build_v50_edge_filter_variants() -> list[V50EdgeFilterVariant]:
    """Return the required V50 edge-filter variants in a stable order."""
    return [
        V50EdgeFilterVariant("v50_base"),
        V50EdgeFilterVariant("v50_long_only", allowed_sides=("BUY",)),
        V50EdgeFilterVariant("v50_no_asia_london", blocked_sessions=("ASIA/LONDON",)),
        V50EdgeFilterVariant("v50_london_only", allowed_sessions=("LONDON",)),
        V50EdgeFilterVariant("v50_london_and_newyork", allowed_sessions=("LONDON", "NEW YORK")),
        V50EdgeFilterVariant(
            "v50_long_no_asia_london",
            allowed_sides=("BUY",),
            blocked_sessions=("ASIA/LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_long_london_only",
            allowed_sides=("BUY",),
            allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_short_london_only",
            allowed_sides=("SELL",),
            allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_long_all_short_london_only",
            short_allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_no_short_asia_london",
            blocked_side_sessions=(("SELL", "ASIA/LONDON"),),
        ),
    ]

def run_v50_edge_filter_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    variants: list[V50EdgeFilterVariant] | None = None,
    output_path: str | Path = DEFAULT_V50_EDGE_SWEEP_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run V50 edge-filter variants over the supplied OHLCV data."""
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if variants is None:
        variants = build_v50_edge_filter_variants()

    rows = []
    for variant in variants:
        if show_progress:
            print(f"Running variant: {variant.variant_name}")
        result = run_v50_edge_filter_variant(df, variant, strategy_config, backtest_config)
        rows.append(_sweep_row(variant, result))

    report = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_v50_edge_filter_walk_forward(
    df: pd.DataFrame,
    period: str,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    variants: list[V50EdgeFilterVariant] | None = None,
    output_path: str | Path = DEFAULT_V50_EDGE_WALK_FORWARD_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run V50 edge-filter variants by period and export variant summaries."""
    if period not in PERIOD_CHOICES:
        raise ValueError(f"period must be one of: {', '.join(PERIOD_CHOICES)}")

    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if variants is None:
        variants = build_v50_edge_filter_variants()

    period_rows = []
    for period_slice in split_into_periods(_ensure_datetime_index(df), period):
        if show_progress:
            print(f"Period {period_slice.period_start.date()} -> {period_slice.period_end.date()}")

        for variant in variants:
            if show_progress:
                print(f"  Running variant: {variant.variant_name}")

            result = _run_period_variant(period_slice.data, variant, strategy_config, backtest_config)
            period_rows.append(_period_row(variant, period_slice.period_start, period_slice.period_end, result))

    period_report = pd.DataFrame(period_rows)
    summary = _summarize_walk_forward(period_report, variants)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_path, index=False)
    return summary


def run_v50_edge_filter_variant(
    df: pd.DataFrame,
    variant: V50EdgeFilterVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one V50 edge-filter variant through the backtester."""
    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=make_v50_edge_filter_signal_generator(variant),
        strategy_name=variant.variant_name,
    )


def sort_v50_edge_sweep(report: pd.DataFrame) -> pd.DataFrame:
    """Sort sweep results by quality and absolute net result."""
    return report.sort_values(
        ["profit_factor", "net_profit", "max_drawdown"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _run_period_variant(
    df: pd.DataFrame,
    variant: V50EdgeFilterVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    if len(df) <= backtest_config.warmup_candles:
        return BacktestResult(
            trades=pd.DataFrame(),
            metrics=_empty_metrics(),
            final_balance=backtest_config.initial_balance,
        )

    return run_v50_edge_filter_variant(df, variant, strategy_config, backtest_config)


def _sweep_row(variant: V50EdgeFilterVariant, result: BacktestResult) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])

    return {
        "strategy_name": BASE_STRATEGY_NAME,
        "variant_name": variant.variant_name,
        "total_trades": metrics["total_trades"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
    }


def _period_row(
    variant: V50EdgeFilterVariant,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    result: BacktestResult,
) -> dict:
    metrics = metrics_to_dict(result.metrics)
    return {
        "strategy_name": variant.variant_name,
        "period_start": period_start,
        "period_end": period_end,
        "total_trades": metrics["total_trades"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "net_profit": metrics["net_profit"],
        "max_drawdown": metrics["max_drawdown"],
        "expectancy": metrics["expectancy"],
    }


def _summarize_walk_forward(
    period_report: pd.DataFrame,
    variants: list[V50EdgeFilterVariant],
) -> pd.DataFrame:
    if period_report.empty:
        return pd.DataFrame(columns=WALK_FORWARD_COLUMNS)

    variant_names = [variant.variant_name for variant in variants]
    diagnostics = build_strategy_diagnostics(period_report, strategy_names=variant_names)
    summary = diagnostics.rename(columns={"strategy_name": "variant_name"})
    summary.insert(0, "strategy_name", BASE_STRATEGY_NAME)
    return summary[WALK_FORWARD_COLUMNS]


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.sort_index()

    if "time" in df.columns:
        result = df.copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        result = result.dropna(subset=["time"])
        return result.set_index("time", drop=False).sort_index()

    raise ValueError("DataFrame must have a DatetimeIndex or time column")


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
