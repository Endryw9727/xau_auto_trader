"""
Cost-aware diagnostics for V50 proxy candidates.

The helpers in this module are research-only. Cost-aware filters use only
entry-known trade fields such as session, side, score, score gap, target
distance and risk/reward. Outcome fields are used only after filtering to
calculate diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.backtesting.metrics import calculate_metrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_candidates, strategy_v50_proxy_candidate
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_fast_loss_proxies import validate_no_leakage_columns
from src.strategy_lab.v50_proxy_hardening import build_proxy_hardening_variants
from src.strategy_lab.v50_realtime_loss_proxy_sweep import make_realtime_loss_proxy_signal_generator


DEFAULT_COST_MODEL_AUDIT_PATH = Path("reports/strategy_lab/v50_cost_model_audit.csv")
DEFAULT_COST_AWARE_SWEEP_PATH = Path("reports/strategy_lab/v50_cost_aware_sweep.csv")
DEFAULT_AXI_REAL_COST_BACKTEST_PATH = Path("reports/strategy_lab/v50_axi_real_cost_backtest.csv")

SOURCE_VARIANT_NAMES = (
    strategy_v50_proxy_candidate.STRATEGY_NAME,
    "proxy_hardened_no_worst_hours",
    "proxy_hardened_score_plus",
    "proxy_hardened_low_dd",
)
COST_PROFILE_NAMES = (
    "cost_none",
    "axi_pro_realistic",
    "axi_pro_conservative",
    "axi_pro_stress",
    "cost_light",
    "cost_medium",
    "cost_heavy",
    "cost_extreme",
)
AXI_REAL_COST_PROFILE_NAMES = (
    "cost_none",
    "axi_pro_realistic",
    "axi_pro_conservative",
    "axi_pro_stress",
    "cost_medium",
)
AXI_REAL_COST_STRATEGY_NAMES = (
    strategy_v50_candidates.FINAL_BALANCED_STRATEGY_NAME,
    strategy_v50_proxy_candidate.STRATEGY_NAME,
    "proxy_hardened_no_worst_hours",
    "proxy_hardened_score_plus",
    "proxy_hardened_no_worst_hours_high_margin",
)
COST_AWARE_VARIANT_NAMES = (
    "costaware_base",
    "costaware_min_score_plus",
    "costaware_no_tight_tp",
    "costaware_min_expected_edge",
    "costaware_min_atr_distance",
    "costaware_skip_low_rr",
    "costaware_skip_small_target",
    "costaware_london_only_quality",
    "costaware_reduce_partial_exits",
    "costaware_tp2_tp3_focus",
    "costaware_high_margin_combo",
    "costaware_balanced_combo",
    "costaware_low_frequency_combo",
)
COST_AWARE_FILTER_COLUMNS = (
    "hour",
    "session",
    "side",
    "score",
    "score_gap",
    "target_points",
    "risk_reward",
    "target_to_cost_ratio",
    "atr_to_cost_ratio",
)
AUDIT_COLUMNS = [
    "source_variant",
    "cost_profile",
    "group_type",
    "group_value",
    "total_trades",
    "gross_net_profit",
    "net_profit",
    "total_cost",
    "average_cost_per_trade",
    "average_cost_per_round_turn",
    "round_turn_cost_points",
    "spread_points",
    "slippage_points",
    "commission_per_trade",
    "commission_per_lot",
    "backtester_slippage_applications",
    "backtester_commission_applications",
    "spread_native_supported",
    "partial_exits_supported",
    "partial_tp_cost_supported",
    "audit_note",
]
SWEEP_COLUMNS = [
    "source_variant",
    "variant_name",
    "cost_profile",
    "total_trades",
    "average_trades_per_day",
    "win_rate",
    "gross_profit_factor",
    "net_profit_factor",
    "gross_net_profit",
    "net_profit",
    "total_cost",
    "average_cost_per_trade",
    "max_drawdown",
    "expectancy_net",
    "profit_drawdown_ratio_net",
    "max_consecutive_losses",
    "positive_months",
    "negative_months",
    "pf_without_top_1pct",
    "pf_without_top_3pct",
    "pf_without_top_5pct",
    "pf_without_top_10pct",
    "net_profit_without_top_5pct",
    "max_drawdown_without_top_5pct",
    "anti_overfit_pass",
    "leakage_safe",
]
AXI_REAL_COST_COLUMNS = [
    "strategy_name",
    "cost_profile",
    "total_trades",
    "average_trades_per_day",
    "win_rate",
    "gross_profit_factor",
    "net_profit_factor",
    "gross_net_profit",
    "net_profit_after_costs",
    "total_commission",
    "total_spread_cost",
    "total_slippage_cost",
    "total_cost",
    "average_cost_per_trade",
    "average_trade_after_costs",
    "max_drawdown_after_costs",
    "expectancy_after_costs",
    "profit_drawdown_ratio_after_costs",
    "max_consecutive_losses",
    "positive_months",
    "negative_months",
    "average_lot",
    "max_lot",
    "commission_round_turn_per_001_lot",
    "profile_note",
]


@dataclass(frozen=True)
class CostProfile:
    """Static research cost profile."""

    name: str
    spread_points: float
    slippage_points: float
    commission_per_trade: float
    commission_per_lot: float = 0.0
    note: str = ""
    spread_pips: float | None = None
    slippage_pips: float | None = None
    commission_per_001_lot_per_side: float | None = None
    pip_value_eur_per_001_lot: float = 0.01
    profile_group: str = "legacy"

    @property
    def is_axi_profile(self) -> bool:
        """Return True for Axi-style lot-based profiles."""
        return self.profile_group == "axi"

    @property
    def commission_round_turn_per_001_lot(self) -> float:
        """Return round-turn commission for 0.01 lot."""
        if self.commission_per_001_lot_per_side is None:
            return 0.0
        return float(self.commission_per_001_lot_per_side * 2.0)


@dataclass(frozen=True)
class AxiSizingConfig:
    """Equity-step lot sizing used for Axi real-cost research."""

    initial_equity_eur: float = 1000.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    equity_step_eur: float = 1000.0
    max_lot: float | None = 0.10
    eur_per_price_point_per_001_lot: float = 1.0


@dataclass(frozen=True)
class CostAwareVariant:
    """One entry-known cost-aware filter."""

    variant_name: str
    min_score: float | None = None
    min_score_gap: float | None = None
    min_risk_reward: float | None = None
    min_target_points: float | None = None
    min_target_to_cost_ratio: float | None = None
    min_atr_to_cost_ratio: float | None = None
    allowed_sessions: tuple[str, ...] = ()
    blocked_sessions: tuple[str, ...] = ()
    blocked_hours: tuple[int, ...] = ()
    long_min_score: float | None = None
    short_min_score: float | None = None


def build_cost_profiles() -> list[CostProfile]:
    """Return static research cost profiles in stable order."""
    return [
        CostProfile(
            "cost_none",
            0.0,
            0.0,
            0.0,
            0.0,
            "No simulated trading costs.",
            spread_pips=0.0,
            slippage_pips=0.0,
            commission_per_001_lot_per_side=0.0,
            profile_group="baseline",
        ),
        CostProfile(
            "axi_pro_realistic",
            0.0,
            0.0,
            0.0,
            0.0,
            "Axi Pro user-stated realistic profile: zero spread/slippage, EUR 0.04 per 0.01 lot per side.",
            spread_pips=0.0,
            slippage_pips=0.0,
            commission_per_001_lot_per_side=0.04,
            profile_group="axi",
        ),
        CostProfile(
            "axi_pro_conservative",
            0.0,
            0.0,
            0.0,
            0.0,
            "Axi Pro conservative profile: zero spread, 0.1 pip slippage per side, stated commission.",
            spread_pips=0.0,
            slippage_pips=0.1,
            commission_per_001_lot_per_side=0.04,
            profile_group="axi",
        ),
        CostProfile(
            "axi_pro_stress",
            0.0,
            0.0,
            0.0,
            0.0,
            "Axi Pro stress profile: 0.1 pip spread, 0.2 pip slippage per side, stated commission.",
            spread_pips=0.1,
            slippage_pips=0.2,
            commission_per_001_lot_per_side=0.04,
            profile_group="axi",
        ),
        CostProfile("cost_light", 0.05, 0.05, 0.20, 0.0, "Legacy generic light cost profile."),
        CostProfile("cost_medium", 0.10, 0.15, 0.50, 0.0, "Legacy generic medium cost profile, kept as extreme comparison."),
        CostProfile("cost_heavy", 0.20, 0.30, 1.00, 0.0, "Legacy generic heavy cost profile, kept as stress comparison."),
        CostProfile("cost_extreme", 0.35, 0.50, 1.50, 0.0, "Legacy generic extreme profile."),
    ]


def axi_real_cost_profiles() -> list[CostProfile]:
    """Return only profiles used in Axi real-cost reports."""
    profiles = {profile.name: profile for profile in build_cost_profiles()}
    return [profiles[name] for name in AXI_REAL_COST_PROFILE_NAMES]


def lot_size_for_equity(equity: float, config: AxiSizingConfig | None = None) -> float:
    """Return Axi lot size for the current simulated equity."""
    if config is None:
        config = AxiSizingConfig()
    if config.initial_equity_eur <= 0:
        raise ValueError("initial_equity_eur must be greater than 0")
    if config.min_lot <= 0 or config.lot_step <= 0 or config.equity_step_eur <= 0:
        raise ValueError("lot sizing values must be positive")

    step_count = int(max(0.0, equity - config.initial_equity_eur) // config.equity_step_eur)
    lot = config.min_lot + (step_count * config.lot_step)
    if config.max_lot is not None:
        lot = min(lot, config.max_lot)
    return round(lot, 2)


def build_cost_aware_variants() -> list[CostAwareVariant]:
    """Return requested cost-aware variants in stable order."""
    return [
        CostAwareVariant("costaware_base"),
        CostAwareVariant("costaware_min_score_plus", min_score=78.0),
        CostAwareVariant("costaware_no_tight_tp", min_target_to_cost_ratio=6.0),
        CostAwareVariant("costaware_min_expected_edge", min_score_gap=14.0, min_target_to_cost_ratio=5.0),
        CostAwareVariant("costaware_min_atr_distance", min_atr_to_cost_ratio=8.0),
        CostAwareVariant("costaware_skip_low_rr", min_risk_reward=2.2),
        CostAwareVariant("costaware_skip_small_target", min_target_points=3.0),
        CostAwareVariant("costaware_london_only_quality", allowed_sessions=("LONDON",), min_score=75.0),
        CostAwareVariant("costaware_reduce_partial_exits", min_target_to_cost_ratio=8.0),
        CostAwareVariant("costaware_tp2_tp3_focus", min_risk_reward=2.4, min_score_gap=12.0),
        CostAwareVariant(
            "costaware_high_margin_combo",
            min_score=78.0,
            min_score_gap=14.0,
            min_target_to_cost_ratio=8.0,
            min_atr_to_cost_ratio=10.0,
            allowed_sessions=("LONDON", "NEW YORK"),
        ),
        CostAwareVariant(
            "costaware_balanced_combo",
            min_score=75.0,
            min_score_gap=12.0,
            min_target_to_cost_ratio=6.0,
            min_atr_to_cost_ratio=8.0,
            allowed_sessions=("LONDON", "NEW YORK"),
        ),
        CostAwareVariant(
            "costaware_low_frequency_combo",
            min_score=80.0,
            min_score_gap=16.0,
            min_target_to_cost_ratio=10.0,
            min_atr_to_cost_ratio=12.0,
            allowed_sessions=("LONDON",),
        ),
    ]


def run_source_variant_backtests(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    show_progress: bool = False,
) -> dict[str, BacktestResult]:
    """Run the clean source variants once."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    results: dict[str, BacktestResult] = {}
    for source_name in SOURCE_VARIANT_NAMES:
        if show_progress:
            print(f"Running source variant: {source_name}")
        results[source_name] = _run_source_variant(df, source_name, strategy_config, backtest_config)
    return results


def run_axi_source_backtests(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    show_progress: bool = False,
) -> dict[str, BacktestResult]:
    """Run source strategies required for Axi real-cost evaluation."""
    if strategy_config is None:
        strategy_config = StrategyConfig()
    if backtest_config is None:
        backtest_config = BacktestConfig()

    sources = [
        strategy_v50_candidates.FINAL_BALANCED_STRATEGY_NAME,
        strategy_v50_proxy_candidate.STRATEGY_NAME,
        "proxy_hardened_no_worst_hours",
        "proxy_hardened_score_plus",
    ]
    results: dict[str, BacktestResult] = {}
    for source_name in sources:
        if show_progress:
            print(f"Running Axi source strategy: {source_name}")
        results[source_name] = _run_source_variant(df, source_name, strategy_config, backtest_config)
    return results


def run_axi_real_cost_backtest(
    source_results: dict[str, BacktestResult],
    market_data: pd.DataFrame,
    profiles: list[CostProfile] | None = None,
    sizing_config: AxiSizingConfig | None = None,
    value_per_point: float = 1.0,
    output_path: str | Path = DEFAULT_AXI_REAL_COST_BACKTEST_PATH,
) -> pd.DataFrame:
    """Evaluate requested V50 candidates with Axi real-cost profiles."""
    if profiles is None:
        profiles = axi_real_cost_profiles()
    if sizing_config is None:
        sizing_config = AxiSizingConfig()

    rows = []
    for strategy_name, result in source_results.items():
        trades = _prepare_trade_candidates(result.trades, strategy_name)
        for profile in profiles:
            net_trades = apply_cost_profile_to_trades(
                trades,
                profile,
                value_per_point=value_per_point,
                sizing_config=sizing_config,
            )
            rows.append(_axi_real_cost_row(strategy_name, profile, net_trades, market_data))

    high_margin_source = source_results.get("proxy_hardened_no_worst_hours")
    if high_margin_source is not None:
        high_margin_variant = next(
            variant for variant in build_cost_aware_variants() if variant.variant_name == "costaware_high_margin_combo"
        )
        base_trades = _prepare_trade_candidates(high_margin_source.trades, "proxy_hardened_no_worst_hours")
        for profile in profiles:
            filtered = apply_cost_aware_filter(base_trades, high_margin_variant, profile, value_per_point=value_per_point)
            net_trades = apply_cost_profile_to_trades(
                filtered,
                profile,
                value_per_point=value_per_point,
                sizing_config=sizing_config,
            )
            rows.append(_axi_real_cost_row("proxy_hardened_no_worst_hours_high_margin", profile, net_trades, market_data))

    report = pd.DataFrame(rows, columns=AXI_REAL_COST_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def build_cost_model_audit(
    source_results: dict[str, BacktestResult],
    profiles: list[CostProfile] | None = None,
    value_per_point: float = 1.0,
) -> pd.DataFrame:
    """Audit static cost impact by source variant, side and session."""
    if profiles is None:
        profiles = build_cost_profiles()

    rows = []
    for source_name, result in source_results.items():
        trades = _prepare_trade_candidates(result.trades, source_name)
        for profile in profiles:
            net_trades = apply_cost_profile_to_trades(trades, profile, value_per_point=value_per_point)
            rows.append(_audit_row(source_name, profile, "variant", source_name, net_trades))
            for side, group in net_trades.groupby("side", dropna=False):
                rows.append(_audit_row(source_name, profile, "side", str(side), group))
            for session, group in net_trades.groupby("session", dropna=False):
                rows.append(_audit_row(source_name, profile, "session", str(session), group))
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def export_cost_model_audit(
    audit: pd.DataFrame,
    output_path: str | Path = DEFAULT_COST_MODEL_AUDIT_PATH,
) -> Path:
    """Export cost model audit CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_path, index=False)
    return output_path


def run_cost_aware_sweep(
    source_results: dict[str, BacktestResult],
    market_data: pd.DataFrame,
    profiles: list[CostProfile] | None = None,
    variants: list[CostAwareVariant] | None = None,
    value_per_point: float = 1.0,
    output_path: str | Path = DEFAULT_COST_AWARE_SWEEP_PATH,
    show_progress: bool = False,
) -> pd.DataFrame:
    """Run cost-aware filters over clean source-variant trade candidates."""
    if profiles is None:
        profiles = build_cost_profiles()
    if variants is None:
        variants = build_cost_aware_variants()

    rows = []
    for source_name, result in source_results.items():
        candidates = _prepare_trade_candidates(result.trades, source_name)
        for variant in variants:
            validate_cost_aware_variant(variant)
            for profile in profiles:
                if show_progress:
                    print(f"Cost-aware row: {source_name} / {variant.variant_name} / {profile.name}")
                filtered = apply_cost_aware_filter(candidates, variant, profile, value_per_point=value_per_point)
                net_trades = apply_cost_profile_to_trades(filtered, profile, value_per_point=value_per_point)
                rows.append(_sweep_row(source_name, variant, profile, net_trades, market_data))

    report = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def apply_cost_aware_filter(
    trades: pd.DataFrame,
    variant: CostAwareVariant,
    profile: CostProfile,
    value_per_point: float = 1.0,
) -> pd.DataFrame:
    """Filter trades using entry-known cost-aware fields only."""
    validate_cost_aware_variant(variant)
    prepared = _prepare_trade_candidates(trades, source_variant=str(trades.get("strategy_name", pd.Series(["source"])).iloc[0]) if not trades.empty else "source")
    if prepared.empty:
        return prepared

    result = prepared.copy()
    mask = pd.Series(True, index=result.index)
    score = pd.to_numeric(result["score"], errors="coerce").fillna(0.0)
    gap = pd.to_numeric(result["score_gap"], errors="coerce").fillna(0.0)
    rr = pd.to_numeric(result["risk_reward"], errors="coerce").fillna(0.0)
    target_points = pd.to_numeric(result["target_points"], errors="coerce").fillna(0.0)
    profile_cost = estimate_trade_cost(result, profile, value_per_point=value_per_point)
    target_money = target_points * pd.to_numeric(result["position_size"], errors="coerce").fillna(0.0) * value_per_point
    atr_money = pd.to_numeric(result["atr_proxy_points"], errors="coerce").fillna(0.0) * pd.to_numeric(
        result["position_size"], errors="coerce"
    ).fillna(0.0) * value_per_point
    result["target_to_cost_ratio"] = _safe_ratio_series(target_money, profile_cost)
    result["atr_to_cost_ratio"] = _safe_ratio_series(atr_money, profile_cost)

    if variant.min_score is not None:
        mask &= score >= variant.min_score
    if variant.long_min_score is not None:
        mask &= (result["side"] != "BUY") | (score >= variant.long_min_score)
    if variant.short_min_score is not None:
        mask &= (result["side"] != "SELL") | (score >= variant.short_min_score)
    if variant.min_score_gap is not None:
        mask &= gap >= variant.min_score_gap
    if variant.min_risk_reward is not None:
        mask &= rr >= variant.min_risk_reward
    if variant.min_target_points is not None:
        mask &= target_points >= variant.min_target_points
    if variant.min_target_to_cost_ratio is not None:
        mask &= result["target_to_cost_ratio"] >= variant.min_target_to_cost_ratio
    if variant.min_atr_to_cost_ratio is not None:
        mask &= result["atr_to_cost_ratio"] >= variant.min_atr_to_cost_ratio
    if variant.allowed_sessions:
        mask &= result["session"].isin(variant.allowed_sessions)
    if variant.blocked_sessions:
        mask &= ~result["session"].isin(variant.blocked_sessions)
    if variant.blocked_hours:
        mask &= ~result["hour"].isin(variant.blocked_hours)

    return result[mask].reset_index(drop=True)


def apply_cost_profile_to_trades(
    trades: pd.DataFrame,
    profile: CostProfile,
    value_per_point: float = 1.0,
    sizing_config: AxiSizingConfig | None = None,
) -> pd.DataFrame:
    """Return trades with gross/net P&L columns for one cost profile."""
    result = _prepare_trade_candidates(trades, source_variant="source")
    if result.empty:
        result["gross_profit_loss"] = pd.Series(dtype=float)
        result["cost_amount"] = pd.Series(dtype=float)
        result["net_profit_loss"] = pd.Series(dtype=float)
        return result

    if profile.is_axi_profile:
        return apply_axi_cost_profile_to_trades(
            result,
            profile,
            sizing_config=sizing_config,
        )

    result["gross_profit_loss"] = pd.to_numeric(result["profit_loss"], errors="coerce").fillna(0.0)
    spread_cost, slippage_cost, commission_cost = _legacy_cost_components(result, profile, value_per_point)
    result["lot_size"] = pd.NA
    result["spread_cost"] = spread_cost
    result["slippage_cost"] = slippage_cost
    result["commission_cost"] = commission_cost
    result["cost_amount"] = result["spread_cost"] + result["slippage_cost"] + result["commission_cost"]
    result["net_profit_loss"] = result["gross_profit_loss"] - result["cost_amount"]
    result["pnl"] = result["net_profit_loss"]
    result["profit_loss"] = result["net_profit_loss"]
    return result


def apply_axi_cost_profile_to_trades(
    trades: pd.DataFrame,
    profile: CostProfile,
    sizing_config: AxiSizingConfig | None = None,
) -> pd.DataFrame:
    """Apply Axi lot-step commission/spread/slippage costs sequentially."""
    if sizing_config is None:
        sizing_config = AxiSizingConfig()
    result = _prepare_trade_candidates(trades, source_variant="source")
    if result.empty:
        return result

    result["gross_profit_loss"] = pd.to_numeric(result["profit_loss"], errors="coerce").fillna(0.0)
    equity = sizing_config.initial_equity_eur
    lots = []
    equity_before = []
    equity_after = []
    spread_costs = []
    slippage_costs = []
    commission_costs = []
    net_pnl = []

    for gross_pnl in result["gross_profit_loss"]:
        lot = lot_size_for_equity(equity, sizing_config)
        spread_cost, slippage_cost, commission_cost = _axi_cost_components_for_lot(profile, lot)
        total_cost = spread_cost + slippage_cost + commission_cost
        net = float(gross_pnl) - total_cost

        equity_before.append(equity)
        lots.append(lot)
        spread_costs.append(spread_cost)
        slippage_costs.append(slippage_cost)
        commission_costs.append(commission_cost)
        net_pnl.append(net)
        equity += net
        equity_after.append(equity)

    result["equity_before_trade"] = equity_before
    result["equity_after_trade"] = equity_after
    result["lot_size"] = lots
    result["spread_cost"] = spread_costs
    result["slippage_cost"] = slippage_costs
    result["commission_cost"] = commission_costs
    result["cost_amount"] = result["spread_cost"] + result["slippage_cost"] + result["commission_cost"]
    result["net_profit_loss"] = net_pnl
    result["pnl"] = result["net_profit_loss"]
    result["profit_loss"] = result["net_profit_loss"]
    return result


def estimate_trade_cost(
    trades: pd.DataFrame,
    profile: CostProfile,
    value_per_point: float = 1.0,
) -> pd.Series:
    """Estimate static round-turn cost for each trade."""
    if trades.empty:
        return pd.Series(dtype=float)
    if profile.is_axi_profile:
        spread_cost, slippage_cost, commission_cost = _axi_cost_components_for_lot(profile, lot=0.01)
        return pd.Series([spread_cost + slippage_cost + commission_cost] * len(trades), index=trades.index)
    spread_cost, slippage_cost, commission_cost = _legacy_cost_components(trades, profile, value_per_point)
    return (spread_cost + slippage_cost + commission_cost).astype(float)


def axi_cost_components_for_lot(profile: CostProfile, lot: float) -> tuple[float, float, float]:
    """Return spread, slippage and commission costs for one Axi lot size."""
    return _axi_cost_components_for_lot(profile, lot)


def round_turn_cost_points(profile: CostProfile) -> float:
    """Return spread plus entry/exit slippage in points."""
    return float(profile.spread_points + (2.0 * profile.slippage_points))


def validate_cost_aware_variant(variant: CostAwareVariant) -> None:
    """Validate cost-aware filter fields against leakage rules."""
    validate_no_leakage_columns(COST_AWARE_FILTER_COLUMNS)
    text = repr(variant).lower()
    forbidden = ("pnl", "profit_loss", "exit_time", "bars_in_trade", "trade_result", "drawdown")
    if any(token in text for token in forbidden):
        raise ValueError(f"Cost-aware variant {variant.variant_name} contains leakage token")


def select_best_rows_for_anti_top_trade(report: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    """Return robust rows for selection reporting."""
    if report.empty:
        return report
    prepared = report.copy()
    medium = prepared[prepared["cost_profile"] == "cost_medium"].copy()
    if medium.empty:
        medium = prepared
    return medium.sort_values(
        ["anti_overfit_pass", "net_profit_factor", "profit_drawdown_ratio_net", "net_profit"],
        ascending=[False, False, False, False],
    ).head(limit)


def _run_source_variant(
    df: pd.DataFrame,
    source_name: str,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    if source_name == strategy_v50_candidates.FINAL_BALANCED_STRATEGY_NAME:
        signal_generator = strategy_v50_candidates.generate_final_balanced_signal
        config = backtest_config
    elif source_name == strategy_v50_proxy_candidate.STRATEGY_NAME:
        signal_generator = strategy_v50_proxy_candidate.generate_signal
        config = backtest_config
    else:
        variants = {variant.variant_name: variant for variant in build_proxy_hardening_variants()}
        if source_name not in variants:
            raise ValueError(f"Unknown V50 cost-aware source variant: {source_name}")
        proxy_variant = variants[source_name]
        signal_generator = make_realtime_loss_proxy_signal_generator(proxy_variant.realtime_variant)
        config = backtest_config
        if proxy_variant.max_consecutive_losses_override is not None:
            from dataclasses import replace

            config = replace(config, max_consecutive_losses=proxy_variant.max_consecutive_losses_override)

    return run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=signal_generator,
        strategy_name=source_name,
    )


def _prepare_trade_candidates(trades: pd.DataFrame, source_variant: str) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        return result
    if "strategy_name" not in result.columns:
        result["strategy_name"] = source_variant
    result["source_variant"] = source_variant
    result["entry_time"] = pd.to_datetime(_series_or_default(result, "entry_time", pd.NaT), errors="coerce")
    result["hour"] = result["entry_time"].dt.hour.fillna(-1).astype(int)
    result["day_of_week"] = result["entry_time"].dt.day_name()
    result["session"] = _series_or_default(result, "session", "UNKNOWN").astype(str).str.upper()
    result["side"] = _series_or_default(result, "side", "UNKNOWN").astype(str).str.upper()

    score_long = pd.to_numeric(_series_or_default(result, "score_long", 0.0), errors="coerce")
    score_short = pd.to_numeric(_series_or_default(result, "score_short", 0.0), errors="coerce")
    side = result["side"]
    result["score"] = score_long.where(side == "BUY", score_short).fillna(0.0)
    result["opposite_score"] = score_short.where(side == "BUY", score_long).fillna(0.0)
    result["score_gap"] = (result["score"] - result["opposite_score"]).abs()

    entry = pd.to_numeric(_series_or_default(result, "entry_price", 0.0), errors="coerce").fillna(0.0)
    stop = pd.to_numeric(_series_or_default(result, "stop_loss", 0.0), errors="coerce").fillna(entry)
    target = pd.to_numeric(_series_or_default(result, "take_profit", 0.0), errors="coerce").fillna(entry)
    result["target_points"] = (target - entry).abs()
    result["stop_points"] = (entry - stop).abs()
    result["risk_reward"] = _safe_ratio_series(result["target_points"], result["stop_points"])
    result["atr_proxy_points"] = result["target_points"] / 3.0
    result["position_size"] = pd.to_numeric(_series_or_default(result, "position_size", 0.0), errors="coerce").fillna(0.0)
    result["profit_loss"] = pd.to_numeric(_series_or_default(result, "profit_loss", 0.0), errors="coerce").fillna(0.0)
    return result.reset_index(drop=True)


def _series_or_default(df: pd.DataFrame, column: str, default: object) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([default] * len(df), index=df.index)


def _sweep_row(
    source_name: str,
    variant: CostAwareVariant,
    profile: CostProfile,
    trades: pd.DataFrame,
    market_data: pd.DataFrame,
) -> dict:
    gross_pnl = pd.to_numeric(trades.get("gross_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    net_pnl = pd.to_numeric(trades.get("net_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    net_metrics = calculate_metrics(pd.DataFrame({"profit_loss": net_pnl}), 1000.0)
    gross_pf = _profit_factor(gross_pnl)
    net_pf = net_metrics.profit_factor
    max_drawdown = net_metrics.max_drawdown
    months = _monthly_pnl(trades, pnl_column="net_profit_loss")
    total_trades = int(len(trades))
    average_trades_per_day = _average_trades_per_day(trades, market_data)
    total_cost = float(pd.to_numeric(trades.get("cost_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    anti = _passes_cost_aware_constraints(
        total_trades=total_trades,
        average_trades_per_day=average_trades_per_day,
        net_profit_factor=net_pf,
        net_profit=float(net_pnl.sum()),
        max_drawdown=max_drawdown,
        max_consecutive_losses=net_metrics.max_consecutive_losses,
    )
    anti_top = _anti_top_trade_metrics(net_pnl)
    return {
        "source_variant": source_name,
        "variant_name": variant.variant_name,
        "cost_profile": profile.name,
        "total_trades": total_trades,
        "average_trades_per_day": average_trades_per_day,
        "win_rate": net_metrics.win_rate,
        "gross_profit_factor": gross_pf,
        "net_profit_factor": net_pf,
        "gross_net_profit": float(gross_pnl.sum()),
        "net_profit": float(net_pnl.sum()),
        "total_cost": total_cost,
        "average_cost_per_trade": total_cost / total_trades if total_trades else 0.0,
        "max_drawdown": max_drawdown,
        "expectancy_net": net_metrics.expectancy,
        "profit_drawdown_ratio_net": float(net_pnl.sum()) / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": net_metrics.max_consecutive_losses,
        "positive_months": int((months > 0).sum()) if not months.empty else 0,
        "negative_months": int((months < 0).sum()) if not months.empty else 0,
        "pf_without_top_1pct": anti_top["pf_without_top_1pct"],
        "pf_without_top_3pct": anti_top["pf_without_top_3pct"],
        "pf_without_top_5pct": anti_top["pf_without_top_5pct"],
        "pf_without_top_10pct": anti_top["pf_without_top_10pct"],
        "net_profit_without_top_5pct": anti_top["net_profit_without_top_5pct"],
        "max_drawdown_without_top_5pct": anti_top["max_drawdown_without_top_5pct"],
        "anti_overfit_pass": anti,
        "leakage_safe": True,
    }


def _axi_real_cost_row(
    strategy_name: str,
    profile: CostProfile,
    trades: pd.DataFrame,
    market_data: pd.DataFrame,
) -> dict:
    gross_pnl = pd.to_numeric(trades.get("gross_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    net_pnl = pd.to_numeric(trades.get("net_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    metrics = calculate_metrics(pd.DataFrame({"profit_loss": net_pnl}), 1000.0)
    gross_pf = _profit_factor(gross_pnl)
    months = _monthly_pnl(trades, pnl_column="net_profit_loss")
    total_trades = int(len(trades))
    net_profit = float(net_pnl.sum())
    max_drawdown = float(metrics.max_drawdown)
    lots = pd.to_numeric(trades.get("lot_size", pd.Series(dtype=float)), errors="coerce")
    return {
        "strategy_name": strategy_name,
        "cost_profile": profile.name,
        "total_trades": total_trades,
        "average_trades_per_day": _average_trades_per_day(trades, market_data),
        "win_rate": metrics.win_rate,
        "gross_profit_factor": gross_pf,
        "net_profit_factor": metrics.profit_factor,
        "gross_net_profit": float(gross_pnl.sum()),
        "net_profit_after_costs": net_profit,
        "total_commission": _sum_column(trades, "commission_cost"),
        "total_spread_cost": _sum_column(trades, "spread_cost"),
        "total_slippage_cost": _sum_column(trades, "slippage_cost"),
        "total_cost": _sum_column(trades, "cost_amount"),
        "average_cost_per_trade": _sum_column(trades, "cost_amount") / total_trades if total_trades else 0.0,
        "average_trade_after_costs": float(net_pnl.mean()) if total_trades else 0.0,
        "max_drawdown_after_costs": max_drawdown,
        "expectancy_after_costs": metrics.expectancy,
        "profit_drawdown_ratio_after_costs": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics.max_consecutive_losses,
        "positive_months": int((months > 0).sum()) if not months.empty else 0,
        "negative_months": int((months < 0).sum()) if not months.empty else 0,
        "average_lot": float(lots.mean()) if lots.notna().any() else 0.0,
        "max_lot": float(lots.max()) if lots.notna().any() else 0.0,
        "commission_round_turn_per_001_lot": profile.commission_round_turn_per_001_lot,
        "profile_note": profile.note,
    }


def _audit_row(
    source_name: str,
    profile: CostProfile,
    group_type: str,
    group_value: str,
    trades: pd.DataFrame,
) -> dict:
    gross = pd.to_numeric(trades.get("gross_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    net = pd.to_numeric(trades.get("net_profit_loss", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    cost = pd.to_numeric(trades.get("cost_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    total_trades = int(len(trades))
    return {
        "source_variant": source_name,
        "cost_profile": profile.name,
        "group_type": group_type,
        "group_value": group_value,
        "total_trades": total_trades,
        "gross_net_profit": float(gross.sum()),
        "net_profit": float(net.sum()),
        "total_cost": float(cost.sum()),
        "average_cost_per_trade": float(cost.mean()) if total_trades else 0.0,
        "average_cost_per_round_turn": float(cost.mean()) if total_trades else 0.0,
        "round_turn_cost_points": round_turn_cost_points(profile),
        "spread_points": profile.spread_points,
        "slippage_points": profile.slippage_points,
        "commission_per_trade": profile.commission_per_trade,
        "commission_per_lot": profile.commission_per_lot,
        "backtester_slippage_applications": 2,
        "backtester_commission_applications": 1,
        "spread_native_supported": False,
        "partial_exits_supported": False,
        "partial_tp_cost_supported": False,
        "audit_note": (
            "Backtester applies slippage on entry and exit and one fixed commission per closed trade; "
            "spread is simulated here as a static round-turn cost; partial exits are not supported."
        ),
    }


def _legacy_cost_components(
    trades: pd.DataFrame,
    profile: CostProfile,
    value_per_point: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    position_size = pd.to_numeric(_series_or_default(trades, "position_size", 0.0), errors="coerce").fillna(0.0)
    spread_cost = profile.spread_points * position_size * value_per_point
    slippage_cost = 2.0 * profile.slippage_points * position_size * value_per_point
    commission_cost = profile.commission_per_trade + (profile.commission_per_lot * position_size)
    return spread_cost.astype(float), slippage_cost.astype(float), commission_cost.astype(float)


def _axi_cost_components_for_lot(profile: CostProfile, lot: float) -> tuple[float, float, float]:
    lot_units = max(lot, 0.0) / 0.01
    spread_pips = float(profile.spread_pips or 0.0)
    slippage_pips = float(profile.slippage_pips or 0.0)
    spread_cost = spread_pips * profile.pip_value_eur_per_001_lot * lot_units
    slippage_cost = 2.0 * slippage_pips * profile.pip_value_eur_per_001_lot * lot_units
    commission_side = float(profile.commission_per_001_lot_per_side or 0.0)
    commission_cost = 2.0 * commission_side * lot_units
    return spread_cost, slippage_cost, commission_cost


def _sum_column(df: pd.DataFrame, column: str) -> float:
    return float(pd.to_numeric(df.get(column, pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())


def _passes_cost_aware_constraints(
    total_trades: int,
    average_trades_per_day: float,
    net_profit_factor: float,
    net_profit: float,
    max_drawdown: float,
    max_consecutive_losses: int,
) -> bool:
    return bool(
        total_trades >= 700
        and average_trades_per_day >= 0.70
        and net_profit_factor >= 1.20
        and net_profit > 0
        and max_drawdown <= 160.0
        and max_consecutive_losses <= 10
    )


def _anti_top_trade_metrics(pnl: pd.Series) -> dict[str, float]:
    result = {}
    for pct in (0.01, 0.03, 0.05, 0.10):
        stressed = _remove_top_pnl(pnl, pct)
        label = int(pct * 100)
        result[f"pf_without_top_{label}pct"] = _profit_factor(stressed)
        if pct == 0.05:
            metrics = calculate_metrics(pd.DataFrame({"profit_loss": stressed}), 1000.0)
            result["net_profit_without_top_5pct"] = float(stressed.sum())
            result["max_drawdown_without_top_5pct"] = metrics.max_drawdown
    return result


def _remove_top_pnl(pnl: pd.Series, pct: float) -> pd.Series:
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0).reset_index(drop=True)
    if pnl.empty:
        return pnl
    remove_count = max(1, int(len(pnl) * pct))
    drop_index = pnl.sort_values(ascending=False).head(remove_count).index
    return pnl.drop(index=drop_index).sort_index().reset_index(drop=True)


def _profit_factor(pnl: pd.Series) -> float:
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))
    if gross_loss > 0:
        return gross_profit / gross_loss
    return float("inf") if gross_profit > 0 else 0.0


def _monthly_pnl(trades: pd.DataFrame, pnl_column: str) -> pd.Series:
    if trades.empty or "entry_time" not in trades.columns:
        return pd.Series(dtype=float)
    prepared = trades.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return pd.Series(dtype=float)
    prepared["month"] = prepared["entry_time"].dt.to_period("M").astype("string")
    return prepared.groupby("month")[pnl_column].sum()


def _average_trades_per_day(trades: pd.DataFrame, market_data: pd.DataFrame) -> float:
    if market_data.empty:
        days = _trade_days(trades)
    else:
        market_index = market_data.index if isinstance(market_data.index, pd.DatetimeIndex) else pd.DatetimeIndex([])
        days = len(pd.Series(market_index.date).drop_duplicates()) if len(market_index) else _trade_days(trades)
    return len(trades) / days if days else 0.0


def _trade_days(trades: pd.DataFrame) -> int:
    if trades.empty or "entry_time" not in trades.columns:
        return 0
    entry_time = pd.to_datetime(trades["entry_time"], errors="coerce").dropna()
    return int(len(pd.Series(entry_time.dt.date).drop_duplicates()))


def _safe_ratio_series(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator = pd.to_numeric(numerator, errors="coerce").fillna(0.0)
    denominator = pd.to_numeric(denominator, errors="coerce").fillna(0.0)
    ratio = numerator / denominator.where(denominator != 0)
    return ratio.fillna(float("inf")).replace([float("-inf")], 0.0)
