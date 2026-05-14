"""
Local paper-forward engine for the frozen high-margin V50 candidate.

The engine evaluates the latest closed local candle, records paper decisions,
and updates simulated open/closed paper trades. It never imports the protected
live execution layer and never sends orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import re

import pandas as pd

from src.paper.paper_candidate import (
    PAPER_MAIN_STRATEGY,
    PaperCandidateConfig,
    load_paper_candidate_config,
)
from src.paper.paper_engine import (
    PaperTradingConfig,
    load_paper_trading_config,
    paper_cost_profile,
)
from src.paper.paper_monitor import current_consecutive_losses, max_consecutive_losses, profit_factor
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.v50_cost_aware import (
    axi_cost_components_for_lot,
    build_cost_aware_variants,
    lot_size_for_equity,
)
from src.strategy_lab.v50_proxy_hardening import build_proxy_hardening_variants
from src.strategy_lab.v50_realtime_loss_proxy_sweep import make_realtime_loss_proxy_signal_generator


DEFAULT_FORWARD_OUTPUT_DIR = Path("reports/paper_forward")
DEFAULT_FORWARD_SIGNALS_PATH = DEFAULT_FORWARD_OUTPUT_DIR / "paper_forward_signals.csv"
DEFAULT_FORWARD_OPEN_TRADES_PATH = DEFAULT_FORWARD_OUTPUT_DIR / "paper_forward_open_trades.csv"
DEFAULT_FORWARD_CLOSED_TRADES_PATH = DEFAULT_FORWARD_OUTPUT_DIR / "paper_forward_closed_trades.csv"
DEFAULT_FORWARD_EQUITY_PATH = DEFAULT_FORWARD_OUTPUT_DIR / "paper_forward_equity.csv"
DEFAULT_FORWARD_DAILY_LOG_PATH = DEFAULT_FORWARD_OUTPUT_DIR / "paper_forward_daily_log.csv"
DEFAULT_PAPER_SUMMARY_PATH = Path("reports/paper/paper_summary.csv")

PAPER_FORWARD_DECISIONS = {"NO_TRADE", "PAPER_BUY", "PAPER_SELL", "PAUSE", "STOP"}

SIGNAL_COLUMNS = [
    "signal_id",
    "created_at",
    "candle_time",
    "strategy_name",
    "decision",
    "side",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "lot_size",
    "commission_eur",
    "spread_cost_eur",
    "slippage_cost_eur",
    "total_cost_eur",
    "score",
    "opposite_score",
    "score_gap",
    "session",
    "reason",
    "allow_live",
    "live_mode",
]

OPEN_TRADE_COLUMNS = [
    "trade_id",
    "signal_id",
    "strategy_name",
    "symbol",
    "timeframe",
    "entry_time",
    "side",
    "session",
    "entry_price",
    "stop_loss",
    "take_profit",
    "break_even_price",
    "invalidation_price",
    "risk_reward",
    "lot_size",
    "commission_eur",
    "spread_cost_eur",
    "slippage_cost_eur",
    "total_cost_eur",
    "score",
    "opposite_score",
    "score_gap",
    "signal_reason",
    "status",
]

CLOSED_TRADE_COLUMNS = [
    *OPEN_TRADE_COLUMNS,
    "exit_time",
    "exit_price",
    "exit_reason",
    "price_points",
    "gross_pnl_eur",
    "pnl_eur",
    "equity_before",
    "equity_after",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_pct",
]

EQUITY_COLUMNS = [
    "timestamp",
    "candle_time",
    "event",
    "trade_id",
    "strategy_name",
    "equity",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_pct",
    "pnl_eur",
]

DAILY_LOG_COLUMNS = [
    "date",
    "timestamp",
    "strategy_name",
    "status",
    "decision",
    "reason",
    "equity",
    "drawdown_pct",
    "daily_pnl",
    "daily_loss_pct",
    "weekly_pnl",
    "weekly_loss_pct",
    "trades_today",
    "open_trades",
    "allow_live",
    "live_mode",
]


@dataclass(frozen=True)
class ForwardTables:
    """Loaded paper-forward CSV tables."""

    signals: pd.DataFrame
    open_trades: pd.DataFrame
    closed_trades: pd.DataFrame
    equity: pd.DataFrame
    daily_log: pd.DataFrame


@dataclass(frozen=True)
class ForwardSignalCandidate:
    """Signal plus entry-known filter metadata."""

    signal: TradingSignal
    allowed: bool
    reason: str
    metadata: dict


@dataclass(frozen=True)
class ForwardRunResult:
    """Result of one paper-forward cycle."""

    status: str
    decision: str
    strategy_name: str
    reason: str
    equity: float
    drawdown_pct: float
    daily_loss_pct: float
    open_trades: int
    next_action: str
    signal_id: str | None = None
    trade_id: str | None = None


SignalBuilder = Callable[[pd.DataFrame, StrategyConfig, PaperTradingConfig, float], ForwardSignalCandidate]


def ensure_forward_files(output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR) -> dict[str, Path]:
    """Create paper-forward CSV files with stable headers if they do not exist."""
    paths = forward_paths(output_dir)
    for path, columns in [
        (paths["signals"], SIGNAL_COLUMNS),
        (paths["open_trades"], OPEN_TRADE_COLUMNS),
        (paths["closed_trades"], CLOSED_TRADE_COLUMNS),
        (paths["equity"], EQUITY_COLUMNS),
        (paths["daily_log"], DAILY_LOG_COLUMNS),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pd.DataFrame(columns=columns).to_csv(path, index=False)
    return paths


def forward_paths(output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR) -> dict[str, Path]:
    """Return paper-forward output paths for one directory."""
    directory = Path(output_dir)
    return {
        "signals": directory / "paper_forward_signals.csv",
        "open_trades": directory / "paper_forward_open_trades.csv",
        "closed_trades": directory / "paper_forward_closed_trades.csv",
        "equity": directory / "paper_forward_equity.csv",
        "daily_log": directory / "paper_forward_daily_log.csv",
    }


def load_forward_tables(output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR) -> ForwardTables:
    """Load paper-forward tables, creating empty CSV files when needed."""
    paths = ensure_forward_files(output_dir)
    return ForwardTables(
        signals=_read_csv(paths["signals"], SIGNAL_COLUMNS),
        open_trades=_read_csv(paths["open_trades"], OPEN_TRADE_COLUMNS),
        closed_trades=_read_csv(paths["closed_trades"], CLOSED_TRADE_COLUMNS),
        equity=_read_csv(paths["equity"], EQUITY_COLUMNS),
        daily_log=_read_csv(paths["daily_log"], DAILY_LOG_COLUMNS),
    )


def run_paper_forward_once(
    market_data: pd.DataFrame,
    *,
    output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR,
    candidate_config_path: str | Path = "config/paper_candidate.yaml",
    paper_config_path: str | Path = "config/paper_trading.yaml",
    signal_builder: SignalBuilder | None = None,
    now: pd.Timestamp | None = None,
) -> ForwardRunResult:
    """
    Run one local paper-forward cycle.

    Open trades are updated first. A new signal is evaluated only when no paper
    trade remains open and the latest candle has not already been evaluated.
    """
    candidate = load_paper_candidate_config(candidate_config_path)
    paper_config = load_paper_trading_config(paper_config_path)
    validate_forward_safety(candidate, paper_config)

    data = normalize_market_data(market_data)
    if data.empty:
        raise ValueError("market_data must contain at least one closed candle")

    now = pd.Timestamp.utcnow() if now is None else pd.Timestamp(now)
    candle_time = pd.Timestamp(data.index[-1])
    output_dir = Path(output_dir)
    tables = load_forward_tables(output_dir)
    equity = current_forward_equity(tables.equity, paper_config, candidate.paper_main_strategy)
    running_high = current_running_high(tables.equity, equity)

    tables, equity, running_high = update_open_trades(
        data,
        tables,
        paper_config=paper_config,
        strategy_name=candidate.paper_main_strategy,
        equity=equity,
        running_high=running_high,
        output_dir=output_dir,
        now=now,
    )
    ensure_equity_snapshot(tables, output_dir, candidate.paper_main_strategy, equity, running_high, candle_time, now)
    tables = load_forward_tables(output_dir)

    state = calculate_forward_state(tables, candidate, paper_config, as_of=candle_time)
    if state["status"] == "STOP":
        result = _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "STOP",
            "risk limits reached: " + state["stop_reason"],
            state,
        )
        return result

    if int(state["open_trades"]) > 0:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "NO_TRADE",
            "paper trade already open",
            state,
        )

    if int(state["trades_today"]) >= candidate.max_trades_per_day:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "PAUSE",
            f"max trades per day reached ({candidate.max_trades_per_day})",
            state,
        )

    if state["daily_loss_pct"] > candidate.max_daily_loss_pct:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "STOP",
            f"daily loss {state['daily_loss_pct']:.2f}% above {candidate.max_daily_loss_pct:.2f}%",
            state,
        )

    if state["weekly_loss_pct"] > candidate.max_weekly_loss_pct:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "STOP",
            f"weekly loss {state['weekly_loss_pct']:.2f}% above {candidate.max_weekly_loss_pct:.2f}%",
            state,
        )

    if _already_evaluated_candle(tables.signals, candle_time):
        return ForwardRunResult(
            status=state["status"],
            decision="NO_TRADE",
            strategy_name=candidate.paper_main_strategy,
            reason="latest candle already evaluated",
            equity=float(state["equity"]),
            drawdown_pct=float(state["drawdown_pct"]),
            daily_loss_pct=float(state["daily_loss_pct"]),
            open_trades=int(state["open_trades"]),
            next_action="wait for a new closed candle",
        )

    strategy_config = StrategyConfig(symbol=paper_config.symbol, timeframe=paper_config.base_timeframe)
    builder = signal_builder or generate_high_margin_candidate
    candidate_signal = builder(data, strategy_config, paper_config, state["equity"])
    signal = candidate_signal.signal
    metadata = candidate_signal.metadata

    if signal.side not in {"BUY", "SELL"}:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "NO_TRADE",
            candidate_signal.reason,
            state,
            signal=signal,
            metadata=metadata,
        )

    if not candidate_signal.allowed:
        return _finalize_decision(
            tables,
            output_dir,
            candidate,
            paper_config,
            now,
            candle_time,
            "NO_TRADE",
            candidate_signal.reason,
            state,
            signal=signal,
            metadata=metadata,
        )

    trade_id = _trade_id(candle_time, signal.side)
    signal_id = _signal_id(candle_time)
    append_signal(
        output_dir,
        signal_id,
        now,
        candle_time,
        candidate,
        paper_config,
        f"PAPER_{signal.side}",
        candidate_signal.reason,
        state,
        signal=signal,
        metadata=metadata,
    )
    append_open_trade(
        output_dir,
        trade_id,
        signal_id,
        candidate.paper_main_strategy,
        paper_config,
        signal,
        metadata,
    )
    tables = load_forward_tables(output_dir)
    state = calculate_forward_state(tables, candidate, paper_config, as_of=candle_time)
    append_daily_log(output_dir, now, candle_time, candidate, paper_config, f"PAPER_{signal.side}", candidate_signal.reason, state)
    return ForwardRunResult(
        status=state["status"],
        decision=f"PAPER_{signal.side}",
        strategy_name=candidate.paper_main_strategy,
        reason=candidate_signal.reason,
        equity=float(state["equity"]),
        drawdown_pct=float(state["drawdown_pct"]),
        daily_loss_pct=float(state["daily_loss_pct"]),
        open_trades=int(state["open_trades"]),
        next_action="record paper trade only; wait for next closed candle",
        signal_id=signal_id,
        trade_id=trade_id,
    )


def validate_forward_safety(candidate: PaperCandidateConfig, paper_config: PaperTradingConfig) -> None:
    """Validate paper-forward safety gates."""
    if candidate.allow_live:
        raise ValueError("allow_live must remain false")
    if not candidate.paper_mode:
        raise ValueError("paper_mode must remain true")
    if candidate.paper_main_strategy != PAPER_MAIN_STRATEGY:
        raise ValueError(f"paper_main_strategy must be {PAPER_MAIN_STRATEGY}")
    if paper_config.live_mode:
        raise ValueError("paper_trading live_mode must remain false")
    if not paper_config.paper_mode:
        raise ValueError("paper_trading paper_mode must remain true")


def normalize_market_data(market_data: pd.DataFrame) -> pd.DataFrame:
    """Return OHLCV data sorted on a DatetimeIndex."""
    data = market_data.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        for column in ("Date", "time", "timestamp"):
            if column in data.columns:
                data[column] = pd.to_datetime(data[column], errors="coerce")
                data = data.dropna(subset=[column]).set_index(column)
                break
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("market_data must have a DatetimeIndex or a Date/time column")
    return data.sort_index()


def generate_high_margin_candidate(
    market_data: pd.DataFrame,
    strategy_config: StrategyConfig,
    paper_config: PaperTradingConfig,
    equity: float,
) -> ForwardSignalCandidate:
    """Generate the frozen high-margin paper candidate from local data only."""
    features = strategy_v50_pine.build_v50_features(market_data.tail(strategy_v50_pine.REQUIRED_HISTORY_CANDLES + 50))
    variant = _proxy_no_worst_hours_variant()
    generator = make_realtime_loss_proxy_signal_generator(variant)
    signal = generator(features, strategy_config)

    if signal.side not in {"BUY", "SELL"}:
        return ForwardSignalCandidate(signal=signal, allowed=False, reason=signal.reason, metadata=_signal_metadata(features, signal, paper_config, equity))

    metadata = _signal_metadata(features, signal, paper_config, equity)
    allowed, reason = _passes_high_margin_filter(signal, metadata)
    return ForwardSignalCandidate(signal=signal, allowed=allowed, reason=reason, metadata=metadata)


def update_open_trades(
    market_data: pd.DataFrame,
    tables: ForwardTables,
    *,
    paper_config: PaperTradingConfig,
    strategy_name: str,
    equity: float,
    running_high: float,
    output_dir: str | Path,
    now: pd.Timestamp,
) -> tuple[ForwardTables, float, float]:
    """Close paper trades whose TP/SL/BE/invalidation was reached by local candles."""
    open_trades = _active_open_trades(tables.open_trades)
    if open_trades.empty:
        return tables, equity, running_high

    remaining_rows = []
    closed_rows = []
    equity_rows = []

    for _, trade in open_trades.iterrows():
        exit_event = _find_exit_event(market_data, trade)
        if exit_event is None:
            remaining_rows.append(trade.to_dict())
            continue

        close_time, exit_price, exit_reason = exit_event
        points = _price_points_for_trade(trade, exit_price)
        lot = _float(trade.get("lot_size"))
        gross_pnl = points * (lot / 0.01) * paper_config.sizing_config.eur_per_price_point_per_001_lot
        total_cost = _float(trade.get("total_cost_eur"))
        pnl = gross_pnl - total_cost
        equity_before = equity
        equity += pnl
        running_high = max(running_high, equity)
        drawdown = running_high - equity
        drawdown_pct = drawdown / running_high * 100 if running_high > 0 else 0.0
        closed = trade.to_dict()
        closed.update(
            {
                "status": "CLOSED",
                "exit_time": close_time.isoformat(),
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "price_points": points,
                "gross_pnl_eur": gross_pnl,
                "pnl_eur": pnl,
                "equity_before": equity_before,
                "equity_after": equity,
                "running_equity_high": running_high,
                "drawdown_eur": drawdown,
                "drawdown_pct": drawdown_pct,
            }
        )
        closed_rows.append(closed)
        equity_rows.append(
            {
                "timestamp": now.isoformat(),
                "candle_time": close_time.isoformat(),
                "event": "trade_closed",
                "trade_id": trade.get("trade_id", ""),
                "strategy_name": strategy_name,
                "equity": equity,
                "running_equity_high": running_high,
                "drawdown_eur": drawdown,
                "drawdown_pct": drawdown_pct,
                "pnl_eur": pnl,
            }
        )

    all_open = pd.DataFrame(remaining_rows, columns=OPEN_TRADE_COLUMNS)
    all_closed = _append_rows(tables.closed_trades, closed_rows, CLOSED_TRADE_COLUMNS)
    all_equity = _append_rows(tables.equity, equity_rows, EQUITY_COLUMNS)
    paths = ensure_forward_files(output_dir)
    all_open.to_csv(paths["open_trades"], index=False)
    all_closed.to_csv(paths["closed_trades"], index=False)
    all_equity.to_csv(paths["equity"], index=False)
    return load_forward_tables(output_dir), equity, running_high


def calculate_forward_state(
    tables: ForwardTables,
    candidate: PaperCandidateConfig,
    paper_config: PaperTradingConfig,
    *,
    as_of: pd.Timestamp,
) -> dict:
    """Calculate current paper-forward operational state."""
    closed = _prepare_closed_trades(tables.closed_trades)
    open_trades = _active_open_trades(tables.open_trades)
    equity = current_forward_equity(tables.equity, paper_config, candidate.paper_main_strategy)
    running_high = current_running_high(tables.equity, equity)
    drawdown = running_high - equity
    drawdown_pct = drawdown / running_high * 100 if running_high > 0 else 0.0
    daily_pnl = _period_pnl(closed, as_of, "D")
    weekly_pnl = _period_pnl(closed, as_of, "W")
    day_start = max(equity - daily_pnl, 1e-9)
    week_start = max(equity - weekly_pnl, 1e-9)
    daily_loss_pct = abs(min(0.0, daily_pnl)) / day_start * 100
    weekly_loss_pct = abs(min(0.0, weekly_pnl)) / week_start * 100
    trades_today = _trades_entered_on(tables.open_trades, closed, as_of)
    pnl = pd.to_numeric(closed.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)

    stop_reasons = []
    warning_reasons = []
    if drawdown_pct > candidate.stop_drawdown_pct:
        stop_reasons.append(f"drawdown {drawdown_pct:.2f}% > {candidate.stop_drawdown_pct:.2f}%")
    if daily_loss_pct > candidate.max_daily_loss_pct:
        stop_reasons.append(f"daily loss {daily_loss_pct:.2f}% > {candidate.max_daily_loss_pct:.2f}%")
    if weekly_loss_pct > candidate.max_weekly_loss_pct:
        stop_reasons.append(f"weekly loss {weekly_loss_pct:.2f}% > {candidate.max_weekly_loss_pct:.2f}%")
    if drawdown_pct > candidate.warning_drawdown_pct:
        warning_reasons.append(f"drawdown {drawdown_pct:.2f}% > {candidate.warning_drawdown_pct:.2f}%")

    status = "STOP" if stop_reasons else "WARNING" if warning_reasons else "OK"
    return {
        "status": status,
        "stop_reason": "; ".join(stop_reasons),
        "warning_reason": "; ".join(warning_reasons),
        "equity": equity,
        "running_high": running_high,
        "drawdown_eur": drawdown,
        "drawdown_pct": drawdown_pct,
        "daily_pnl": daily_pnl,
        "weekly_pnl": weekly_pnl,
        "daily_loss_pct": daily_loss_pct,
        "weekly_loss_pct": weekly_loss_pct,
        "trades_today": trades_today,
        "open_trades": int(len(open_trades)),
        "closed_trades": int(len(closed)),
        "profit_factor": profit_factor(pnl),
        "loss_streak": current_consecutive_losses(pnl),
        "max_loss_streak": max_consecutive_losses(pnl),
    }


def build_forward_status(output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR) -> dict:
    """Return a user-facing status snapshot for paper-forward reports."""
    candidate = load_paper_candidate_config()
    paper_config = load_paper_trading_config()
    tables = load_forward_tables(output_dir)
    as_of = _status_as_of(tables)
    state = calculate_forward_state(tables, candidate, paper_config, as_of=as_of)
    closed = _prepare_closed_trades(tables.closed_trades)
    pnl = pd.to_numeric(closed.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    today_pnl = state["daily_pnl"]
    status = state["status"]
    can_continue = status != "STOP"
    return {
        **state,
        "strategy_name": candidate.paper_main_strategy,
        "open_trades_count": state["open_trades"],
        "closed_trades_count": state["closed_trades"],
        "total_pnl": float(pnl.sum()) if not pnl.empty else 0.0,
        "today_pnl": today_pnl,
        "can_continue_tomorrow": bool(can_continue),
    }


def record_paper_forward_pause(
    reason: str,
    *,
    output_dir: str | Path = DEFAULT_FORWARD_OUTPUT_DIR,
    candidate_config_path: str | Path = "config/paper_candidate.yaml",
    paper_config_path: str | Path = "config/paper_trading.yaml",
    now: pd.Timestamp | None = None,
) -> ForwardRunResult:
    """Record a paper-forward PAUSE decision without evaluating strategy signals."""
    candidate = load_paper_candidate_config(candidate_config_path)
    paper_config = load_paper_trading_config(paper_config_path)
    validate_forward_safety(candidate, paper_config)
    now = pd.Timestamp.utcnow() if now is None else pd.Timestamp(now)
    output_dir = Path(output_dir)
    tables = load_forward_tables(output_dir)
    equity = current_forward_equity(tables.equity, paper_config, candidate.paper_main_strategy)
    running_high = current_running_high(tables.equity, equity)
    state = calculate_forward_state(tables, candidate, paper_config, as_of=now)
    state["status"] = "WARNING"
    state["equity"] = equity
    state["running_high"] = running_high
    append_signal(output_dir, _signal_id(now), now, now, candidate, paper_config, "PAUSE", reason, state)
    append_daily_log(output_dir, now, now, candidate, paper_config, "PAUSE", reason, state)
    return ForwardRunResult(
        status="WARNING",
        decision="PAUSE",
        strategy_name=candidate.paper_main_strategy,
        reason=reason,
        equity=float(state["equity"]),
        drawdown_pct=float(state["drawdown_pct"]),
        daily_loss_pct=float(state["daily_loss_pct"]),
        open_trades=int(state["open_trades"]),
        next_action="update local XAUUSD data before paper-forward",
        signal_id=_signal_id(now),
    )


def current_forward_equity(equity_table: pd.DataFrame, paper_config: PaperTradingConfig, strategy_name: str) -> float:
    """Return latest forward equity, falling back to the validated paper summary."""
    if not equity_table.empty and "equity" in equity_table.columns:
        values = pd.to_numeric(equity_table["equity"], errors="coerce").dropna()
        if not values.empty:
            return float(values.iloc[-1])
    summary_path = DEFAULT_PAPER_SUMMARY_PATH
    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        if {"strategy_name", "ending_equity"}.issubset(summary.columns):
            row = summary[summary["strategy_name"] == strategy_name]
            if not row.empty:
                value = pd.to_numeric(row.iloc[0]["ending_equity"], errors="coerce")
                if pd.notna(value):
                    return float(value)
    return float(paper_config.initial_equity)


def current_running_high(equity_table: pd.DataFrame, current_equity: float) -> float:
    """Return latest running equity high."""
    if not equity_table.empty and "running_equity_high" in equity_table.columns:
        values = pd.to_numeric(equity_table["running_equity_high"], errors="coerce").dropna()
        if not values.empty:
            return max(float(values.iloc[-1]), current_equity)
    return float(current_equity)


def append_signal(
    output_dir: str | Path,
    signal_id: str,
    now: pd.Timestamp,
    candle_time: pd.Timestamp,
    candidate: PaperCandidateConfig,
    paper_config: PaperTradingConfig,
    decision: str,
    reason: str,
    state: dict,
    *,
    signal: TradingSignal | None = None,
    metadata: dict | None = None,
) -> None:
    """Append one paper-forward signal decision."""
    metadata = metadata or {}
    row = {
        "signal_id": signal_id,
        "created_at": now.isoformat(),
        "candle_time": candle_time.isoformat(),
        "strategy_name": candidate.paper_main_strategy,
        "decision": decision,
        "side": signal.side if signal else "",
        "entry_price": signal.entry_price if signal else None,
        "stop_loss": signal.stop_loss if signal else None,
        "take_profit": signal.take_profit if signal else None,
        "risk_reward": signal.risk_reward if signal else None,
        "lot_size": metadata.get("lot_size"),
        "commission_eur": metadata.get("commission_eur"),
        "spread_cost_eur": metadata.get("spread_cost_eur"),
        "slippage_cost_eur": metadata.get("slippage_cost_eur"),
        "total_cost_eur": metadata.get("total_cost_eur"),
        "score": metadata.get("score"),
        "opposite_score": metadata.get("opposite_score"),
        "score_gap": metadata.get("score_gap"),
        "session": metadata.get("session"),
        "reason": reason,
        "allow_live": candidate.allow_live,
        "live_mode": paper_config.live_mode,
    }
    paths = ensure_forward_files(output_dir)
    signals = _read_csv(paths["signals"], SIGNAL_COLUMNS)
    _append_rows(signals, [row], SIGNAL_COLUMNS).to_csv(paths["signals"], index=False)


def append_open_trade(
    output_dir: str | Path,
    trade_id: str,
    signal_id: str,
    strategy_name: str,
    paper_config: PaperTradingConfig,
    signal: TradingSignal,
    metadata: dict,
) -> None:
    """Record one simulated paper open trade. No real order is sent."""
    row = {
        "trade_id": trade_id,
        "signal_id": signal_id,
        "strategy_name": strategy_name,
        "symbol": paper_config.symbol,
        "timeframe": paper_config.base_timeframe,
        "entry_time": pd.Timestamp(signal.timestamp).isoformat(),
        "side": signal.side,
        "session": metadata.get("session"),
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "break_even_price": None,
        "invalidation_price": None,
        "risk_reward": signal.risk_reward,
        "lot_size": metadata.get("lot_size"),
        "commission_eur": metadata.get("commission_eur"),
        "spread_cost_eur": metadata.get("spread_cost_eur"),
        "slippage_cost_eur": metadata.get("slippage_cost_eur"),
        "total_cost_eur": metadata.get("total_cost_eur"),
        "score": metadata.get("score"),
        "opposite_score": metadata.get("opposite_score"),
        "score_gap": metadata.get("score_gap"),
        "signal_reason": signal.reason,
        "status": "OPEN",
    }
    paths = ensure_forward_files(output_dir)
    open_trades = _read_csv(paths["open_trades"], OPEN_TRADE_COLUMNS)
    _append_rows(open_trades, [row], OPEN_TRADE_COLUMNS).to_csv(paths["open_trades"], index=False)


def append_daily_log(
    output_dir: str | Path,
    now: pd.Timestamp,
    candle_time: pd.Timestamp,
    candidate: PaperCandidateConfig,
    paper_config: PaperTradingConfig,
    decision: str,
    reason: str,
    state: dict,
) -> None:
    """Append one operational daily log row."""
    row = {
        "date": candle_time.date().isoformat(),
        "timestamp": now.isoformat(),
        "strategy_name": candidate.paper_main_strategy,
        "status": state["status"],
        "decision": decision,
        "reason": reason,
        "equity": state["equity"],
        "drawdown_pct": state["drawdown_pct"],
        "daily_pnl": state["daily_pnl"],
        "daily_loss_pct": state["daily_loss_pct"],
        "weekly_pnl": state["weekly_pnl"],
        "weekly_loss_pct": state["weekly_loss_pct"],
        "trades_today": state["trades_today"],
        "open_trades": state["open_trades"],
        "allow_live": candidate.allow_live,
        "live_mode": paper_config.live_mode,
    }
    paths = ensure_forward_files(output_dir)
    daily = _read_csv(paths["daily_log"], DAILY_LOG_COLUMNS)
    _append_rows(daily, [row], DAILY_LOG_COLUMNS).to_csv(paths["daily_log"], index=False)


def ensure_equity_snapshot(
    tables: ForwardTables,
    output_dir: str | Path,
    strategy_name: str,
    equity: float,
    running_high: float,
    candle_time: pd.Timestamp,
    now: pd.Timestamp,
) -> None:
    """Create an initial equity snapshot so status files are immediately useful."""
    if not tables.equity.empty:
        return
    drawdown = running_high - equity
    drawdown_pct = drawdown / running_high * 100 if running_high > 0 else 0.0
    row = {
        "timestamp": now.isoformat(),
        "candle_time": candle_time.isoformat(),
        "event": "initial_snapshot",
        "trade_id": "",
        "strategy_name": strategy_name,
        "equity": equity,
        "running_equity_high": running_high,
        "drawdown_eur": drawdown,
        "drawdown_pct": drawdown_pct,
        "pnl_eur": 0.0,
    }
    paths = ensure_forward_files(output_dir)
    pd.DataFrame([row], columns=EQUITY_COLUMNS).to_csv(paths["equity"], index=False)


def _passes_high_margin_filter(signal: TradingSignal, metadata: dict) -> tuple[bool, str]:
    variant = next(item for item in build_cost_aware_variants() if item.variant_name == "costaware_high_margin_combo")
    session = str(metadata.get("session", "")).upper()
    score = float(metadata.get("score", 0.0))
    gap = float(metadata.get("score_gap", 0.0))
    target_ratio = float(metadata.get("target_to_cost_ratio", 0.0))
    atr_ratio = float(metadata.get("atr_to_cost_ratio", 0.0))

    if variant.allowed_sessions and session not in set(variant.allowed_sessions):
        return False, f"high-margin filter blocked session {session}"
    if variant.min_score is not None and score < variant.min_score:
        return False, f"high-margin filter score {score:.1f} below {variant.min_score:.1f}"
    if variant.min_score_gap is not None and gap < variant.min_score_gap:
        return False, f"high-margin filter score gap {gap:.1f} below {variant.min_score_gap:.1f}"
    if variant.min_target_to_cost_ratio is not None and target_ratio < variant.min_target_to_cost_ratio:
        return False, f"high-margin filter target/cost {target_ratio:.2f} below {variant.min_target_to_cost_ratio:.2f}"
    if variant.min_atr_to_cost_ratio is not None and atr_ratio < variant.min_atr_to_cost_ratio:
        return False, f"high-margin filter ATR/cost {atr_ratio:.2f} below {variant.min_atr_to_cost_ratio:.2f}"
    return True, "PAPER signal accepted by frozen high-margin filters"


def _signal_metadata(features: pd.DataFrame, signal: TradingSignal, paper_config: PaperTradingConfig, equity: float) -> dict:
    latest = features.iloc[-1]
    side = signal.side
    score = _score_for_side(latest, side)
    opposite = _opposite_score_for_side(latest, side)
    lot = lot_size_for_equity(equity, paper_config.sizing_config)
    profile = paper_cost_profile(paper_config)
    spread_cost, slippage_cost, commission_cost = axi_cost_components_for_lot(profile, lot)
    total_cost = spread_cost + slippage_cost + commission_cost
    target_points = _target_points(signal)
    atr_points = _float(latest.get("v50_atr", latest.get("ATR_14", 0.0)))
    point_value = paper_config.sizing_config.eur_per_price_point_per_001_lot
    target_money = target_points * (lot / 0.01) * point_value
    atr_money = atr_points * (lot / 0.01) * point_value
    return {
        "session": str(latest.get("v50_session", "UNKNOWN")).upper(),
        "score": score,
        "opposite_score": opposite,
        "score_gap": score - opposite,
        "lot_size": lot,
        "spread_cost_eur": spread_cost,
        "slippage_cost_eur": slippage_cost,
        "commission_eur": commission_cost,
        "total_cost_eur": total_cost,
        "target_points": target_points,
        "atr_points": atr_points,
        "target_to_cost_ratio": _safe_ratio(target_money, total_cost),
        "atr_to_cost_ratio": _safe_ratio(atr_money, total_cost),
    }


def _finalize_decision(
    tables: ForwardTables,
    output_dir: str | Path,
    candidate: PaperCandidateConfig,
    paper_config: PaperTradingConfig,
    now: pd.Timestamp,
    candle_time: pd.Timestamp,
    decision: str,
    reason: str,
    state: dict,
    *,
    signal: TradingSignal | None = None,
    metadata: dict | None = None,
) -> ForwardRunResult:
    signal_id = _signal_id(candle_time)
    append_signal(output_dir, signal_id, now, candle_time, candidate, paper_config, decision, reason, state, signal=signal, metadata=metadata)
    append_daily_log(output_dir, now, candle_time, candidate, paper_config, decision, reason, state)
    next_action = "continue paper observation" if decision in {"NO_TRADE", "PAUSE"} else "stop paper trading until reviewed"
    return ForwardRunResult(
        status=state["status"],
        decision=decision,
        strategy_name=candidate.paper_main_strategy,
        reason=reason,
        equity=float(state["equity"]),
        drawdown_pct=float(state["drawdown_pct"]),
        daily_loss_pct=float(state["daily_loss_pct"]),
        open_trades=int(state["open_trades"]),
        next_action=next_action,
        signal_id=signal_id,
    )


def _find_exit_event(market_data: pd.DataFrame, trade: pd.Series) -> tuple[pd.Timestamp, float, str] | None:
    entry_time = pd.to_datetime(trade.get("entry_time"), errors="coerce")
    if pd.isna(entry_time):
        return None
    future = market_data[market_data.index > entry_time]
    if future.empty:
        return None
    side = str(trade.get("side", "")).upper()
    stop_loss = _float_or_none(trade.get("stop_loss"))
    take_profit = _float_or_none(trade.get("take_profit"))
    break_even = _float_or_none(trade.get("break_even_price"))
    invalidation = _float_or_none(trade.get("invalidation_price"))

    for timestamp, candle in future.iterrows():
        high = _float(candle.get("High"))
        low = _float(candle.get("Low"))
        if side == "BUY":
            if stop_loss is not None and low <= stop_loss:
                return pd.Timestamp(timestamp), stop_loss, "SL"
            if break_even is not None and low <= break_even:
                return pd.Timestamp(timestamp), break_even, "BE"
            if invalidation is not None and low <= invalidation:
                return pd.Timestamp(timestamp), invalidation, "INVALIDATION"
            if take_profit is not None and high >= take_profit:
                return pd.Timestamp(timestamp), take_profit, "TP"
        if side == "SELL":
            if stop_loss is not None and high >= stop_loss:
                return pd.Timestamp(timestamp), stop_loss, "SL"
            if break_even is not None and high >= break_even:
                return pd.Timestamp(timestamp), break_even, "BE"
            if invalidation is not None and high >= invalidation:
                return pd.Timestamp(timestamp), invalidation, "INVALIDATION"
            if take_profit is not None and low <= take_profit:
                return pd.Timestamp(timestamp), take_profit, "TP"
    return None


def _price_points_for_trade(trade: pd.Series, exit_price: float) -> float:
    entry = _float(trade.get("entry_price"))
    side = str(trade.get("side", "")).upper()
    return entry - exit_price if side == "SELL" else exit_price - entry


def _proxy_no_worst_hours_variant():
    variants = {variant.variant_name: variant for variant in build_proxy_hardening_variants()}
    return variants["proxy_hardened_no_worst_hours"].realtime_variant


def _score_for_side(row: pd.Series, side: str) -> float:
    if side == "BUY":
        return _float(row.get("v50_score_long"))
    if side == "SELL":
        return _float(row.get("v50_score_short"))
    return 0.0


def _opposite_score_for_side(row: pd.Series, side: str) -> float:
    return _score_for_side(row, "SELL" if side == "BUY" else "BUY")


def _target_points(signal: TradingSignal) -> float:
    if signal.entry_price is None or signal.take_profit is None:
        return 0.0
    return abs(float(signal.take_profit) - float(signal.entry_price))


def _already_evaluated_candle(signals: pd.DataFrame, candle_time: pd.Timestamp) -> bool:
    if signals.empty or "candle_time" not in signals.columns:
        return False
    times = pd.to_datetime(signals["candle_time"], errors="coerce")
    return bool((times == candle_time).any())


def _active_open_trades(open_trades: pd.DataFrame) -> pd.DataFrame:
    if open_trades.empty:
        return pd.DataFrame(columns=OPEN_TRADE_COLUMNS)
    status = open_trades.get("status", pd.Series(["OPEN"] * len(open_trades), index=open_trades.index)).astype(str).str.upper()
    return open_trades[status == "OPEN"].copy().reset_index(drop=True)


def _prepare_closed_trades(closed_trades: pd.DataFrame) -> pd.DataFrame:
    if closed_trades.empty:
        return pd.DataFrame(columns=CLOSED_TRADE_COLUMNS)
    result = closed_trades.copy()
    for column in ("entry_time", "exit_time"):
        result[column] = pd.to_datetime(result[column], errors="coerce")
    return result


def _period_pnl(closed_trades: pd.DataFrame, as_of: pd.Timestamp, freq: str) -> float:
    if closed_trades.empty:
        return 0.0
    column = "exit_time" if "exit_time" in closed_trades.columns else "entry_time"
    times = pd.to_datetime(closed_trades[column], errors="coerce")
    pnl = pd.to_numeric(closed_trades.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    if freq == "D":
        mask = times.dt.normalize() == as_of.normalize()
    else:
        mask = times.dt.to_period(freq) == as_of.to_period(freq)
    return float(pnl[mask].sum())


def _trades_entered_on(open_trades: pd.DataFrame, closed_trades: pd.DataFrame, as_of: pd.Timestamp) -> int:
    frames = []
    for frame in (open_trades, closed_trades):
        if frame is not None and not frame.empty and "entry_time" in frame.columns:
            frames.append(pd.to_datetime(frame["entry_time"], errors="coerce"))
    if not frames:
        return 0
    times = pd.concat(frames, ignore_index=True).dropna()
    return int((times.dt.normalize() == as_of.normalize()).sum())


def _status_as_of(tables: ForwardTables) -> pd.Timestamp:
    for frame, column in ((tables.equity, "candle_time"), (tables.closed_trades, "exit_time"), (tables.signals, "candle_time")):
        if not frame.empty and column in frame.columns:
            times = pd.to_datetime(frame[column], errors="coerce").dropna()
            if not times.empty:
                return pd.Timestamp(times.iloc[-1])
    return pd.Timestamp.utcnow()


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[columns]


def _append_rows(frame: pd.DataFrame, rows: list[dict], columns: list[str]) -> pd.DataFrame:
    if not rows:
        result = frame.copy()
    else:
        result = pd.concat([frame, pd.DataFrame(rows)], ignore_index=True)
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[columns]


def _float(value: object) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(parsed) else float(parsed)


def _float_or_none(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return float("inf") if numerator > 0 else 0.0
    return float(numerator / denominator)


def _signal_id(candle_time: pd.Timestamp) -> str:
    return "PFWD-SIG-" + _compact_time(candle_time)


def _trade_id(candle_time: pd.Timestamp, side: str) -> str:
    return f"PFWD-{_compact_time(candle_time)}-{side}"


def _compact_time(timestamp: pd.Timestamp) -> str:
    value = pd.Timestamp(timestamp)
    text = value.strftime("%Y%m%d%H%M%S")
    return re.sub(r"[^0-9]", "", text)
