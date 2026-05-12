"""
Controlled paper-trading simulation for V50 research candidates.

The engine consumes locally generated backtest trades and turns them into
paper-order records with Axi-style lot sizing and costs. It never places real
orders and never imports the protected live execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml

from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_max_consecutive
from src.strategy_lab.v50_cost_aware import (
    AxiSizingConfig,
    CostProfile,
    apply_cost_aware_filter,
    axi_cost_components_for_lot,
    build_cost_aware_variants,
    lot_size_for_equity,
)


DEFAULT_PAPER_CONFIG_PATH = Path("config/paper_trading.yaml")
DEFAULT_PAPER_OUTPUT_DIR = Path("reports/paper")
DEFAULT_PAPER_TRADES_PATH = DEFAULT_PAPER_OUTPUT_DIR / "paper_trades.csv"
DEFAULT_PAPER_EQUITY_CURVE_PATH = DEFAULT_PAPER_OUTPUT_DIR / "paper_equity_curve.csv"
DEFAULT_PAPER_DAILY_SUMMARY_PATH = DEFAULT_PAPER_OUTPUT_DIR / "paper_daily_summary.csv"
DEFAULT_PAPER_SUMMARY_PATH = DEFAULT_PAPER_OUTPUT_DIR / "paper_summary.csv"

PAPER_SUMMARY_COLUMNS = [
    "strategy_name",
    "starting_equity",
    "ending_equity",
    "net_profit",
    "profit_factor_net",
    "max_dd_pct",
    "max_dd_eur",
    "total_trades",
    "trades_per_day",
    "win_rate",
    "avg_win",
    "avg_loss",
    "expectancy",
    "max_consecutive_losses",
    "worst_day",
    "worst_week",
    "worst_month",
    "months_positive",
    "months_negative",
    "no_trade_days",
    "max_no_trade_days",
    "time_to_1500_if_reached",
    "trades_to_1500_if_reached",
    "time_to_2000_if_reached",
    "trades_to_2000_if_reached",
    "time_to_002_lot_if_reached",
    "trades_to_002_lot_if_reached",
    "returned_below_1000_after_growth",
    "drawdown_over_8_pct",
    "drawdown_over_10_pct",
    "drawdown_over_12_pct",
    "equity_min",
    "equity_max",
    "lot_min",
    "lot_max",
]

PAPER_TRADE_COLUMNS = [
    "strategy_name",
    "paper_order_id",
    "entry_time",
    "exit_time",
    "symbol",
    "timeframe",
    "side",
    "session",
    "entry_price",
    "stop_loss",
    "take_profit",
    "signal_reason",
    "setup_type",
    "score_long",
    "score_short",
    "score",
    "risk_reward",
    "lot_size",
    "price_points",
    "gross_pnl_eur",
    "commission_eur",
    "spread_cost_eur",
    "slippage_cost_eur",
    "total_cost_eur",
    "pnl_eur",
    "equity_before",
    "equity_after",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_percent",
    "daily_pnl_after",
    "daily_trade_number",
    "daily_loss_streak",
]

PAPER_EQUITY_COLUMNS = [
    "strategy_name",
    "paper_order_id",
    "entry_time",
    "equity_before",
    "equity_after",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_percent",
    "lot_size",
    "pnl_eur",
]

PAPER_DAILY_COLUMNS = [
    "strategy_name",
    "date",
    "trades",
    "skipped_trades",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "ending_equity",
    "max_drawdown_eur",
    "max_drawdown_percent",
    "daily_stopped",
    "positive_day",
    "negative_day",
]


@dataclass(frozen=True)
class PaperTradingConfig:
    """Static paper configuration loaded from config/paper_trading.yaml."""

    strategy_name: str
    backup_strategy: str
    symbol: str
    base_timeframe: str
    live_mode: bool
    paper_mode: bool
    initial_equity: float
    min_lot: float
    lot_step: float
    equity_step: float
    max_lot: float
    commission_per_001_lot_per_side: float
    spread_pips: float
    slippage_pips: float
    conservative_slippage_pips: float
    max_trades_per_day: int
    max_daily_loss_pct: float
    max_consecutive_losses_day: int
    max_consecutive_losses_total_warning: int
    max_drawdown_warning_pct: float
    max_drawdown_stop_pct: float
    min_score_required: float
    no_trade_after_daily_stop: bool

    @property
    def sizing_config(self) -> AxiSizingConfig:
        """Return the equity ladder used by the paper engine."""
        return AxiSizingConfig(
            initial_equity_eur=self.initial_equity,
            min_lot=self.min_lot,
            lot_step=self.lot_step,
            equity_step_eur=self.equity_step,
            max_lot=self.max_lot,
        )

    @property
    def main_strategies(self) -> tuple[str, str]:
        """Return main and backup strategy names."""
        return (self.strategy_name, self.backup_strategy)


def load_paper_trading_config(path: str | Path = DEFAULT_PAPER_CONFIG_PATH) -> PaperTradingConfig:
    """Load and validate the research-only paper configuration."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Paper trading config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    if not isinstance(raw, dict):
        raise ValueError("paper_trading.yaml must contain a YAML dictionary")

    config = PaperTradingConfig(
        strategy_name=str(raw.get("strategy_name", "")),
        backup_strategy=str(raw.get("backup_strategy", "")),
        symbol=str(raw.get("symbol", "XAUUSD")),
        base_timeframe=str(raw.get("base_timeframe", "15m")),
        live_mode=bool(raw.get("live_mode", False)),
        paper_mode=bool(raw.get("paper_mode", True)),
        initial_equity=float(raw.get("initial_equity", 1000.0)),
        min_lot=float(raw.get("min_lot", 0.01)),
        lot_step=float(raw.get("lot_step", 0.01)),
        equity_step=float(raw.get("equity_step", 1000.0)),
        max_lot=float(raw.get("max_lot", 0.10)),
        commission_per_001_lot_per_side=float(raw.get("commission_per_001_lot_per_side", 0.04)),
        spread_pips=float(raw.get("spread_pips", 0.0)),
        slippage_pips=float(raw.get("slippage_pips", 0.0)),
        conservative_slippage_pips=float(raw.get("conservative_slippage_pips", 0.1)),
        max_trades_per_day=int(raw.get("max_trades_per_day", 2)),
        max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 3.0)),
        max_consecutive_losses_day=int(raw.get("max_consecutive_losses_day", 2)),
        max_consecutive_losses_total_warning=int(raw.get("max_consecutive_losses_total_warning", 8)),
        max_drawdown_warning_pct=float(raw.get("max_drawdown_warning_pct", 8.0)),
        max_drawdown_stop_pct=float(raw.get("max_drawdown_stop_pct", 12.0)),
        min_score_required=float(raw.get("min_score_required", 72.0)),
        no_trade_after_daily_stop=bool(raw.get("no_trade_after_daily_stop", True)),
    )
    validate_paper_config(config)
    return config


def validate_paper_config(config: PaperTradingConfig) -> None:
    """Fail fast if the file is not safe for paper-only research."""
    if config.live_mode:
        raise ValueError("paper_trading.yaml must keep live_mode=false")
    if not config.paper_mode:
        raise ValueError("paper_trading.yaml must keep paper_mode=true")
    if config.strategy_name != "proxy_hardened_no_worst_hours":
        raise ValueError("Main paper strategy must be proxy_hardened_no_worst_hours")
    if config.backup_strategy != "proxy_hardened_no_worst_hours_high_margin":
        raise ValueError("Backup paper strategy must be proxy_hardened_no_worst_hours_high_margin")
    if config.initial_equity <= 0 or config.min_lot <= 0 or config.lot_step <= 0:
        raise ValueError("Paper sizing values must be positive")
    if config.max_trades_per_day <= 0:
        raise ValueError("max_trades_per_day must be positive")


def run_controlled_paper_simulation(
    source_results: dict[str, BacktestResult],
    config: PaperTradingConfig,
    market_data: pd.DataFrame | None = None,
    strategy_names: Iterable[str] | None = None,
    output_trades_path: str | Path = DEFAULT_PAPER_TRADES_PATH,
    output_equity_path: str | Path = DEFAULT_PAPER_EQUITY_CURVE_PATH,
    output_daily_path: str | Path = DEFAULT_PAPER_DAILY_SUMMARY_PATH,
    output_summary_path: str | Path = DEFAULT_PAPER_SUMMARY_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Simulate configured paper strategies and export reports."""
    validate_paper_config(config)
    names = tuple(strategy_names or config.main_strategies)
    sources = build_paper_trade_sources(source_results, names, config)
    market_days = market_trading_days(market_data)

    summary_rows: list[dict] = []
    trade_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []
    daily_frames: list[pd.DataFrame] = []

    for strategy_name in names:
        trades = sources.get(strategy_name, pd.DataFrame())
        paper_trades, equity_curve, daily_summary, summary_row = simulate_paper_strategy(
            trades=trades,
            strategy_name=strategy_name,
            config=config,
            market_days=market_days,
        )
        summary_rows.append(summary_row)
        trade_frames.append(paper_trades)
        equity_frames.append(equity_curve)
        daily_frames.append(daily_summary)

    summary = pd.DataFrame(summary_rows, columns=PAPER_SUMMARY_COLUMNS)
    paper_trades = _concat_or_empty(trade_frames, PAPER_TRADE_COLUMNS)
    equity_curve = _concat_or_empty(equity_frames, PAPER_EQUITY_COLUMNS)
    daily_summary = _concat_or_empty(daily_frames, PAPER_DAILY_COLUMNS)

    export_dataframe(paper_trades, output_trades_path)
    export_dataframe(equity_curve, output_equity_path)
    export_dataframe(daily_summary, output_daily_path)
    export_dataframe(summary, output_summary_path)
    return summary, paper_trades, equity_curve, daily_summary


def build_paper_trade_sources(
    source_results: dict[str, BacktestResult],
    strategy_names: Iterable[str],
    config: PaperTradingConfig,
) -> dict[str, pd.DataFrame]:
    """Build raw trade inputs for main and backup paper candidates."""
    names = set(strategy_names)
    sources: dict[str, pd.DataFrame] = {}
    if "proxy_hardened_no_worst_hours" in names and "proxy_hardened_no_worst_hours" in source_results:
        sources["proxy_hardened_no_worst_hours"] = source_results["proxy_hardened_no_worst_hours"].trades.copy()
    if "proxy_hardened_score_plus" in names and "proxy_hardened_score_plus" in source_results:
        sources["proxy_hardened_score_plus"] = source_results["proxy_hardened_score_plus"].trades.copy()
    if "proxy_hardened_no_worst_hours_high_margin" in names:
        base = source_results.get("proxy_hardened_no_worst_hours")
        if base is not None:
            variant = next(
                item for item in build_cost_aware_variants() if item.variant_name == "costaware_high_margin_combo"
            )
            profile = paper_cost_profile(config)
            sources["proxy_hardened_no_worst_hours_high_margin"] = apply_cost_aware_filter(
                base.trades,
                variant,
                profile,
            )
    return sources


def simulate_paper_strategy(
    trades: pd.DataFrame,
    strategy_name: str,
    config: PaperTradingConfig,
    market_days: list[pd.Timestamp] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Simulate one strategy with paper controls and Axi-style costs."""
    prepared = prepare_trade_input(trades)
    if prepared.empty:
        empty_trades = pd.DataFrame(columns=PAPER_TRADE_COLUMNS)
        empty_equity = pd.DataFrame(columns=PAPER_EQUITY_COLUMNS)
        daily = build_daily_summary(strategy_name, empty_trades, config, market_days or [])
        return empty_trades, empty_equity, daily, build_summary_row(strategy_name, empty_trades, daily, config)

    sizing = config.sizing_config
    profile = paper_cost_profile(config)
    equity = config.initial_equity
    running_high = equity
    current_day = None
    day_start_equity = equity
    daily_pnl = 0.0
    daily_trade_count = 0
    daily_loss_streak = 0
    daily_stopped = False
    skipped_by_day: dict[pd.Timestamp, int] = {}
    rows = []

    for _, trade in prepared.iterrows():
        entry_time = pd.to_datetime(trade["entry_time"])
        trade_day = pd.Timestamp(entry_time.date())
        if current_day != trade_day:
            current_day = trade_day
            day_start_equity = equity
            daily_pnl = 0.0
            daily_trade_count = 0
            daily_loss_streak = 0
            daily_stopped = False

        if daily_stopped or daily_trade_count >= config.max_trades_per_day:
            skipped_by_day[trade_day] = skipped_by_day.get(trade_day, 0) + 1
            continue

        if _daily_loss_limit_reached(daily_pnl, day_start_equity, config):
            daily_stopped = bool(config.no_trade_after_daily_stop)
            skipped_by_day[trade_day] = skipped_by_day.get(trade_day, 0) + 1
            continue

        lot = lot_size_for_equity(equity, sizing)
        price_points = trade_price_points(trade)
        gross_pnl = price_points * (lot / 0.01) * sizing.eur_per_price_point_per_001_lot
        spread_cost, slippage_cost, commission_cost = axi_cost_components_for_lot(profile, lot)
        total_cost = spread_cost + slippage_cost + commission_cost
        net_pnl = gross_pnl - total_cost
        equity_before = equity
        equity += net_pnl
        running_high = max(running_high, equity)
        drawdown = running_high - equity
        drawdown_percent = drawdown / running_high * 100 if running_high > 0 else 0.0
        daily_pnl += net_pnl
        daily_trade_count += 1
        daily_loss_streak = daily_loss_streak + 1 if net_pnl < 0 else 0
        if (
            daily_loss_streak >= config.max_consecutive_losses_day
            or _daily_loss_limit_reached(daily_pnl, day_start_equity, config)
        ):
            daily_stopped = bool(config.no_trade_after_daily_stop)

        side = str(trade.get("side", "UNKNOWN")).upper()
        score_long = _float_or_none(trade.get("score_long"))
        score_short = _float_or_none(trade.get("score_short"))
        score = score_long if side == "BUY" else score_short if side == "SELL" else max(score_long, score_short)
        rows.append(
            {
                "strategy_name": strategy_name,
                "paper_order_id": f"{strategy_name}-{len(rows) + 1:06d}",
                "entry_time": entry_time,
                "exit_time": trade.get("exit_time", pd.NaT),
                "symbol": trade.get("symbol", config.symbol),
                "timeframe": trade.get("timeframe", config.base_timeframe),
                "side": side,
                "session": str(trade.get("session", "UNKNOWN")).upper(),
                "entry_price": _float_or_none(trade.get("entry_price")),
                "stop_loss": _float_or_none(trade.get("stop_loss")),
                "take_profit": _float_or_none(trade.get("take_profit")),
                "signal_reason": _first_text(trade, ("signal_reason", "reason", "reason_entry")),
                "setup_type": trade.get("setup_type", pd.NA),
                "score_long": score_long,
                "score_short": score_short,
                "score": score,
                "risk_reward": _float_or_none(trade.get("risk_reward")),
                "lot_size": lot,
                "price_points": price_points,
                "gross_pnl_eur": gross_pnl,
                "commission_eur": commission_cost,
                "spread_cost_eur": spread_cost,
                "slippage_cost_eur": slippage_cost,
                "total_cost_eur": total_cost,
                "pnl_eur": net_pnl,
                "equity_before": equity_before,
                "equity_after": equity,
                "running_equity_high": running_high,
                "drawdown_eur": drawdown,
                "drawdown_percent": drawdown_percent,
                "daily_pnl_after": daily_pnl,
                "daily_trade_number": daily_trade_count,
                "daily_loss_streak": daily_loss_streak,
            }
        )

    paper_trades = pd.DataFrame(rows, columns=PAPER_TRADE_COLUMNS)
    daily_summary = build_daily_summary(strategy_name, paper_trades, config, market_days or [], skipped_by_day)
    equity_curve = paper_trades[PAPER_EQUITY_COLUMNS].copy() if not paper_trades.empty else pd.DataFrame(columns=PAPER_EQUITY_COLUMNS)
    summary_row = build_summary_row(strategy_name, paper_trades, daily_summary, config)
    return paper_trades, equity_curve, daily_summary, summary_row


def paper_cost_profile(config: PaperTradingConfig) -> CostProfile:
    """Build a static Axi Pro cost profile from paper config."""
    return CostProfile(
        name="axi_pro_paper_config",
        spread_points=0.0,
        slippage_points=0.0,
        commission_per_trade=0.0,
        commission_per_lot=0.0,
        note="Axi Pro paper research profile from config/paper_trading.yaml.",
        spread_pips=config.spread_pips,
        slippage_pips=config.slippage_pips,
        commission_per_001_lot_per_side=config.commission_per_001_lot_per_side,
        profile_group="axi",
    )


def prepare_trade_input(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize source trade rows before paper simulation."""
    if trades is None or trades.empty:
        return pd.DataFrame()
    prepared = trades.copy()
    prepared["entry_time"] = pd.to_datetime(prepared.get("entry_time"), errors="coerce")
    prepared["exit_time"] = pd.to_datetime(prepared.get("exit_time"), errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    return prepared


def build_daily_summary(
    strategy_name: str,
    paper_trades: pd.DataFrame,
    config: PaperTradingConfig,
    market_days: list[pd.Timestamp],
    skipped_by_day: dict[pd.Timestamp, int] | None = None,
) -> pd.DataFrame:
    """Return one row per market/trade day with paper P&L."""
    skipped_by_day = skipped_by_day or {}
    days = list(market_days)
    if not days and not paper_trades.empty:
        dates = pd.to_datetime(paper_trades["entry_time"], errors="coerce").dropna().dt.date.unique()
        days = [pd.Timestamp(day) for day in sorted(dates)]
    if not days:
        return pd.DataFrame(columns=PAPER_DAILY_COLUMNS)

    if not paper_trades.empty:
        prepared = paper_trades.copy()
        prepared["date"] = pd.to_datetime(prepared["entry_time"], errors="coerce").dt.normalize()
    else:
        prepared = pd.DataFrame(columns=list(paper_trades.columns) + ["date"])

    rows = []
    last_equity = config.initial_equity
    for day in days:
        day = pd.Timestamp(day).normalize()
        group = prepared[prepared["date"] == day]
        pnl = pd.to_numeric(group.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        if not group.empty:
            last_equity = float(pd.to_numeric(group["equity_after"], errors="coerce").iloc[-1])
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(abs(pnl[pnl < 0].sum()))
        rows.append(
            {
                "strategy_name": strategy_name,
                "date": day.date().isoformat(),
                "trades": int(len(group)),
                "skipped_trades": int(skipped_by_day.get(day, 0)),
                "net_profit": float(pnl.sum()),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "ending_equity": last_equity,
                "max_drawdown_eur": float(pd.to_numeric(group.get("drawdown_eur", pd.Series(dtype=float)), errors="coerce").max()) if not group.empty else 0.0,
                "max_drawdown_percent": float(pd.to_numeric(group.get("drawdown_percent", pd.Series(dtype=float)), errors="coerce").max()) if not group.empty else 0.0,
                "daily_stopped": bool(skipped_by_day.get(day, 0) > 0),
                "positive_day": bool(pnl.sum() > 0),
                "negative_day": bool(pnl.sum() < 0),
            }
        )
    return pd.DataFrame(rows, columns=PAPER_DAILY_COLUMNS)


def build_summary_row(
    strategy_name: str,
    paper_trades: pd.DataFrame,
    daily_summary: pd.DataFrame,
    config: PaperTradingConfig,
) -> dict:
    """Calculate high-level paper metrics for one strategy."""
    if paper_trades.empty:
        return {column: 0 for column in PAPER_SUMMARY_COLUMNS} | {
            "strategy_name": strategy_name,
            "starting_equity": config.initial_equity,
            "ending_equity": config.initial_equity,
            "equity_min": config.initial_equity,
            "equity_max": config.initial_equity,
        }

    pnl = pd.to_numeric(paper_trades["pnl_eur"], errors="coerce").fillna(0.0)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    entry_time = pd.to_datetime(paper_trades["entry_time"], errors="coerce")
    first_trade_time = entry_time.dropna().min()
    period_pnl = _period_pnl(paper_trades)
    daily_pnl = pd.to_numeric(daily_summary.get("net_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    no_trade_days = int((pd.to_numeric(daily_summary.get("trades", pd.Series(dtype=float)), errors="coerce").fillna(0) == 0).sum())

    return {
        "strategy_name": strategy_name,
        "starting_equity": config.initial_equity,
        "ending_equity": float(paper_trades["equity_after"].iloc[-1]),
        "net_profit": float(pnl.sum()),
        "profit_factor_net": gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "max_dd_pct": float(pd.to_numeric(paper_trades["drawdown_percent"], errors="coerce").max()),
        "max_dd_eur": float(pd.to_numeric(paper_trades["drawdown_eur"], errors="coerce").max()),
        "total_trades": int(len(paper_trades)),
        "trades_per_day": len(paper_trades) / len(daily_summary) if len(daily_summary) else 0.0,
        "win_rate": len(wins) / len(paper_trades) * 100 if len(paper_trades) else 0.0,
        "avg_win": float(wins.mean()) if not wins.empty else 0.0,
        "avg_loss": float(losses.mean()) if not losses.empty else 0.0,
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "max_consecutive_losses": int(calculate_max_consecutive(pnl, positive=False)),
        "worst_day": float(daily_pnl.min()) if len(daily_pnl) else 0.0,
        "worst_week": float(period_pnl["W"].min()) if not period_pnl["W"].empty else 0.0,
        "worst_month": float(period_pnl["M"].min()) if not period_pnl["M"].empty else 0.0,
        "months_positive": int((period_pnl["M"] > 0).sum()) if not period_pnl["M"].empty else 0,
        "months_negative": int((period_pnl["M"] < 0).sum()) if not period_pnl["M"].empty else 0,
        "no_trade_days": no_trade_days,
        "max_no_trade_days": max_consecutive_no_trade_days(daily_summary),
        "time_to_1500_if_reached": _time_to_equity(paper_trades, first_trade_time, 1500.0)[0],
        "trades_to_1500_if_reached": _time_to_equity(paper_trades, first_trade_time, 1500.0)[1],
        "time_to_2000_if_reached": _time_to_equity(paper_trades, first_trade_time, 2000.0)[0],
        "trades_to_2000_if_reached": _time_to_equity(paper_trades, first_trade_time, 2000.0)[1],
        "time_to_002_lot_if_reached": _time_to_lot(paper_trades, first_trade_time, 0.02)[0],
        "trades_to_002_lot_if_reached": _time_to_lot(paper_trades, first_trade_time, 0.02)[1],
        "returned_below_1000_after_growth": returned_below_initial_after_growth(paper_trades, config.initial_equity),
        "drawdown_over_8_pct": bool(pd.to_numeric(paper_trades["drawdown_percent"], errors="coerce").ge(8.0).any()),
        "drawdown_over_10_pct": bool(pd.to_numeric(paper_trades["drawdown_percent"], errors="coerce").ge(10.0).any()),
        "drawdown_over_12_pct": bool(pd.to_numeric(paper_trades["drawdown_percent"], errors="coerce").ge(12.0).any()),
        "equity_min": float(pd.to_numeric(paper_trades["equity_after"], errors="coerce").min()),
        "equity_max": float(pd.to_numeric(paper_trades["equity_after"], errors="coerce").max()),
        "lot_min": float(pd.to_numeric(paper_trades["lot_size"], errors="coerce").min()),
        "lot_max": float(pd.to_numeric(paper_trades["lot_size"], errors="coerce").max()),
    }


def market_trading_days(market_data: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Return sorted market dates from a local OHLCV dataframe."""
    if market_data is None or market_data.empty or not isinstance(market_data.index, pd.DatetimeIndex):
        return []
    dates = pd.Series(market_data.index.normalize()).drop_duplicates().sort_values()
    return [pd.Timestamp(date) for date in dates]


def trade_price_points(trade: pd.Series) -> float:
    """Return raw XAU price points from entry to exit with side direction."""
    entry = pd.to_numeric(trade.get("entry_price"), errors="coerce")
    exit_price = pd.to_numeric(trade.get("exit_price"), errors="coerce")
    if pd.isna(entry) or pd.isna(exit_price):
        pnl = pd.to_numeric(trade.get("profit_loss"), errors="coerce")
        size = pd.to_numeric(trade.get("position_size"), errors="coerce")
        return float(pnl / size) if pd.notna(pnl) and pd.notna(size) and size else 0.0
    side = str(trade.get("side", "")).upper()
    return float(entry - exit_price) if side == "SELL" else float(exit_price - entry)


def max_consecutive_no_trade_days(daily_summary: pd.DataFrame) -> int:
    """Return longest run of days with zero executed paper trades."""
    if daily_summary.empty or "trades" not in daily_summary.columns:
        return 0
    longest = current = 0
    for trades in pd.to_numeric(daily_summary["trades"], errors="coerce").fillna(0):
        if int(trades) == 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def returned_below_initial_after_growth(paper_trades: pd.DataFrame, initial_equity: float) -> bool:
    """Return True if equity grows above initial and later falls below initial."""
    equity = pd.to_numeric(paper_trades.get("equity_after", pd.Series(dtype=float)), errors="coerce").dropna()
    if equity.empty:
        return False
    grew = False
    for value in equity:
        if value > initial_equity:
            grew = True
        if grew and value < initial_equity:
            return True
    return False


def export_dataframe(df: pd.DataFrame, path: str | Path) -> Path:
    """Export a CSV, creating parent directories."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def _period_pnl(paper_trades: pd.DataFrame) -> dict[str, pd.Series]:
    prepared = paper_trades.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return {"W": pd.Series(dtype=float), "M": pd.Series(dtype=float)}
    return {
        "W": prepared.groupby(prepared["entry_time"].dt.to_period("W"))["pnl_eur"].sum(),
        "M": prepared.groupby(prepared["entry_time"].dt.to_period("M"))["pnl_eur"].sum(),
    }


def _time_to_equity(
    paper_trades: pd.DataFrame,
    first_trade_time: pd.Timestamp | None,
    threshold: float,
) -> tuple[int | pd._libs.missing.NAType, int | pd._libs.missing.NAType]:
    reached = paper_trades[pd.to_numeric(paper_trades["equity_after"], errors="coerce") >= threshold]
    if reached.empty:
        return pd.NA, pd.NA
    first = reached.iloc[0]
    reached_time = pd.to_datetime(first["entry_time"], errors="coerce")
    days = int((reached_time - first_trade_time).days) if pd.notna(reached_time) and pd.notna(first_trade_time) else pd.NA
    return days, int(first.name + 1)


def _time_to_lot(
    paper_trades: pd.DataFrame,
    first_trade_time: pd.Timestamp | None,
    lot_threshold: float,
) -> tuple[int | pd._libs.missing.NAType, int | pd._libs.missing.NAType]:
    reached = paper_trades[pd.to_numeric(paper_trades["lot_size"], errors="coerce") >= lot_threshold]
    if reached.empty:
        return pd.NA, pd.NA
    first = reached.iloc[0]
    reached_time = pd.to_datetime(first["entry_time"], errors="coerce")
    days = int((reached_time - first_trade_time).days) if pd.notna(reached_time) and pd.notna(first_trade_time) else pd.NA
    return days, int(first.name + 1)


def _daily_loss_limit_reached(daily_pnl: float, day_start_equity: float, config: PaperTradingConfig) -> bool:
    return daily_pnl <= -(day_start_equity * config.max_daily_loss_pct / 100.0)


def _concat_or_empty(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=columns)
    return pd.concat(non_empty, ignore_index=True)


def _float_or_none(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _first_text(row: pd.Series, columns: tuple[str, ...]) -> str | None:
    for column in columns:
        value = row.get(column)
        if pd.notna(value) and str(value):
            return str(value)
    return None
