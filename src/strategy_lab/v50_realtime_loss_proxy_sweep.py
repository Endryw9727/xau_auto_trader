"""
Realtime-safe proxy sweep for V50 fast-loss mitigation.

Variants only use entry-known V50 signal features: hour, session, side, score,
score bucket, and score gap. They must not use outcome fields such as P&L,
exit time, or bars in trade to generate signals.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import BacktestMetrics, metrics_to_dict
from src.strategy.rules import StrategyConfig, calculate_trade_levels
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_daily_coverage import build_daily_breakdown, build_daily_coverage_report
from src.strategy_lab.v50_fast_loss_proxies import validate_no_leakage_columns
from src.strategy_lab.v50_stress_test import StressScenario, apply_trade_stress


DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH = Path("reports/strategy_lab/v50_realtime_loss_proxy_sweep.csv")
DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH = Path("reports/strategy_lab/v50_realtime_loss_proxy_stress.csv")
REALTIME_PROXY_VARIANT_NAMES = (
    "proxy_base",
    "proxy_block_score_70_74",
    "proxy_block_worst_hours",
    "proxy_block_score_70_74_in_worst_hours",
    "proxy_min_score_75",
    "proxy_min_score_78",
    "proxy_side_specific_min_score",
    "proxy_session_specific_min_score",
    "proxy_block_bad_session_side",
    "proxy_require_score_gap",
    "proxy_no_low_score_newyork",
    "proxy_no_low_score_london_lunch",
    "proxy_quality_combo",
    "proxy_balanced_combo",
    "proxy_low_dd_combo",
)
REALTIME_SWEEP_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_trades",
    "average_trades_per_day",
    "active_day_ratio",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "positive_months",
    "negative_months",
    "removed_trade_pct",
    "leakage_safe",
    "anti_overfit_pass",
]
REALTIME_STRESS_COLUMNS = [
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
ENTRY_FILTER_COLUMNS = ("hour", "session", "side", "score_bucket", "score_gap")


@dataclass(frozen=True)
class RealtimeLossProxyVariant:
    """One realtime-safe proxy filter variant."""

    variant_name: str
    min_score: float = strategy_v50_pine.SCORE_THRESHOLD
    min_score_gap: float = strategy_v50_pine.SCORE_GAP
    long_min_score: float | None = None
    short_min_score: float | None = None
    session_min_scores: tuple[tuple[str, float], ...] = ()
    blocked_hours: tuple[int, ...] = ()
    blocked_score_buckets: tuple[str, ...] = ()
    blocked_score_bucket_hours: tuple[tuple[str, tuple[int, ...]], ...] = ()
    blocked_side_sessions: tuple[tuple[str, str], ...] = ()
    low_score_session_blocks: tuple[tuple[str, float], ...] = ()
    low_score_hour_blocks: tuple[tuple[tuple[int, ...], float], ...] = ()


def build_realtime_loss_proxy_variants() -> list[RealtimeLossProxyVariant]:
    """Return realtime-safe proxy variants in a stable order."""
    worst_hours = (11, 12, 20)
    lunch_hours = (11, 12)
    return [
        RealtimeLossProxyVariant("proxy_base"),
        RealtimeLossProxyVariant("proxy_block_score_70_74", blocked_score_buckets=("score_70_74",)),
        RealtimeLossProxyVariant("proxy_block_worst_hours", blocked_hours=worst_hours),
        RealtimeLossProxyVariant(
            "proxy_block_score_70_74_in_worst_hours",
            blocked_score_bucket_hours=(("score_70_74", worst_hours),),
        ),
        RealtimeLossProxyVariant("proxy_min_score_75", min_score=75.0),
        RealtimeLossProxyVariant("proxy_min_score_78", min_score=78.0),
        RealtimeLossProxyVariant("proxy_side_specific_min_score", long_min_score=72.0, short_min_score=75.0),
        RealtimeLossProxyVariant(
            "proxy_session_specific_min_score",
            session_min_scores=(("LONDON", 75.0), ("NEW YORK", 72.0)),
        ),
        RealtimeLossProxyVariant("proxy_block_bad_session_side", blocked_side_sessions=(("LONDON", "SELL"),)),
        RealtimeLossProxyVariant("proxy_require_score_gap", min_score_gap=12.0),
        RealtimeLossProxyVariant("proxy_no_low_score_newyork", low_score_session_blocks=(("NEW YORK", 75.0),)),
        RealtimeLossProxyVariant(
            "proxy_no_low_score_london_lunch",
            low_score_hour_blocks=((lunch_hours, 75.0),),
        ),
        RealtimeLossProxyVariant(
            "proxy_quality_combo",
            min_score=75.0,
            min_score_gap=10.0,
            blocked_score_buckets=("score_70_74",),
            low_score_hour_blocks=((lunch_hours, 78.0),),
        ),
        RealtimeLossProxyVariant(
            "proxy_balanced_combo",
            min_score_gap=10.0,
            short_min_score=75.0,
            blocked_score_bucket_hours=(("score_70_74", worst_hours),),
        ),
        RealtimeLossProxyVariant(
            "proxy_low_dd_combo",
            min_score=75.0,
            min_score_gap=12.0,
            blocked_hours=worst_hours,
            blocked_side_sessions=(("LONDON", "SELL"),),
        ),
    ]


def run_realtime_loss_proxy_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run all realtime-safe proxy variants and export the sweep report."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    variants = build_realtime_loss_proxy_variants()
    rows = []
    base_row = None
    for variant in variants:
        validate_variant_no_leakage(variant)
        if show_progress:
            print(f"Running variant: {variant.variant_name}")
        result = run_realtime_loss_proxy_variant(df, variant, strategy_config, backtest_config)
        row = _sweep_row(variant, result, base_trade_count=None, market_data=df)
        if variant.variant_name == "proxy_base":
            base_row = row
            row["removed_trade_pct"] = 0.0
        else:
            row["removed_trade_pct"] = _removed_trade_pct(row, base_row)
        row["leakage_safe"] = True
        row["anti_overfit_pass"] = _passes_anti_overfit(row, base_row or row)
        rows.append(row)

    report = pd.DataFrame(rows, columns=REALTIME_SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_realtime_loss_proxy_stress(
    df: pd.DataFrame,
    sweep_report: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run stress scenarios on the best five realtime-safe proxy variants."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    variant_lookup = {variant.variant_name: variant for variant in build_realtime_loss_proxy_variants()}
    top_names = top_realtime_proxy_variant_names(sweep_report, limit=5)
    scenarios = [
        StressScenario("base"),
        StressScenario("slippage_light", slippage_points=0.05),
        StressScenario("slippage_medium", slippage_points=0.15),
        StressScenario("pnl_minus_10pct", pnl_multiplier=0.90),
        StressScenario("remove_best_5pct", remove_best_pct=0.05),
    ]
    rows = []

    for variant_name in top_names:
        variant = variant_lookup[variant_name]
        if show_progress:
            print(f"Stress variant: {variant_name}")
        base_result = run_realtime_loss_proxy_variant(df, variant, strategy_config, backtest_config)

        for scenario in scenarios:
            if scenario.slippage_points is not None:
                stressed_config = replace(backtest_config, slippage_points=scenario.slippage_points)
                result = run_realtime_loss_proxy_variant(df, variant, strategy_config, stressed_config)
            elif scenario.pnl_multiplier is not None or scenario.remove_best_pct is not None:
                result = apply_trade_stress(base_result, scenario, backtest_config.initial_balance)
            else:
                result = base_result
            rows.append(_stress_row(variant_name, scenario.name, result.metrics))

    report = pd.DataFrame(rows, columns=REALTIME_STRESS_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def top_realtime_proxy_variant_names(sweep_report: pd.DataFrame, limit: int = 5) -> list[str]:
    """Return best variant names for stress testing."""
    prepared = sweep_report.copy()
    for column in ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "net_profit"]:
        if column not in prepared.columns:
            prepared[column] = 0
    prepared["anti_overfit_pass"] = prepared["anti_overfit_pass"].astype(bool)
    prepared = prepared.sort_values(
        ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "net_profit"],
        ascending=[False, False, False, False],
    )
    names = prepared["variant_name"].head(limit).astype(str).tolist()
    if "proxy_base" not in names and "proxy_base" in set(prepared["variant_name"]):
        names = (["proxy_base"] + names)[:limit]
    return names


def run_realtime_loss_proxy_variant(
    df: pd.DataFrame,
    variant: RealtimeLossProxyVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one realtime-safe proxy variant through the backtester."""
    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=make_realtime_loss_proxy_signal_generator(variant),
        strategy_name=variant.variant_name,
    )


def make_realtime_loss_proxy_signal_generator(variant: RealtimeLossProxyVariant):
    """Create a signal generator that uses entry-known V50 proxy filters only."""
    validate_variant_no_leakage(variant)

    def _signal_generator(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
        if config is None:
            config = StrategyConfig()
        if df.empty:
            raise ValueError("DataFrame cannot be empty")

        features = (
            df
            if strategy_v50_pine.V50_REQUIRED_COLUMNS.issubset(df.columns)
            else strategy_v50_pine.build_v50_features(df)
        )
        latest = features.iloc[-1]
        timestamp = _timestamp(features)
        side = _select_proxy_side(latest, variant)
        if side == "NO_TRADE":
            return _no_trade(timestamp, config, f"V50 realtime proxy no setup | variant={variant.variant_name}")

        entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)
        if risk_reward < config.min_risk_reward:
            return _no_trade(
                timestamp,
                config,
                f"V50 realtime proxy RR below minimum | variant={variant.variant_name} | Side={side} | RR={risk_reward:.2f}",
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward=risk_reward,
            )

        score = _side_score(latest, side)
        opposite_score = _opposite_score(latest, side)
        return TradingSignal(
            timestamp=timestamp,
            symbol=config.symbol,
            timeframe=config.timeframe,
            side=side,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            confidence=min(score, 100.0),
            reason=(
                "V50 realtime loss proxy"
                f" | variant={variant.variant_name}"
                f" | Side={side}"
                f" | score={score:.1f}"
                f" | opposite_score={opposite_score:.1f}"
                f" | session={_session(latest)}"
                f" | RR={risk_reward:.2f}"
            ),
        )

    _signal_generator.required_history_candles = strategy_v50_pine.REQUIRED_HISTORY_CANDLES
    _signal_generator.prepare_backtest_data = strategy_v50_pine.build_v50_features
    return _signal_generator


def validate_variant_no_leakage(variant: RealtimeLossProxyVariant) -> None:
    """Validate realtime proxy variant fields against leakage columns."""
    validate_no_leakage_columns(ENTRY_FILTER_COLUMNS)
    if any("bars" in str(value).lower() for value in _variant_values(variant)):
        raise ValueError(f"Variant {variant.variant_name} contains bars-based leakage")


def _select_proxy_side(row: pd.Series, variant: RealtimeLossProxyVariant) -> str:
    candidates = []
    for side in ["BUY", "SELL"]:
        if _side_allowed(row, side, variant) and _side_setup_ok(row, side, variant):
            candidates.append((side, _side_score(row, side)))
    if not candidates:
        return "NO_TRADE"
    return max(candidates, key=lambda item: item[1])[0]


def _side_allowed(row: pd.Series, side: str, variant: RealtimeLossProxyVariant) -> bool:
    session = _session(row)
    hour = _hour(row)
    score = _side_score(row, side)
    score_bucket = _score_bucket(score)

    if side == "BUY" and session not in {"LONDON", "NEW YORK"}:
        return False
    if side == "SELL" and session != "LONDON":
        return False
    if session == "ASIA/LONDON":
        return False
    if hour in variant.blocked_hours:
        return False
    if score_bucket in variant.blocked_score_buckets:
        return False
    if (session, side) in variant.blocked_side_sessions:
        return False
    for bucket, hours in variant.blocked_score_bucket_hours:
        if score_bucket == bucket and hour in hours:
            return False
    for block_session, threshold in variant.low_score_session_blocks:
        if session == block_session and score < threshold:
            return False
    for hours, threshold in variant.low_score_hour_blocks:
        if hour in hours and score < threshold:
            return False
    return True


def _side_setup_ok(row: pd.Series, side: str, variant: RealtimeLossProxyVariant) -> bool:
    score = _side_score(row, side)
    opposite = _opposite_score(row, side)
    threshold = _threshold_for_side(row, side, variant)
    if side == "BUY":
        return (
            bool(row.get("v50_setup_long", False))
            and bool(row.get("v50_quality_long_ok", False))
            and score >= threshold
            and score >= opposite + variant.min_score_gap
        )
    return (
        bool(row.get("v50_setup_short", False))
        and bool(row.get("v50_quality_short_ok", False))
        and score >= threshold
        and score >= opposite + variant.min_score_gap
    )


def _threshold_for_side(row: pd.Series, side: str, variant: RealtimeLossProxyVariant) -> float:
    threshold = variant.min_score
    if side == "BUY" and variant.long_min_score is not None:
        threshold = variant.long_min_score
    if side == "SELL" and variant.short_min_score is not None:
        threshold = variant.short_min_score

    session = _session(row)
    for session_name, session_threshold in variant.session_min_scores:
        if session == session_name:
            threshold = max(threshold, session_threshold)
    return threshold


def _sweep_row(
    variant: RealtimeLossProxyVariant,
    result: BacktestResult,
    base_trade_count: int | None,
    market_data: pd.DataFrame,
) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])
    coverage = _coverage_row(result.trades, variant.variant_name, market_data)
    months = _monthly_pnl(result.trades)

    return {
        "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
        "variant_name": variant.variant_name,
        "total_trades": metrics["total_trades"],
        "average_trades_per_day": float(coverage.get("average_trades_per_day", 0.0)),
        "active_day_ratio": float(coverage.get("active_day_ratio", 0.0)),
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics["max_consecutive_losses"],
        "positive_months": int((months > 0).sum()) if not months.empty else 0,
        "negative_months": int((months < 0).sum()) if not months.empty else 0,
        "removed_trade_pct": 0.0,
        "leakage_safe": True,
        "anti_overfit_pass": False,
    }


def _passes_anti_overfit(row: dict, base_row: dict) -> bool:
    base_pf = float(base_row["profit_factor"])
    base_dd = float(base_row["max_drawdown"])
    return bool(
        int(row["total_trades"]) >= 700
        and float(row["average_trades_per_day"]) >= 0.75
        and (float(row["profit_factor"]) >= 1.25 or (float(row["profit_factor"]) >= base_pf and float(row["max_drawdown"]) <= base_dd * 0.85))
        and float(row["max_drawdown"]) <= base_dd
        and int(row["max_consecutive_losses"]) <= 10
        and float(row["net_profit"]) > 0
        and float(row["removed_trade_pct"]) <= 0.40
        and bool(row["leakage_safe"])
    )


def _stress_row(variant_name: str, scenario_name: str, metrics: BacktestMetrics) -> dict:
    metrics_dict = metrics_to_dict(metrics)
    max_drawdown = float(metrics_dict["max_drawdown"])
    net_profit = float(metrics_dict["net_profit"])
    return {
        "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
        "variant_name": variant_name,
        "scenario": scenario_name,
        "total_trades": metrics_dict["total_trades"],
        "win_rate": metrics_dict["win_rate"],
        "profit_factor": metrics_dict["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics_dict["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics_dict["max_consecutive_losses"],
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


def _removed_trade_pct(row: dict, base_row: dict | None) -> float:
    if base_row is None:
        return 0.0
    base_trades = max(int(base_row["total_trades"]), 1)
    return max(0.0, (base_trades - int(row["total_trades"])) / base_trades)


def _side_score(row: pd.Series, side: str) -> float:
    key = "v50_score_long" if side == "BUY" else "v50_score_short"
    value = row.get(key, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _opposite_score(row: pd.Series, side: str) -> float:
    return _side_score(row, "SELL" if side == "BUY" else "BUY")


def _score_bucket(score: float) -> str:
    if score < 70:
        return "score_lt_70"
    if score < 75:
        return "score_70_74"
    if score < 80:
        return "score_75_79"
    if score < 85:
        return "score_80_84"
    return "score_85_plus"


def _session(row: pd.Series) -> str:
    return str(row.get("v50_session", row.get("session", "UNKNOWN"))).strip().upper()


def _hour(row: pd.Series) -> int:
    timestamp = row.name
    if hasattr(timestamp, "hour"):
        return int(timestamp.hour)
    return -1


def _timestamp(df: pd.DataFrame) -> pd.Timestamp:
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.Timestamp(df.index[-1])
    latest = df.iloc[-1]
    for column in ("time", "Date"):
        if column in latest:
            value = pd.to_datetime(latest[column], errors="coerce")
            if pd.notna(value):
                return pd.Timestamp(value)
    return pd.Timestamp.utcnow()


def _no_trade(
    timestamp: pd.Timestamp,
    config: StrategyConfig,
    reason: str,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    risk_reward: float | None = None,
) -> TradingSignal:
    return TradingSignal(
        timestamp=timestamp.to_pydatetime(),
        symbol=config.symbol,
        timeframe=config.timeframe,
        side="NO_TRADE",
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=0.0,
        reason=reason,
    )


def _variant_values(variant: RealtimeLossProxyVariant) -> list[object]:
    return [
        variant.min_score,
        variant.min_score_gap,
        variant.long_min_score,
        variant.short_min_score,
        variant.session_min_scores,
        variant.blocked_hours,
        variant.blocked_score_buckets,
        variant.blocked_score_bucket_hours,
        variant.blocked_side_sessions,
        variant.low_score_session_blocks,
        variant.low_score_hour_blocks,
    ]
