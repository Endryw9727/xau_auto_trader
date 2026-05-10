"""
Targeted refinement sweep for v50_growth_long_all_short_london_strategy.

The variants are research-only wrappers around the V50 technical signal. They
only block analytical signals before the backtester can open a simulated trade.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.analysis.trade_level_diagnostics import prepare_trade_report
from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import BacktestMetrics, metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab.strategy_diagnostics import build_strategy_diagnostics
from src.strategy_lab.strategy_v50_candidates import GROWTH_LONG_ALL_SHORT_LONDON_STRATEGY_NAME
from src.strategy_lab.v50_edge_filters import (
    V50EdgeFilterVariant,
    make_v50_edge_filter_signal_generator,
)
from src.strategy_lab.walk_forward_analysis import PERIOD_CHOICES, split_into_periods


DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH = Path("reports/strategy_lab/v50_growth_refinement_sweep.csv")
DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_QUARTER_PATH = Path(
    "reports/strategy_lab/v50_growth_refinement_walk_forward_quarter.csv"
)
DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_MONTH_PATH = Path(
    "reports/strategy_lab/v50_growth_refinement_walk_forward_month.csv"
)
BASE_STRATEGY_NAME = GROWTH_LONG_ALL_SHORT_LONDON_STRATEGY_NAME
VARIANT_NAMES = (
    "v50_growth_current",
    "v50_growth_no_asia_london",
    "v50_growth_london_ny_only",
    "v50_growth_london_only",
    "v50_growth_london_ny_no_londonus",
    "v50_growth_no_asia_no_asia_london",
    "v50_growth_long_london_ny_short_london",
    "v50_growth_long_london_ny_short_london_ny",
    "v50_growth_no_weak_sessions",
    "v50_growth_low_dd_candidate",
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
    "max_consecutive_losses",
    "long_trades",
    "long_net_profit",
    "long_profit_factor",
    "short_trades",
    "short_net_profit",
    "short_profit_factor",
    "side_performance",
    "session_performance",
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


def build_v50_growth_refinement_variants() -> list[V50EdgeFilterVariant]:
    """Return the requested growth-refinement variants in a stable order."""
    london_ny = ("LONDON", "NEW YORK")
    weak_overlap_sessions = ("LONDON/US", "ASIA/LONDON")

    return [
        V50EdgeFilterVariant("v50_growth_current", short_allowed_sessions=("LONDON",)),
        V50EdgeFilterVariant(
            "v50_growth_no_asia_london",
            blocked_sessions=("ASIA/LONDON",),
            short_allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant("v50_growth_london_ny_only", allowed_sessions=london_ny),
        V50EdgeFilterVariant("v50_growth_london_only", allowed_sessions=("LONDON",)),
        V50EdgeFilterVariant(
            "v50_growth_london_ny_no_londonus",
            allowed_sessions=london_ny,
            blocked_sessions=weak_overlap_sessions,
        ),
        V50EdgeFilterVariant(
            "v50_growth_no_asia_no_asia_london",
            blocked_sessions=("ASIA", "ASIA/LONDON"),
            short_allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_growth_long_london_ny_short_london",
            long_allowed_sessions=london_ny,
            short_allowed_sessions=("LONDON",),
        ),
        V50EdgeFilterVariant(
            "v50_growth_long_london_ny_short_london_ny",
            long_allowed_sessions=london_ny,
            short_allowed_sessions=london_ny,
        ),
        V50EdgeFilterVariant("v50_growth_no_weak_sessions", allowed_sessions=london_ny),
        V50EdgeFilterVariant("v50_growth_low_dd_candidate", allowed_sessions=("LONDON",)),
    ]


def run_v50_growth_refinement_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    variants: list[V50EdgeFilterVariant] | None = None,
    output_path: str | Path = DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run all growth-refinement variants over the supplied OHLCV data."""
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if variants is None:
        variants = build_v50_growth_refinement_variants()

    rows = []
    for variant in variants:
        if show_progress:
            print(f"Running variant: {variant.variant_name}")
        result = run_v50_growth_refinement_variant(df, variant, strategy_config, backtest_config)
        rows.append(_sweep_row(variant, result))

    report = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_v50_growth_refinement_walk_forward(
    df: pd.DataFrame,
    period: str,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    variants: list[V50EdgeFilterVariant] | None = None,
    output_path: str | Path | None = None,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run growth-refinement variants by calendar period."""
    if period not in PERIOD_CHOICES:
        raise ValueError(f"period must be one of: {', '.join(PERIOD_CHOICES)}")

    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if variants is None:
        variants = build_v50_growth_refinement_variants()

    if output_path is None:
        output_path = growth_refinement_walk_forward_path(period)

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


def run_v50_growth_refinement_variant(
    df: pd.DataFrame,
    variant: V50EdgeFilterVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one growth-refinement variant through the backtester."""
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


def growth_refinement_walk_forward_path(period: str) -> Path:
    """Return the default walk-forward report path for a period mode."""
    if period == "quarter":
        return DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_QUARTER_PATH
    if period == "month":
        return DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_MONTH_PATH
    return Path(f"reports/strategy_lab/v50_growth_refinement_walk_forward_{period}.csv")


def sort_growth_refinement_sweep(report: pd.DataFrame) -> pd.DataFrame:
    """Sort full-history variants by risk-adjusted quality."""
    return report.sort_values(
        ["profit_drawdown_ratio", "profit_factor", "net_profit"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def sort_growth_refinement_walk_forward(report: pd.DataFrame) -> pd.DataFrame:
    """Sort walk-forward variants by stability."""
    return report.sort_values(
        ["stability_score", "total_net_profit"],
        ascending=[False, False],
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

    return run_v50_growth_refinement_variant(df, variant, strategy_config, backtest_config)


def _sweep_row(variant: V50EdgeFilterVariant, result: BacktestResult) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])
    trades = prepare_trade_report(result.trades)
    side_performance = _group_performance(trades, "side_label")
    session_performance = _group_performance(trades, "session")
    long = side_performance.get("LONG", _empty_group_stats())
    short = side_performance.get("SHORT", _empty_group_stats())

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
        "max_consecutive_losses": metrics["max_consecutive_losses"],
        "long_trades": long["total_trades"],
        "long_net_profit": long["net_profit"],
        "long_profit_factor": long["profit_factor"],
        "short_trades": short["total_trades"],
        "short_net_profit": short["net_profit"],
        "short_profit_factor": short["profit_factor"],
        "side_performance": json.dumps(side_performance, sort_keys=True),
        "session_performance": json.dumps(session_performance, sort_keys=True),
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


def _group_performance(trades: pd.DataFrame, group_column: str) -> dict[str, dict]:
    if trades.empty or group_column not in trades.columns or "pnl" not in trades.columns:
        return {}

    performance = {}
    grouped = trades.copy()
    grouped[group_column] = grouped[group_column].astype("object").where(
        grouped[group_column].notna(),
        "Unknown",
    )

    for group_name, group in grouped.groupby(group_column, dropna=False):
        performance[str(group_name)] = _pnl_stats(group["pnl"])

    return performance


def _pnl_stats(pnl: pd.Series) -> dict:
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    total_trades = int(len(pnl))
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))
    net_profit = float(pnl.sum())

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total_trades * 100 if total_trades else 0.0,
        "net_profit": net_profit,
        "profit_factor": _safe_profit_factor(gross_profit, gross_loss),
        "average_trade": float(pnl.mean()) if total_trades else 0.0,
    }


def _safe_profit_factor(gross_profit: float, gross_loss: float) -> float | None:
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return None
    return 0.0


def _empty_group_stats() -> dict:
    return {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "net_profit": 0.0,
        "profit_factor": 0.0,
        "average_trade": 0.0,
    }


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
