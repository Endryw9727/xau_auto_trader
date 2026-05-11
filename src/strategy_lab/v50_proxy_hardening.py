"""
Hardening diagnostics and sweeps for v50_proxy_balanced_candidate.

The variants use realtime-known score/session/hour filters. The loss-streak
guard relies on already closed trade state through the backtester risk manager,
not on future outcomes for the current signal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.strategy.rules import StrategyConfig
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.strategy_v50_proxy_candidate import STRATEGY_NAME as PROXY_CANDIDATE_NAME
from src.strategy_lab.v50_daily_coverage import build_daily_breakdown, build_daily_coverage_report
from src.strategy_lab.v50_monte_carlo import MONTE_CARLO_COLUMNS, monte_carlo_summary_row
from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    RealtimeLossProxyVariant,
    make_realtime_loss_proxy_signal_generator,
    validate_variant_no_leakage,
)
from src.strategy_lab.v50_stress_test import StressScenario, apply_trade_stress


DEFAULT_PROXY_STRESS_FAILURE_ANALYSIS_PATH = Path("reports/strategy_lab/v50_proxy_stress_failure_analysis.csv")
DEFAULT_PROXY_HARDENING_SWEEP_PATH = Path("reports/strategy_lab/v50_proxy_hardening_sweep.csv")
DEFAULT_PROXY_HARDENING_STRESS_PATH = Path("reports/strategy_lab/v50_proxy_hardening_stress.csv")
DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH = Path("reports/strategy_lab/v50_proxy_hardening_monte_carlo.csv")

PROXY_HARDENING_VARIANT_NAMES = (
    "proxy_hardened_base",
    "proxy_hardened_score_plus",
    "proxy_hardened_no_worst_hours",
    "proxy_hardened_low_slippage",
    "proxy_hardened_reduce_fast_reversal",
    "proxy_hardened_session_side",
    "proxy_hardened_loss_streak_guard",
    "proxy_hardened_low_dd",
    "proxy_hardened_balanced",
)
SWEEP_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_trades",
    "average_trades_per_day",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "positive_months",
    "negative_months",
    "anti_overfit_pass",
    "leakage_safe",
]
STRESS_COLUMNS = [
    "strategy_name",
    "variant_name",
    "scenario",
    "total_trades",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
]
FAILURE_ANALYSIS_COLUMNS = [
    "strategy_name",
    "scenario",
    "total_trades",
    "profit_factor",
    "pf_below_1_20",
    "net_profit",
    "net_profit_delta_vs_base",
    "max_drawdown",
    "max_drawdown_delta_vs_base",
    "median_mc_drawdown",
    "probability_drawdown_over_20_percent",
]
SELECTION_STRATEGIES = (
    "v50_final_balanced_strategy",
    PROXY_CANDIDATE_NAME,
    "v50_final_low_risk_strategy",
    "v50_final_growth_strategy",
)


@dataclass(frozen=True)
class ProxyHardeningVariant:
    """One realtime-safe hardening variant."""

    variant_name: str
    realtime_variant: RealtimeLossProxyVariant
    max_consecutive_losses_override: int | None = None


def build_proxy_hardening_variants() -> list[ProxyHardeningVariant]:
    """Return hardening variants in the requested stable order."""
    worst_hours = (11, 12, 20)
    london_lunch = (11, 12)
    return [
        _variant("proxy_hardened_base"),
        _variant(
            "proxy_hardened_score_plus",
            low_score_hour_blocks=((worst_hours, 78.0),),
        ),
        _variant(
            "proxy_hardened_no_worst_hours",
            blocked_hours=worst_hours,
        ),
        _variant(
            "proxy_hardened_low_slippage",
            min_score=75.0,
            min_score_gap=14.0,
        ),
        _variant(
            "proxy_hardened_reduce_fast_reversal",
            min_score_gap=14.0,
            blocked_score_buckets=("score_70_74",),
            short_min_score=78.0,
        ),
        _variant(
            "proxy_hardened_session_side",
            session_side_min_scores=(
                ("LONDON", "BUY", 75.0),
                ("LONDON", "SELL", 78.0),
                ("NEW YORK", "BUY", 75.0),
            ),
        ),
        _variant(
            "proxy_hardened_loss_streak_guard",
            min_score_gap=12.0,
            short_min_score=78.0,
            max_consecutive_losses_override=2,
        ),
        _variant(
            "proxy_hardened_low_dd",
            min_score=78.0,
            min_score_gap=14.0,
            blocked_hours=worst_hours,
            short_min_score=80.0,
        ),
        _variant(
            "proxy_hardened_balanced",
            min_score=75.0,
            min_score_gap=12.0,
            short_min_score=78.0,
            low_score_hour_blocks=((london_lunch, 80.0),),
        ),
    ]


def build_proxy_stress_failure_analysis(
    stress: pd.DataFrame,
    monte_carlo: pd.DataFrame,
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Compare stress failures for the key final/proxy candidates."""
    rows = []
    for strategy_name in SELECTION_STRATEGIES:
        strategy_stress = stress[stress["strategy_name"] == strategy_name].copy()
        if strategy_stress.empty:
            continue
        base = strategy_stress[strategy_stress["scenario"] == "base"]
        base_net = float(base.iloc[0]["net_profit"]) if not base.empty else 0.0
        base_dd = float(base.iloc[0]["max_drawdown"]) if not base.empty else 0.0
        mc_row = monte_carlo[monte_carlo["strategy_name"] == strategy_name]
        median_mc_dd = float(mc_row.iloc[0]["median_max_drawdown"]) if not mc_row.empty else 0.0
        probability_dd20 = (
            float(mc_row.iloc[0]["probability_drawdown_over_20_percent"]) if not mc_row.empty else 0.0
        )

        for _, row in strategy_stress.iterrows():
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "scenario": row["scenario"],
                    "total_trades": int(row.get("total_trades", 0)),
                    "profit_factor": float(row.get("profit_factor", 0.0)),
                    "pf_below_1_20": bool(float(row.get("profit_factor", 0.0)) < 1.20),
                    "net_profit": float(row.get("net_profit", 0.0)),
                    "net_profit_delta_vs_base": float(row.get("net_profit", 0.0)) - base_net,
                    "max_drawdown": float(row.get("max_drawdown", 0.0)),
                    "max_drawdown_delta_vs_base": float(row.get("max_drawdown", 0.0)) - base_dd,
                    "median_mc_drawdown": median_mc_dd,
                    "probability_drawdown_over_20_percent": probability_dd20,
                }
            )

    report = pd.DataFrame(rows, columns=FAILURE_ANALYSIS_COLUMNS)
    if comparison.empty:
        return report
    return report


def export_proxy_stress_failure_analysis(
    analysis: pd.DataFrame,
    output_path: str | Path = DEFAULT_PROXY_STRESS_FAILURE_ANALYSIS_PATH,
) -> Path:
    """Export proxy stress failure diagnostics."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(output_path, index=False)
    return output_path


def run_proxy_hardening_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_PROXY_HARDENING_SWEEP_PATH,
    show_progress: bool = False,
) -> tuple[pd.DataFrame, dict[str, BacktestResult]]:
    """Run the proxy hardening variants and export the sweep CSV."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    rows = []
    results: dict[str, BacktestResult] = {}
    for variant in build_proxy_hardening_variants():
        validate_proxy_hardening_variant(variant)
        if show_progress:
            print(f"Running hardening variant: {variant.variant_name}")
        result = run_proxy_hardening_variant(df, variant, strategy_config, backtest_config)
        results[variant.variant_name] = result
        rows.append(_sweep_row(variant, result, df, base_probability_dd20=None))

    report = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report, results


def run_proxy_hardening_stress(
    df: pd.DataFrame,
    sweep_report: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_PROXY_HARDENING_STRESS_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run stress scenarios on the best hardening variants."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    variants = {variant.variant_name: variant for variant in build_proxy_hardening_variants()}
    rows = []
    for variant_name in top_hardening_variant_names(sweep_report):
        variant = variants[variant_name]
        if show_progress:
            print(f"Stress hardening variant: {variant_name}")
        base_result = run_proxy_hardening_variant(df, variant, strategy_config, backtest_config)
        for scenario in build_hardening_stress_scenarios():
            if scenario.slippage_points is not None or scenario.commission_per_trade is not None:
                stressed_config = replace(
                    _config_for_variant(backtest_config, variant),
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
                result = run_proxy_hardening_variant(df, variant, strategy_config, stressed_config)
            elif scenario.pnl_multiplier is not None or scenario.remove_best_pct is not None:
                result = apply_trade_stress(base_result, scenario, backtest_config.initial_balance)
            else:
                result = base_result
            rows.append(_stress_row(variant_name, scenario.name, result))

    report = pd.DataFrame(rows, columns=STRESS_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_proxy_hardening_monte_carlo(
    results: dict[str, BacktestResult],
    sweep_report: pd.DataFrame,
    initial_balance: float,
    iterations: int = 500,
    output_path: str | Path = DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH,
) -> pd.DataFrame:
    """Run Monte Carlo reshuffling on the best hardening variants."""
    rows = []
    for offset, variant_name in enumerate(top_hardening_variant_names(sweep_report)):
        result = results.get(variant_name)
        if result is None:
            continue
        pnl = pd.to_numeric(result.trades.get("profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        rows.append(
            monte_carlo_summary_row(
                strategy_name=variant_name,
                pnl=pnl.to_numpy(dtype=float),
                base_metrics=metrics_to_dict(result.metrics),
                initial_balance=initial_balance,
                iterations=iterations,
                seed=200 + offset,
            )
        )

    report = pd.DataFrame(rows, columns=MONTE_CARLO_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_proxy_hardening_variant(
    df: pd.DataFrame,
    variant: ProxyHardeningVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one hardening variant through the normal backtester."""
    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=_config_for_variant(backtest_config, variant),
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=make_realtime_loss_proxy_signal_generator(variant.realtime_variant),
        strategy_name=variant.variant_name,
    )


def build_hardening_stress_scenarios() -> list[StressScenario]:
    """Return the required hardening stress scenarios."""
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


def top_hardening_variant_names(sweep_report: pd.DataFrame, limit: int = 5) -> list[str]:
    """Return best hardening variant names for stress and Monte Carlo."""
    prepared = sweep_report.copy()
    for column in ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "net_profit"]:
        prepared[column] = prepared.get(column, 0)
    prepared["anti_overfit_pass"] = prepared["anti_overfit_pass"].astype(bool)
    prepared = prepared.sort_values(
        ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "net_profit"],
        ascending=[False, False, False, False],
    )
    names = prepared["variant_name"].head(limit).astype(str).tolist()
    if "proxy_hardened_base" not in names and "proxy_hardened_base" in set(prepared["variant_name"]):
        names = (["proxy_hardened_base"] + names)[:limit]
    return names


def validate_proxy_hardening_variant(variant: ProxyHardeningVariant) -> None:
    """Validate hardening variant realtime filters against leakage rules."""
    validate_variant_no_leakage(variant.realtime_variant)


def annotate_hardening_interest(
    sweep: pd.DataFrame,
    stress: pd.DataFrame,
    monte_carlo: pd.DataFrame,
    base_probability_dd20: float,
) -> pd.DataFrame:
    """Apply the requested hardening-interest constraints."""
    result = sweep.copy()
    stress_medium = stress[stress["scenario"] == "spread_slippage_medium"][
        ["variant_name", "profit_factor"]
    ].rename(columns={"profit_factor": "stress_medium_profit_factor"})
    mc = monte_carlo[["strategy_name", "probability_drawdown_over_20_percent"]].rename(
        columns={"strategy_name": "variant_name"}
    )
    result = result.merge(stress_medium, on="variant_name", how="left")
    result = result.merge(mc, on="variant_name", how="left")
    result["anti_overfit_pass"] = (
        (result["total_trades"] >= 850)
        & (result["average_trades_per_day"] >= 0.75)
        & (result["profit_factor"] >= 1.23)
        & (result["max_drawdown"] <= 140)
        & (result["max_consecutive_losses"] <= 10)
        & (result["stress_medium_profit_factor"].fillna(0.0) >= 1.20)
        & (result["probability_drawdown_over_20_percent"].fillna(100.0) < base_probability_dd20)
        & result["leakage_safe"].astype(bool)
    )
    return result


def _variant(
    variant_name: str,
    max_consecutive_losses_override: int | None = None,
    **kwargs,
) -> ProxyHardeningVariant:
    base = {
        "variant_name": variant_name,
        "min_score_gap": 10.0,
        "short_min_score": 75.0,
        "blocked_score_bucket_hours": (("score_70_74", (11, 12, 20)),),
    }
    base.update(kwargs)
    variant = ProxyHardeningVariant(
        variant_name=variant_name,
        realtime_variant=RealtimeLossProxyVariant(**base),
        max_consecutive_losses_override=max_consecutive_losses_override,
    )
    validate_proxy_hardening_variant(variant)
    return variant


def _config_for_variant(config: BacktestConfig, variant: ProxyHardeningVariant) -> BacktestConfig:
    if variant.max_consecutive_losses_override is None:
        return config
    return replace(config, max_consecutive_losses=variant.max_consecutive_losses_override)


def _sweep_row(
    variant: ProxyHardeningVariant,
    result: BacktestResult,
    market_data: pd.DataFrame,
    base_probability_dd20: float | None,
) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])
    coverage = _coverage_row(result.trades, variant.variant_name, market_data)
    months = _monthly_pnl(result.trades)
    return {
        "strategy_name": PROXY_CANDIDATE_NAME,
        "variant_name": variant.variant_name,
        "total_trades": int(metrics["total_trades"]),
        "average_trades_per_day": float(coverage.get("average_trades_per_day", 0.0)),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": float(metrics["expectancy"]),
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": int(metrics["max_consecutive_losses"]),
        "positive_months": int((months > 0).sum()) if not months.empty else 0,
        "negative_months": int((months < 0).sum()) if not months.empty else 0,
        "anti_overfit_pass": False if base_probability_dd20 is None else bool(base_probability_dd20),
        "leakage_safe": True,
    }


def _stress_row(variant_name: str, scenario_name: str, result: BacktestResult) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])
    return {
        "strategy_name": PROXY_CANDIDATE_NAME,
        "variant_name": variant_name,
        "scenario": scenario_name,
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": float(metrics["expectancy"]),
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": int(metrics["max_consecutive_losses"]),
    }


def _coverage_row(trades: pd.DataFrame, strategy_name: str, market_data: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    breakdown = build_daily_breakdown(trades, strategy_names=(strategy_name,), market_data=market_data)
    coverage = build_daily_coverage_report(breakdown)
    if coverage.empty:
        return {}
    return coverage.iloc[0].to_dict()


def _monthly_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty or "entry_time" not in trades.columns:
        return pd.Series(dtype=float)
    prepared = trades.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return pd.Series(dtype=float)
    prepared["month"] = prepared["entry_time"].dt.to_period("M").astype("string")
    return prepared.groupby("month")["profit_loss"].sum()
