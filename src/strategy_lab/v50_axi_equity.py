"""
Axi Pro paper/equity simulation for V50 research candidates.

This module recalculates trade P&L using an explicit lot-size ladder instead
of the risk-sized P&L from the generic backtester. It is research-only and does
not execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_max_consecutive
from src.strategy_lab.v50_cost_aware import (
    AxiSizingConfig,
    CostProfile,
    axi_cost_components_for_lot,
    build_cost_aware_variants,
    build_cost_profiles,
    lot_size_for_equity,
    apply_cost_aware_filter,
)


DEFAULT_AXI_EQUITY_SIMULATION_PATH = Path("reports/strategy_lab/v50_axi_equity_simulation.csv")
DEFAULT_AXI_EQUITY_CURVE_PATH = Path("reports/strategy_lab/v50_axi_equity_curve.csv")
DEFAULT_AXI_MONTHLY_EQUITY_PATH = Path("reports/strategy_lab/v50_axi_monthly_equity.csv")

AXI_EQUITY_STRATEGY_NAMES = (
    "v50_proxy_balanced_candidate",
    "proxy_hardened_score_plus",
    "proxy_hardened_no_worst_hours",
    "proxy_hardened_no_worst_hours_high_margin",
)
AXI_EQUITY_SCENARIO_NAMES = (
    "axi_realistic_slippage_0_0",
    "axi_conservative_slippage_0_1",
)
SUMMARY_COLUMNS = [
    "strategy_name",
    "scenario",
    "starting_equity",
    "ending_equity",
    "net_profit_eur",
    "max_drawdown_eur",
    "max_drawdown_percent",
    "total_trades",
    "trades_per_day",
    "win_rate",
    "profit_factor_net",
    "average_trade_eur",
    "average_win_eur",
    "average_loss_eur",
    "max_consecutive_losses",
    "worst_day",
    "worst_week",
    "worst_month",
    "best_month",
    "months_positive",
    "months_negative",
    "time_to_2000_if_reached",
    "trades_to_2000_if_reached",
    "equity_min",
    "equity_max",
    "lot_min",
    "lot_max",
]
EQUITY_CURVE_COLUMNS = [
    "strategy_name",
    "scenario",
    "trade_number",
    "entry_time",
    "exit_time",
    "side",
    "session",
    "lot_size",
    "price_points",
    "gross_profit_eur",
    "commission_eur",
    "spread_cost_eur",
    "slippage_cost_eur",
    "total_cost_eur",
    "net_profit_eur",
    "equity_before",
    "equity_after",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_percent",
]
MONTHLY_COLUMNS = [
    "strategy_name",
    "scenario",
    "month",
    "trades",
    "net_profit_eur",
    "gross_profit_eur",
    "gross_loss_eur",
    "profit_factor_net",
    "ending_equity",
    "max_drawdown_eur",
    "max_consecutive_losses",
]


@dataclass(frozen=True)
class AxiEquityScenario:
    """One Axi paper/equity cost scenario."""

    name: str
    profile: CostProfile


def build_axi_equity_scenarios() -> list[AxiEquityScenario]:
    """Return realistic and conservative Axi equity scenarios."""
    profiles = {profile.name: profile for profile in build_cost_profiles()}
    return [
        AxiEquityScenario("axi_realistic_slippage_0_0", profiles["axi_pro_realistic"]),
        AxiEquityScenario("axi_conservative_slippage_0_1", profiles["axi_pro_conservative"]),
    ]


def run_axi_equity_simulation(
    source_results: dict[str, BacktestResult],
    market_data: pd.DataFrame | None = None,
    scenarios: list[AxiEquityScenario] | None = None,
    sizing_config: AxiSizingConfig | None = None,
    output_summary_path: str | Path = DEFAULT_AXI_EQUITY_SIMULATION_PATH,
    output_curve_path: str | Path = DEFAULT_AXI_EQUITY_CURVE_PATH,
    output_monthly_path: str | Path = DEFAULT_AXI_MONTHLY_EQUITY_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run Axi equity simulation and export summary/curve/monthly CSVs."""
    if scenarios is None:
        scenarios = build_axi_equity_scenarios()
    if sizing_config is None:
        sizing_config = AxiSizingConfig()

    strategy_trades = _strategy_trade_sources(source_results, scenarios[0].profile)
    trading_days = _market_trading_days(market_data)
    summary_rows = []
    curves = []
    monthlies = []

    for strategy_name, trades in strategy_trades.items():
        for scenario in scenarios:
            curve = simulate_axi_equity_curve(
                trades=trades,
                strategy_name=strategy_name,
                scenario=scenario,
                sizing_config=sizing_config,
            )
            summary_rows.append(_summary_row(strategy_name, scenario.name, curve, sizing_config, trading_days))
            curves.append(curve)
            monthlies.append(_monthly_rows(strategy_name, scenario.name, curve))

    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    equity_curve = pd.concat(curves, ignore_index=True) if curves else pd.DataFrame(columns=EQUITY_CURVE_COLUMNS)
    monthly = pd.concat(monthlies, ignore_index=True) if monthlies else pd.DataFrame(columns=MONTHLY_COLUMNS)

    _export(summary, output_summary_path)
    _export(equity_curve, output_curve_path)
    _export(monthly, output_monthly_path)
    return summary, equity_curve, monthly


def simulate_axi_equity_curve(
    trades: pd.DataFrame,
    strategy_name: str,
    scenario: AxiEquityScenario,
    sizing_config: AxiSizingConfig | None = None,
) -> pd.DataFrame:
    """Return one equity-curve row per closed trade."""
    if sizing_config is None:
        sizing_config = AxiSizingConfig()
    prepared = _prepare_trades(trades)
    if prepared.empty:
        return pd.DataFrame(columns=EQUITY_CURVE_COLUMNS)

    equity = sizing_config.initial_equity_eur
    running_high = equity
    rows = []
    for trade_number, (_, trade) in enumerate(prepared.iterrows(), start=1):
        lot = lot_size_for_equity(equity, sizing_config)
        price_points = _trade_price_points(trade)
        gross_profit = price_points * (lot / 0.01) * sizing_config.eur_per_price_point_per_001_lot
        spread_cost, slippage_cost, commission_cost = axi_cost_components_for_lot(scenario.profile, lot)
        total_cost = spread_cost + slippage_cost + commission_cost
        net_profit = gross_profit - total_cost
        equity_before = equity
        equity += net_profit
        running_high = max(running_high, equity)
        drawdown = running_high - equity
        drawdown_percent = drawdown / running_high * 100 if running_high > 0 else 0.0
        rows.append(
            {
                "strategy_name": strategy_name,
                "scenario": scenario.name,
                "trade_number": trade_number,
                "entry_time": trade["entry_time"],
                "exit_time": trade.get("exit_time", pd.NaT),
                "side": trade.get("side", "UNKNOWN"),
                "session": trade.get("session", "UNKNOWN"),
                "lot_size": lot,
                "price_points": price_points,
                "gross_profit_eur": gross_profit,
                "commission_eur": commission_cost,
                "spread_cost_eur": spread_cost,
                "slippage_cost_eur": slippage_cost,
                "total_cost_eur": total_cost,
                "net_profit_eur": net_profit,
                "equity_before": equity_before,
                "equity_after": equity,
                "running_equity_high": running_high,
                "drawdown_eur": drawdown,
                "drawdown_percent": drawdown_percent,
            }
        )
    return pd.DataFrame(rows, columns=EQUITY_CURVE_COLUMNS)


def _strategy_trade_sources(
    source_results: dict[str, BacktestResult],
    high_margin_profile: CostProfile,
) -> dict[str, pd.DataFrame]:
    strategy_trades = {}
    for strategy_name in AXI_EQUITY_STRATEGY_NAMES:
        if strategy_name == "proxy_hardened_no_worst_hours_high_margin":
            source = source_results.get("proxy_hardened_no_worst_hours")
            if source is None:
                continue
            variant = next(
                item for item in build_cost_aware_variants() if item.variant_name == "costaware_high_margin_combo"
            )
            strategy_trades[strategy_name] = apply_cost_aware_filter(source.trades, variant, high_margin_profile)
            continue
        result = source_results.get(strategy_name)
        if result is not None:
            strategy_trades[strategy_name] = result.trades.copy()
    return strategy_trades


def _summary_row(
    strategy_name: str,
    scenario_name: str,
    curve: pd.DataFrame,
    sizing_config: AxiSizingConfig,
    trading_days: int = 0,
) -> dict:
    if curve.empty:
        return {column: 0 for column in SUMMARY_COLUMNS} | {
            "strategy_name": strategy_name,
            "scenario": scenario_name,
            "starting_equity": sizing_config.initial_equity_eur,
            "ending_equity": sizing_config.initial_equity_eur,
        }

    pnl = pd.to_numeric(curve["net_profit_eur"], errors="coerce").fillna(0.0)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    entry_time = pd.to_datetime(curve["entry_time"], errors="coerce")
    first_trade_time = entry_time.dropna().min()
    reached = curve[pd.to_numeric(curve["equity_after"], errors="coerce") >= 2000.0]
    if reached.empty:
        time_to_2000 = pd.NA
        trades_to_2000 = pd.NA
    else:
        first_reached = reached.iloc[0]
        reached_time = pd.to_datetime(first_reached["entry_time"], errors="coerce")
        time_to_2000 = int((reached_time - first_trade_time).days) if pd.notna(reached_time) and pd.notna(first_trade_time) else pd.NA
        trades_to_2000 = int(first_reached["trade_number"])

    return {
        "strategy_name": strategy_name,
        "scenario": scenario_name,
        "starting_equity": sizing_config.initial_equity_eur,
        "ending_equity": float(curve["equity_after"].iloc[-1]),
        "net_profit_eur": float(pnl.sum()),
        "max_drawdown_eur": float(pd.to_numeric(curve["drawdown_eur"], errors="coerce").max()),
        "max_drawdown_percent": float(pd.to_numeric(curve["drawdown_percent"], errors="coerce").max()),
        "total_trades": int(len(curve)),
        "trades_per_day": len(curve) / trading_days if trading_days else _trades_per_day(curve),
        "win_rate": len(wins) / len(curve) * 100 if len(curve) else 0.0,
        "profit_factor_net": gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "average_trade_eur": float(pnl.mean()) if len(curve) else 0.0,
        "average_win_eur": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss_eur": float(losses.mean()) if not losses.empty else 0.0,
        "max_consecutive_losses": int(calculate_max_consecutive(pnl, positive=False)),
        "worst_day": _period_pnl(curve, "D").min(),
        "worst_week": _period_pnl(curve, "W").min(),
        "worst_month": _period_pnl(curve, "M").min(),
        "best_month": _period_pnl(curve, "M").max(),
        "months_positive": int((_period_pnl(curve, "M") > 0).sum()),
        "months_negative": int((_period_pnl(curve, "M") < 0).sum()),
        "time_to_2000_if_reached": time_to_2000,
        "trades_to_2000_if_reached": trades_to_2000,
        "equity_min": float(pd.to_numeric(curve["equity_after"], errors="coerce").min()),
        "equity_max": float(pd.to_numeric(curve["equity_after"], errors="coerce").max()),
        "lot_min": float(pd.to_numeric(curve["lot_size"], errors="coerce").min()),
        "lot_max": float(pd.to_numeric(curve["lot_size"], errors="coerce").max()),
    }


def _monthly_rows(strategy_name: str, scenario_name: str, curve: pd.DataFrame) -> pd.DataFrame:
    if curve.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    prepared = curve.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    prepared["month"] = prepared["entry_time"].dt.to_period("M").astype("string")
    rows = []
    for month, group in prepared.groupby("month", sort=True):
        pnl = pd.to_numeric(group["net_profit_eur"], errors="coerce").fillna(0.0)
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(abs(pnl[pnl < 0].sum()))
        rows.append(
            {
                "strategy_name": strategy_name,
                "scenario": scenario_name,
                "month": month,
                "trades": int(len(group)),
                "net_profit_eur": float(pnl.sum()),
                "gross_profit_eur": gross_profit,
                "gross_loss_eur": gross_loss,
                "profit_factor_net": gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
                "ending_equity": float(group["equity_after"].iloc[-1]),
                "max_drawdown_eur": float(pd.to_numeric(group["drawdown_eur"], errors="coerce").max()),
                "max_consecutive_losses": int(calculate_max_consecutive(pnl, positive=False)),
            }
        )
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS)


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        return result
    result["entry_time"] = pd.to_datetime(result.get("entry_time"), errors="coerce")
    result["exit_time"] = pd.to_datetime(result.get("exit_time"), errors="coerce")
    result = result.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    return result


def _trade_price_points(trade: pd.Series) -> float:
    entry = pd.to_numeric(trade.get("entry_price"), errors="coerce")
    exit_price = pd.to_numeric(trade.get("exit_price"), errors="coerce")
    if pd.isna(entry) or pd.isna(exit_price):
        pnl = pd.to_numeric(trade.get("profit_loss"), errors="coerce")
        size = pd.to_numeric(trade.get("position_size"), errors="coerce")
        return float(pnl / size) if pd.notna(pnl) and pd.notna(size) and size else 0.0
    side = str(trade.get("side", "")).upper()
    if side == "SELL":
        return float(entry - exit_price)
    return float(exit_price - entry)


def _period_pnl(curve: pd.DataFrame, freq: str) -> pd.Series:
    if curve.empty:
        return pd.Series(dtype=float)
    prepared = curve.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return pd.Series(dtype=float)
    return prepared.groupby(prepared["entry_time"].dt.to_period(freq))["net_profit_eur"].sum()


def _trades_per_day(curve: pd.DataFrame) -> float:
    if curve.empty:
        return 0.0
    entry_time = pd.to_datetime(curve["entry_time"], errors="coerce").dropna()
    if entry_time.empty:
        return 0.0
    days = max(1, len(pd.Series(entry_time.dt.date).drop_duplicates()))
    return len(curve) / days


def _market_trading_days(market_data: pd.DataFrame | None) -> int:
    if market_data is None or market_data.empty:
        return 0
    if not isinstance(market_data.index, pd.DatetimeIndex):
        return 0
    return int(len(pd.Series(market_data.index.date).drop_duplicates()))


def _export(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
