"""
Daily coverage sweep for the final V50 balanced candidate.

The variants are research-only signal wrappers around the V50 technical
features. They are designed to explore coverage/quality tradeoffs without
forcing low-quality entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.analysis.trade_level_diagnostics import prepare_trade_report
from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.strategy.rules import StrategyConfig, calculate_trade_levels
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.strategy_v50_candidates import (
    FINAL_BALANCED_STRATEGY_NAME,
    generate_final_balanced_signal,
)
from src.strategy_lab.v50_daily_coverage import (
    build_daily_breakdown,
    build_daily_coverage_report,
)


DEFAULT_DAILY_COVERAGE_SWEEP_PATH = Path("reports/strategy_lab/v50_daily_coverage_sweep.csv")
BASE_VARIANT_NAME = "daily_base"
DAILY_VARIANT_NAMES = (
    BASE_VARIANT_NAME,
    "daily_soft_score",
    "daily_soft_long_only",
    "daily_london_primary_ny_fallback",
    "daily_one_trade_fallback_quality",
    "daily_no_forced_trade",
    "daily_balanced_quality_combo",
    "daily_low_dd_combo",
)
DAILY_SWEEP_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_trades",
    "total_trading_days",
    "active_trading_days",
    "no_trade_days",
    "active_day_ratio",
    "average_trades_per_day",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "positive_days",
    "negative_days",
    "removed_trade_pct",
    "active_years",
    "max_year_net_profit_share",
    "anti_overfit_pass",
]


@dataclass(frozen=True)
class DailyCoverageVariant:
    """One V50 daily-coverage research variant."""

    variant_name: str
    score_threshold: float = strategy_v50_pine.SCORE_THRESHOLD
    score_gap: float = strategy_v50_pine.SCORE_GAP
    long_allowed_sessions: tuple[str, ...] = ("LONDON", "NEW YORK")
    short_allowed_sessions: tuple[str, ...] = ("LONDON",)
    allowed_sides: tuple[str, ...] = ("BUY", "SELL")
    blocked_sessions: tuple[str, ...] = ("ASIA/LONDON",)
    blocked_hours: tuple[int, ...] = ()
    fallback_enabled: bool = False
    fallback_score_threshold: float = 82.0
    fallback_sessions: tuple[str, ...] = ("LONDON", "NEW YORK")
    fallback_sides: tuple[str, ...] = ("BUY",)
    one_fallback_per_day: bool = True


def build_daily_coverage_variants(base_trades: pd.DataFrame | None = None) -> list[DailyCoverageVariant]:
    """Build daily-coverage variants in a stable order."""
    worst_hour = _worst_hour(base_trades)

    return [
        DailyCoverageVariant(BASE_VARIANT_NAME),
        DailyCoverageVariant("daily_soft_score", score_threshold=68.0),
        DailyCoverageVariant(
            "daily_soft_long_only",
            score_threshold=70.0,
            allowed_sides=("BUY",),
            fallback_enabled=True,
            fallback_score_threshold=78.0,
            fallback_sides=("BUY",),
        ),
        DailyCoverageVariant(
            "daily_london_primary_ny_fallback",
            score_threshold=72.0,
            long_allowed_sessions=("LONDON",),
            short_allowed_sessions=("LONDON",),
            fallback_enabled=True,
            fallback_score_threshold=80.0,
            fallback_sessions=("NEW YORK",),
            fallback_sides=("BUY",),
        ),
        DailyCoverageVariant(
            "daily_one_trade_fallback_quality",
            score_threshold=72.0,
            fallback_enabled=True,
            fallback_score_threshold=84.0,
            fallback_sides=("BUY", "SELL"),
        ),
        DailyCoverageVariant("daily_no_forced_trade", score_threshold=70.0),
        DailyCoverageVariant(
            "daily_balanced_quality_combo",
            score_threshold=70.0,
            blocked_hours=(worst_hour,) if worst_hour is not None else (),
        ),
        DailyCoverageVariant(
            "daily_low_dd_combo",
            score_threshold=72.0,
            long_allowed_sessions=("LONDON",),
            short_allowed_sessions=("LONDON",),
            blocked_hours=(worst_hour,) if worst_hour is not None else (),
        ),
    ]


def run_v50_daily_coverage_sweep(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    output_path: str | Path = DEFAULT_DAILY_COVERAGE_SWEEP_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run the daily-coverage variants and export a CSV report."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    base_result = run_daily_coverage_variant(
        df=df,
        variant=DailyCoverageVariant(BASE_VARIANT_NAME),
        strategy_config=strategy_config,
        backtest_config=backtest_config,
    )
    variants = build_daily_coverage_variants(base_result.trades)

    rows = []
    base_row = None
    for variant in variants:
        if show_progress:
            print(f"Running variant: {variant.variant_name}")

        result = base_result if variant.variant_name == BASE_VARIANT_NAME else run_daily_coverage_variant(
            df=df,
            variant=variant,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
        )
        row = _sweep_row(variant, result, market_data=df)
        if variant.variant_name == BASE_VARIANT_NAME:
            base_row = row
        row["anti_overfit_pass"] = _passes_anti_overfit(row, base_row or row)
        rows.append(row)

    report = pd.DataFrame(rows, columns=DAILY_SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def run_daily_coverage_variant(
    df: pd.DataFrame,
    variant: DailyCoverageVariant,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """Run one daily-coverage variant through the regular backtester."""
    signal_generator = (
        generate_final_balanced_signal
        if variant.variant_name == BASE_VARIANT_NAME
        else make_daily_coverage_signal_generator(variant)
    )

    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=signal_generator,
        strategy_name=variant.variant_name,
    )


def make_daily_coverage_signal_generator(variant: DailyCoverageVariant):
    """Create a V50 signal generator with controlled coverage relaxations."""
    emitted_days: set[str] = set()

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
        trade_date = timestamp.date().isoformat()

        side = _select_side(latest, variant)
        fallback_used = False
        if side == "NO_TRADE" and variant.fallback_enabled and trade_date not in emitted_days:
            side = _select_fallback_side(latest, variant)
            fallback_used = side != "NO_TRADE"

        if side == "NO_TRADE":
            return _no_trade(timestamp, config, f"daily coverage no setup | variant={variant.variant_name}")

        entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)
        if risk_reward < config.min_risk_reward:
            return _no_trade(
                timestamp,
                config,
                f"daily coverage RR below minimum | variant={variant.variant_name} | Side={side} | RR={risk_reward:.2f}",
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward=risk_reward,
            )

        emitted_days.add(trade_date)
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
                "V50 daily coverage research"
                f" | variant={variant.variant_name}"
                f" | Side={side}"
                f" | score={score:.1f}"
                f" | opposite_score={opposite_score:.1f}"
                f" | session={_session(latest)}"
                f" | fallback={fallback_used}"
                f" | RR={risk_reward:.2f}"
            ),
        )

    _signal_generator.required_history_candles = strategy_v50_pine.REQUIRED_HISTORY_CANDLES
    _signal_generator.prepare_backtest_data = strategy_v50_pine.build_v50_features
    return _signal_generator


def sort_daily_coverage_sweep(report: pd.DataFrame) -> pd.DataFrame:
    """Sort daily-coverage variants by quality and coverage."""
    prepared = report.copy()
    for column in ["profit_factor", "profit_drawdown_ratio", "active_day_ratio", "net_profit"]:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0.0)
    return prepared.sort_values(
        ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "active_day_ratio", "net_profit"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def _select_side(row: pd.Series, variant: DailyCoverageVariant) -> str:
    candidates = []
    if _side_allowed(row, "BUY", variant) and _base_side_ok(row, "BUY", variant.score_threshold, variant.score_gap):
        candidates.append(("BUY", _side_score(row, "BUY")))
    if _side_allowed(row, "SELL", variant) and _base_side_ok(row, "SELL", variant.score_threshold, variant.score_gap):
        candidates.append(("SELL", _side_score(row, "SELL")))

    if not candidates:
        return "NO_TRADE"
    return max(candidates, key=lambda item: item[1])[0]


def _select_fallback_side(row: pd.Series, variant: DailyCoverageVariant) -> str:
    session = _session(row)
    if session not in variant.fallback_sessions:
        return "NO_TRADE"
    if bool(row.get("v50_time_guard", False)) or bool(row.get("v50_chop_block", False)):
        return "NO_TRADE"
    if session in {"ASIA/LONDON", "OFF", "FX CLOSED", "UNKNOWN"}:
        return "NO_TRADE"

    candidates = []
    for side in variant.fallback_sides:
        if _side_allowed(row, side, variant) and _base_side_ok(
            row,
            side,
            variant.fallback_score_threshold,
            variant.score_gap,
        ):
            candidates.append((side, _side_score(row, side)))

    if not candidates:
        return "NO_TRADE"
    return max(candidates, key=lambda item: item[1])[0]


def _base_side_ok(row: pd.Series, side: str, threshold: float, score_gap: float) -> bool:
    if side == "BUY":
        return (
            bool(row.get("v50_setup_long", False))
            and bool(row.get("v50_quality_long_ok", False))
            and _side_score(row, side) >= threshold
            and _side_score(row, side) >= _opposite_score(row, side) + score_gap
        )
    return (
        bool(row.get("v50_setup_short", False))
        and bool(row.get("v50_quality_short_ok", False))
        and _side_score(row, side) >= threshold
        and _side_score(row, side) >= _opposite_score(row, side) + score_gap
    )


def _side_allowed(row: pd.Series, side: str, variant: DailyCoverageVariant) -> bool:
    session = _session(row)
    timestamp = row.name
    hour = timestamp.hour if hasattr(timestamp, "hour") else None

    if side not in variant.allowed_sides:
        return False
    if session in variant.blocked_sessions:
        return False
    if hour in variant.blocked_hours:
        return False
    if side == "BUY" and session not in variant.long_allowed_sessions:
        return False
    if side == "SELL" and session not in variant.short_allowed_sessions:
        return False
    return True


def _sweep_row(
    variant: DailyCoverageVariant,
    result: BacktestResult,
    market_data: pd.DataFrame,
) -> dict:
    metrics = metrics_to_dict(result.metrics)
    max_drawdown = float(metrics["max_drawdown"])
    net_profit = float(metrics["net_profit"])
    breakdown = build_daily_breakdown(result.trades, strategy_names=(variant.variant_name,), market_data=market_data)
    coverage = build_daily_coverage_report(breakdown)
    coverage_row = coverage.iloc[0].to_dict() if not coverage.empty else {}
    yearly = _yearly_net_profit(result.trades)

    return {
        "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
        "variant_name": variant.variant_name,
        "total_trades": metrics["total_trades"],
        "total_trading_days": int(coverage_row.get("total_trading_days", 0)),
        "active_trading_days": int(coverage_row.get("active_trading_days", 0)),
        "no_trade_days": int(coverage_row.get("no_trade_days", 0)),
        "active_day_ratio": float(coverage_row.get("active_day_ratio", 0.0)),
        "average_trades_per_day": float(coverage_row.get("average_trades_per_day", 0.0)),
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics["max_consecutive_losses"],
        "positive_days": int(coverage_row.get("positive_days", 0)),
        "negative_days": int(coverage_row.get("negative_days", 0)),
        "removed_trade_pct": 0.0,
        "active_years": int((yearly != 0).sum()),
        "max_year_net_profit_share": _max_year_share(yearly),
        "anti_overfit_pass": False,
    }


def _passes_anti_overfit(row: dict, base_row: dict) -> bool:
    total_trades = int(row["total_trades"])
    base_trades = max(int(base_row["total_trades"]), 1)
    removed_trade_pct = max(0.0, (base_trades - total_trades) / base_trades)
    row["removed_trade_pct"] = removed_trade_pct

    pf = float(row["profit_factor"])
    dd = float(row["max_drawdown"])
    pdd = float(row["profit_drawdown_ratio"])
    return bool(
        total_trades >= 700
        and float(row["average_trades_per_day"]) >= 0.8
        and (
            float(row["active_day_ratio"]) >= float(base_row["active_day_ratio"])
            or pf >= float(base_row["profit_factor"])
            or dd <= float(base_row["max_drawdown"])
        )
        and pf >= 1.15
        and (dd <= float(base_row["max_drawdown"]) or pdd > float(base_row["profit_drawdown_ratio"]))
        and int(row["max_consecutive_losses"]) <= int(base_row["max_consecutive_losses"])
        and removed_trade_pct <= 0.40
        and int(row["active_years"]) >= 2
        and float(row["max_year_net_profit_share"]) <= 0.75
    )


def _yearly_net_profit(trades: pd.DataFrame) -> pd.Series:
    prepared = prepare_trade_report(trades)
    if prepared.empty or "entry_time" not in prepared.columns:
        return pd.Series(dtype=float)
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return pd.Series(dtype=float)
    prepared["year"] = prepared["entry_time"].dt.year.astype("string")
    return prepared.groupby("year")["pnl"].sum()


def _max_year_share(yearly: pd.Series) -> float:
    positive_total = float(yearly[yearly > 0].sum()) if not yearly.empty else 0.0
    if positive_total <= 0:
        return 1.0
    return float(yearly.max() / positive_total)


def _worst_hour(trades: pd.DataFrame | None) -> int | None:
    if trades is None or trades.empty:
        return None
    prepared = prepare_trade_report(trades)
    if prepared.empty or "entry_time" not in prepared.columns:
        return None
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return None
    prepared["hour"] = prepared["entry_time"].dt.hour
    grouped = prepared.groupby("hour")["pnl"].agg(["count", "sum"])
    grouped = grouped[grouped["count"] >= max(5, len(prepared) * 0.02)]
    if grouped.empty:
        return None
    return int(grouped.sort_values("sum", ascending=True).index[0])


def _side_score(row: pd.Series, side: str) -> float:
    key = "v50_score_long" if side == "BUY" else "v50_score_short"
    value = row.get(key, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _opposite_score(row: pd.Series, side: str) -> float:
    return _side_score(row, "SELL" if side == "BUY" else "BUY")


def _session(row: pd.Series) -> str:
    return str(row.get("v50_session", row.get("session", "UNKNOWN"))).strip().upper()


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

