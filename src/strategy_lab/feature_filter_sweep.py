"""
Advanced sweep helpers for mtf_feature_filtered_strategy.

This module is research/backtest only. It builds deterministic filter variants,
runs them through the existing backtester, and exports a comparison CSV.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
import time

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab.strategy_v5 import FeatureFilterConfig, make_signal_generator


DEFAULT_SWEEP_REPORT_PATH = Path("reports/strategy_lab/feature_filter_sweep.csv")

RISK_PER_TRADE_VALUES = (0.0025, 0.005)
MIN_RISK_REWARD_VALUES = (1.8, 2.0, 2.2, 2.5)
FOCUSED_MIN_RISK_REWARD_VALUES = (1.8, 2.0, 2.2)

SWEEP_COLUMNS = [
    "variant_name",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "risk_per_trade",
    "min_risk_reward",
    "allowed_sessions",
    "candle_filter",
    "adx_filter",
    "trend_filter",
]


@dataclass(frozen=True)
class OptionSet:
    """Named option group used to build variant grids."""

    label: str
    slug: str
    values: tuple[str, ...] | None


@dataclass(frozen=True)
class FeatureFilterSweepVariant:
    """One sweep variant for the feature-filtered strategy."""

    variant_name: str
    risk_per_trade: float
    min_risk_reward: float
    allowed_sessions_label: str
    allowed_sessions: tuple[str, ...] | None
    candle_filter: str
    candle_regimes: tuple[str, ...]
    adx_filter: str
    adx_buckets: tuple[str, ...]
    trend_filter: str
    trend_regimes: tuple[str, ...]


SESSION_OPTIONS = (
    OptionSet("All", "all", None),
    OptionSet("Off Session", "off", ("Off Session",)),
    OptionSet("Asia", "asia", ("Asia",)),
    OptionSet("New York", "ny", ("New York",)),
    OptionSet("Asia + New York", "asia_ny", ("Asia", "New York")),
    OptionSet("Off Session + Asia", "off_asia", ("Off Session", "Asia")),
    OptionSet("Off Session + New York", "off_ny", ("Off Session", "New York")),
)

CANDLE_FILTER_OPTIONS = (
    OptionSet("normal only", "candle_normal", ("normal",)),
    OptionSet("normal + indecision", "candle_normal_indecision", ("normal", "indecision")),
)

ADX_FILTER_OPTIONS = (
    OptionSet("moderate only", "adx_moderate", ("moderate",)),
    OptionSet("moderate + strong", "adx_moderate_strong", ("moderate", "strong")),
    OptionSet(
        "moderate + strong + very_strong",
        "adx_moderate_strong_verystrong",
        ("moderate", "strong", "very_strong"),
    ),
)

TREND_FILTER_OPTIONS = (
    OptionSet("bullish + bearish only", "trend_bull_bear", ("bullish", "bearish")),
    OptionSet("bullish only", "trend_bull", ("bullish",)),
    OptionSet("bearish only", "trend_bear", ("bearish",)),
)

FOCUSED_SESSION_OPTIONS = (
    SESSION_OPTIONS[0],
    SESSION_OPTIONS[1],
    SESSION_OPTIONS[4],
    SESSION_OPTIONS[5],
    SESSION_OPTIONS[6],
)
FOCUSED_ADX_FILTER_OPTIONS = (
    ADX_FILTER_OPTIONS[1],
    ADX_FILTER_OPTIONS[2],
)
FOCUSED_TREND_FILTER_OPTIONS = (
    TREND_FILTER_OPTIONS[0],
)


def build_feature_filter_variants() -> list[FeatureFilterSweepVariant]:
    """Build the full deterministic feature-filter sweep grid."""
    return _build_variants(
        risk_per_trade_values=RISK_PER_TRADE_VALUES,
        min_risk_reward_values=MIN_RISK_REWARD_VALUES,
        session_options=SESSION_OPTIONS,
        candle_filter_options=CANDLE_FILTER_OPTIONS,
        adx_filter_options=ADX_FILTER_OPTIONS,
        trend_filter_options=TREND_FILTER_OPTIONS,
    )


def build_focused_feature_filter_variants() -> list[FeatureFilterSweepVariant]:
    """Build a reduced feature-filter grid for faster, higher-signal sweeps."""
    return _build_variants(
        risk_per_trade_values=RISK_PER_TRADE_VALUES,
        min_risk_reward_values=FOCUSED_MIN_RISK_REWARD_VALUES,
        session_options=FOCUSED_SESSION_OPTIONS,
        candle_filter_options=CANDLE_FILTER_OPTIONS,
        adx_filter_options=FOCUSED_ADX_FILTER_OPTIONS,
        trend_filter_options=FOCUSED_TREND_FILTER_OPTIONS,
    )


def _build_variants(
    risk_per_trade_values: tuple[float, ...],
    min_risk_reward_values: tuple[float, ...],
    session_options: tuple[OptionSet, ...],
    candle_filter_options: tuple[OptionSet, ...],
    adx_filter_options: tuple[OptionSet, ...],
    trend_filter_options: tuple[OptionSet, ...],
) -> list[FeatureFilterSweepVariant]:
    """Build deterministic feature-filter variants from option groups."""
    variants: list[FeatureFilterSweepVariant] = []

    for (
        risk_per_trade,
        min_risk_reward,
        session_option,
        candle_option,
        adx_option,
        trend_option,
    ) in product(
        risk_per_trade_values,
        min_risk_reward_values,
        session_options,
        candle_filter_options,
        adx_filter_options,
        trend_filter_options,
    ):
        variant_name = "_".join(
            [
                "v5",
                f"risk{_number_slug(risk_per_trade)}",
                f"rr{_number_slug(min_risk_reward)}",
                session_option.slug,
                candle_option.slug,
                adx_option.slug,
                trend_option.slug,
            ]
        )
        variants.append(
            FeatureFilterSweepVariant(
                variant_name=variant_name,
                risk_per_trade=risk_per_trade,
                min_risk_reward=min_risk_reward,
                allowed_sessions_label=session_option.label,
                allowed_sessions=session_option.values,
                candle_filter=candle_option.label,
                candle_regimes=candle_option.values or (),
                adx_filter=adx_option.label,
                adx_buckets=adx_option.values or (),
                trend_filter=trend_option.label,
                trend_regimes=trend_option.values or (),
            )
        )

    return variants


def run_feature_filter_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    variants: list[FeatureFilterSweepVariant] | None = None,
    output_path: str | Path = DEFAULT_SWEEP_REPORT_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run feature-filter variants and export a comparison DataFrame."""
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if variants is None:
        variants = build_feature_filter_variants()

    started_at = time.perf_counter()
    rows = []
    total_variants = len(variants)

    for index, variant in enumerate(variants, start=1):
        result = run_feature_filter_variant(
            df=df,
            variant=variant,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
        )
        rows.append(_result_row(variant, result))

        if show_progress and (index == 1 or index % 25 == 0 or index == total_variants):
            elapsed = time.perf_counter() - started_at
            average_seconds = elapsed / index
            remaining_seconds = average_seconds * (total_variants - index)
            print(
                f"Completed {index}/{total_variants} variants in {elapsed:.2f}s"
                f" | avg {average_seconds:.2f}s/variant"
                f" | ETA {_format_duration(remaining_seconds)}"
            )

    comparison = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output_path, index=False)

    return comparison


def run_feature_filter_variant(
    df: pd.DataFrame,
    variant: FeatureFilterSweepVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one feature-filter variant through the existing backtester."""
    variant_backtest_config = replace(
        backtest_config,
        risk_per_trade=variant.risk_per_trade,
        min_risk_reward=variant.min_risk_reward,
        allowed_sessions=list(variant.allowed_sessions) if variant.allowed_sessions is not None else None,
    )
    feature_filter_config = FeatureFilterConfig(
        allowed_trend_regimes=variant.trend_regimes,
        allowed_candle_regimes=variant.candle_regimes,
        allowed_adx_buckets=variant.adx_buckets,
    )
    signal_generator = make_signal_generator(feature_filter_config)

    return run_backtest(
        df=df,
        strategy_config=replace(strategy_config, min_risk_reward=variant.min_risk_reward),
        backtest_config=variant_backtest_config,
        save_signals=False,
        signal_generator=signal_generator,
    )


def sort_sweep_results(comparison: pd.DataFrame) -> pd.DataFrame:
    """Sort sweep results by quality-oriented metrics."""
    return comparison.sort_values(
        by=["profit_factor", "net_profit", "max_drawdown"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def filter_primary_sweep_results(comparison: pd.DataFrame) -> pd.DataFrame:
    """Keep variants suitable for the primary top-results table."""
    return comparison[
        (comparison["total_trades"] >= 100)
        & (comparison["net_profit"] > 0)
        & (comparison["max_drawdown"] > 0)
    ]


def filter_fallback_sweep_results(comparison: pd.DataFrame) -> pd.DataFrame:
    """Keep fallback variants when the primary trade-count threshold is empty."""
    return comparison[comparison["total_trades"] >= 50]


def _result_row(variant: FeatureFilterSweepVariant, result: BacktestResult) -> dict:
    metrics = metrics_to_dict(result.metrics)

    return {
        "variant_name": variant.variant_name,
        "total_trades": metrics["total_trades"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "net_profit": metrics["net_profit"],
        "max_drawdown": metrics["max_drawdown"],
        "expectancy": metrics["expectancy"],
        "risk_per_trade": variant.risk_per_trade,
        "min_risk_reward": variant.min_risk_reward,
        "allowed_sessions": variant.allowed_sessions_label,
        "candle_filter": variant.candle_filter,
        "adx_filter": variant.adx_filter,
        "trend_filter": variant.trend_filter,
    }


def _number_slug(value: float) -> str:
    return str(value).replace(".", "p")


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"
