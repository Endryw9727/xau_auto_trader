"""V51 demo-only MT5 execution gate.

This module connects the V51 demo intraday candidate to MT5 demo execution.
It never enables real live trading and records V51-specific execution logs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.execution.mt5_demo_executor import import_mt5_module
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    V51DemoIntradayConfig,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_V51_DEMO_OUTPUT_DIR = Path("reports/demo_execution")
DEFAULT_V51_MTF_CONTEXT_SUMMARY_PATH = Path("reports/diagnostics/v51_mtf_context_summary.csv")
V51_DEMO_COMMENT = "V51_DEMO"
FUTURE_CANDIDATE_TOLERANCE_MINUTES = 1.0

V51_DEMO_ORDER_COLUMNS = [
    "timestamp",
    "signal_id",
    "candle_time",
    "symbol",
    "side",
    "lot_size",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "score",
    "score_gap",
    "spread_points",
    "spread_cost",
    "slippage_estimate",
    "status",
    "reason",
    "mt5_retcode",
    "mt5_order",
    "mt5_deal",
    "magic_number",
    "comment",
    "dry_run",
]

V51_DEMO_LOG_COLUMNS = [
    "timestamp",
    "event",
    "status",
    "decision",
    "reason",
    "signal_id",
    "candle_time",
    "symbol",
    "side",
    "now_utc",
    "now_local",
    "candidate_age_minutes",
    "latest_closed_candle_time",
    "selected_candidate_time",
    "candidate_time_basis",
    "time_alignment_status",
    "live_candidate_window_minutes",
    "require_latest_closed_candle_candidate",
    "selection_reason",
    "current_bid",
    "current_ask",
    "expected_entry_price",
    "live_entry_price",
    "slippage_points",
    "adverse_slippage_points",
    "max_slippage_points",
    "chase_distance_points",
    "max_chase_points",
    "point_size",
    "spread_points",
    "session",
    "score",
    "risk_reward",
    "mtf_final_bias",
    "mtf_filter_enabled",
    "mtf_filter_passed",
    "mtf_filter_reason",
    "dry_run",
]

ACTIVE_DEMO_STATUSES = {"SENT", "ACCEPTED", "FILLED"}


@dataclass(frozen=True)
class V51DemoCandidate:
    """Best V51 closed-candle candidate selected for demo execution."""

    signal_id: str
    candle_time: pd.Timestamp
    symbol: str
    side: Literal["BUY", "SELL"]
    lot_size: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    score: float
    score_gap: float
    spread_cost: float
    slippage_estimate: float
    reason: str
    session: str = ""


@dataclass(frozen=True)
class V51DemoExecutionResult:
    """Result of one V51 demo execution attempt."""

    accepted: bool
    status: str
    reason: str
    dry_run: bool
    signal_id: str | None = None
    candle_time: pd.Timestamp | None = None
    symbol: str | None = None
    side: str | None = None
    mt5_retcode: int | None = None
    mt5_order: int | None = None
    mt5_deal: int | None = None
    now_utc: pd.Timestamp | None = None
    now_local: str | None = None
    candidate_age_minutes: float | None = None
    latest_closed_candle_time: pd.Timestamp | None = None
    selected_candidate_time: pd.Timestamp | None = None
    candidate_time_basis: str | None = None
    time_alignment_status: str | None = None
    live_candidate_window_minutes: int | None = None
    require_latest_closed_candle_candidate: bool | None = None
    selection_reason: str | None = None
    current_bid: float | None = None
    current_ask: float | None = None
    expected_entry_price: float | None = None
    live_entry_price: float | None = None
    slippage_points: float | None = None
    adverse_slippage_points: float | None = None
    max_slippage_points: float | None = None
    chase_distance_points: float | None = None
    max_chase_points: float | None = None
    point_size: float | None = None
    spread_points: float | None = None
    session: str | None = None
    score: float | None = None
    risk_reward: float | None = None
    mtf_final_bias: str | None = None
    mtf_filter_enabled: bool | None = None
    mtf_filter_passed: bool | None = None
    mtf_filter_reason: str | None = None


@dataclass(frozen=True)
class MTFDirectionFilterResult:
    """Read-only MTF direction filter outcome for a selected V51 candidate."""

    enabled: bool
    passed: bool
    final_bias: str
    reason: str


@dataclass(frozen=True)
class MTFAuditContext:
    """MTF context loaded once for audit fields on every V51 execution row."""

    enabled: bool
    final_bias: str
    summary: pd.DataFrame | None
    data_issues: tuple[str, ...]


@dataclass(frozen=True)
class LivePriceQuality:
    """Current bid/ask quality check for a selected V51 candidate."""

    live_entry_price: float | None
    expected_entry_price: float
    adverse_slippage_points: float | None
    chase_distance_points: float | None
    point_size: float | None
    reason: str | None = None


def run_v51_demo_execution_once(
    *,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR,
    mtf_context_summary_path: str | Path | None = DEFAULT_V51_MTF_CONTEXT_SUMMARY_PATH,
    mt5_module: Any | None = None,
    dry_run: bool = True,
    now: pd.Timestamp | None = None,
) -> V51DemoExecutionResult:
    """Run one gated V51 demo execution attempt."""
    config = load_v51_config(config_path)
    now = _utc_now(now)
    mtf_audit = load_mtf_audit_context(config, mtf_context_summary_path)
    no_candidate_telemetry = _no_candidate_telemetry(now, mtf_audit)
    gate_error = _validate_execution_gates(config)
    if gate_error is not None:
        result = _result(False, "REJECTED", gate_error, dry_run=dry_run, telemetry=no_candidate_telemetry)
        append_v51_demo_log(output_dir, result, event="config_gate")
        return result

    mt5 = mt5_module or import_mt5_module()
    if mt5 is None:
        result = _result(
            False,
            "MT5_NOT_AVAILABLE",
            "Python MetaTrader5 package is not available.",
            dry_run=dry_run,
            telemetry=no_candidate_telemetry,
        )
        append_v51_demo_log(output_dir, result, event="mt5_unavailable")
        return result

    initialized = False
    try:
        initialized = bool(mt5.initialize()) if callable(getattr(mt5, "initialize", None)) else False
        if not initialized:
            result = _result(
                False,
                "ERROR",
                f"MT5_NOT_INITIALIZED: {_last_error(mt5)}",
                dry_run=dry_run,
                telemetry=no_candidate_telemetry,
            )
            append_v51_demo_log(output_dir, result, event="mt5_initialize")
            return result

        market_error = _validate_mt5_demo_state(mt5, config)
        if market_error is not None:
            result = _result(False, "REJECTED", market_error, dry_run=dry_run, telemetry=no_candidate_telemetry)
            append_v51_demo_log(output_dir, result, event="broker_gate")
            return result

        try:
            rates = read_mt5_closed_rates(mt5, config)
        except Exception as exc:
            result = _result(
                False,
                "NO_TRADE",
                f"MT5 data unavailable: {exc}",
                dry_run=dry_run,
                telemetry=no_candidate_telemetry,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result
        latest_closed_candle_time = _latest_closed_candle_time(rates)
        no_candidate_telemetry = _no_candidate_telemetry(now, mtf_audit, latest_closed_candle_time=latest_closed_candle_time)
        stale_reason = _stale_data_reason(rates, config, now)
        if stale_reason is not None:
            result = _result(False, "NO_TRADE", stale_reason, dry_run=dry_run, telemetry=no_candidate_telemetry)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        order_log = load_v51_demo_orders(output_dir)
        execution_log = load_v51_demo_execution_log(output_dir)
        trading_day = latest_closed_candle_time.normalize()
        trades_today = _trades_for_day(order_log, trading_day)
        if trades_today >= config.max_trades_per_day:
            result = _result(
                False,
                "NO_TRADE",
                f"max trades per day reached ({config.max_trades_per_day})",
                dry_run=dry_run,
                telemetry=no_candidate_telemetry,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        if _has_open_v51_position(mt5, config):
            result = _result(
                False,
                "NO_TRADE",
                "existing open V51_DEMO position blocks new demo order",
                dry_run=dry_run,
                telemetry=no_candidate_telemetry,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        symbol_info = mt5.symbol_info(config.symbol)
        tick = mt5.symbol_info_tick(config.symbol)
        spread_points = _spread_points(symbol_info, tick)
        if spread_points is not None and spread_points > config.max_spread_points:
            result = _result(
                False,
                "NO_TRADE",
                f"spread {spread_points:.1f} points exceeds max {config.max_spread_points:.1f}",
                dry_run=dry_run,
                telemetry={
                    **_market_telemetry(config, tick, spread_points=spread_points),
                    **no_candidate_telemetry,
                },
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        candidate, no_trade_reason = select_best_v51_candidate(
            rates,
            config,
            existing_orders=order_log,
            trades_today=trades_today,
            open_positions=0,
            spread_points=spread_points,
            latest_closed_candle_time=latest_closed_candle_time,
        )
        if candidate is None:
            result = _result(
                False,
                "NO_TRADE",
                no_trade_reason,
                dry_run=dry_run,
                telemetry=_selection_telemetry(
                    config,
                    latest_closed_candle_time=latest_closed_candle_time,
                    tick=tick,
                    spread_points=spread_points,
                    selection_reason=no_trade_reason,
                    now=now,
                )
                | _mtf_audit_telemetry(
                    mtf_audit,
                    passed=False if mtf_audit.enabled else True,
                    reason="no_v51_candidate_to_filter" if mtf_audit.enabled else "mtf_filter_disabled",
                ),
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        candidate_error = validate_v51_demo_candidate(candidate, config, order_log)
        selection_reason = no_trade_reason
        telemetry = _candidate_telemetry(
            candidate,
            config,
            latest_closed_candle_time=latest_closed_candle_time,
            tick=tick,
            spread_points=spread_points,
            slippage_points=None,
            selection_reason=selection_reason,
            now=now,
        )
        if candidate_error is not None:
            telemetry = {
                **telemetry,
                **_mtf_audit_telemetry(
                    mtf_audit,
                    passed=False if mtf_audit.enabled else True,
                    reason="candidate_failed_before_mtf_filter" if mtf_audit.enabled else "mtf_filter_disabled",
                ),
            }
            result = _result(False, "REJECTED", candidate_error, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
            append_v51_demo_log(output_dir, result, event="candidate_gate")
            return result

        time_guard_reason = _candidate_time_guard_reason(candidate, config, latest_closed_candle_time, now)
        if time_guard_reason is not None:
            telemetry = {
                **telemetry,
                **_time_alignment_telemetry(
                    now,
                    latest_closed_candle_time=latest_closed_candle_time,
                    candidate=candidate,
                    status=time_guard_reason,
                ),
                **_mtf_audit_telemetry(
                    mtf_audit,
                    passed=False if mtf_audit.enabled else True,
                    reason="candidate_failed_before_mtf_filter" if mtf_audit.enabled else "mtf_filter_disabled",
                ),
            }
            result = _result(False, "NO_TRADE", time_guard_reason, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        mtf_filter = evaluate_mtf_direction_filter(candidate, config, mtf_context_summary_path, audit=mtf_audit)
        telemetry = _with_mtf_telemetry(telemetry, mtf_filter)
        if not mtf_filter.passed:
            result = _result(False, "NO_TRADE", mtf_filter.reason, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        cooldown_reason = _rejected_signal_cooldown_reason(execution_log, candidate.signal_id, config, now)
        if cooldown_reason is not None:
            result = _result(False, "NO_TRADE", cooldown_reason, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        stale_candidate_reason = _candidate_stale_reason(candidate, config, latest_closed_candle_time)
        if stale_candidate_reason is not None:
            telemetry = {
                **telemetry,
                **_time_alignment_telemetry(
                    now,
                    latest_closed_candle_time=latest_closed_candle_time,
                    candidate=candidate,
                    status=stale_candidate_reason,
                ),
            }
            result = _result(False, "NO_TRADE", stale_candidate_reason, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        price_check = _live_price_quality(candidate, config, symbol_info, tick)
        telemetry = _candidate_telemetry(
            candidate,
            config,
            latest_closed_candle_time=latest_closed_candle_time,
            tick=tick,
            spread_points=spread_points,
            slippage_points=price_check.adverse_slippage_points,
            selection_reason=selection_reason,
            now=now,
        )
        telemetry.update(_price_quality_telemetry(price_check))
        telemetry = _with_mtf_telemetry(telemetry, mtf_filter)
        if price_check.reason is not None:
            result = _result(
                False,
                "NO_TRADE",
                price_check.reason,
                dry_run=dry_run,
                candidate=candidate,
                telemetry=telemetry,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        if config.reprice_live_entry:
            repriced_candidate, reprice_error = _reprice_candidate_from_live_entry(candidate, price_check.live_entry_price)
            if reprice_error is not None:
                result = _result(False, "NO_TRADE", reprice_error, dry_run=dry_run, candidate=candidate, telemetry=telemetry)
                append_v51_demo_log(output_dir, result, event="no_trade")
                return result
            candidate = repriced_candidate
            reprice_validation = validate_v51_demo_candidate(candidate, config, order_log)
            telemetry = _candidate_telemetry(
                candidate,
                config,
                latest_closed_candle_time=latest_closed_candle_time,
                tick=tick,
                spread_points=spread_points,
                slippage_points=price_check.adverse_slippage_points,
                selection_reason=selection_reason,
                now=now,
            )
            telemetry.update(_price_quality_telemetry(price_check))
            telemetry = _with_mtf_telemetry(telemetry, mtf_filter)
            if reprice_validation is not None:
                result = _result(
                    False,
                    "NO_TRADE",
                    f"repriced_candidate_invalid: {reprice_validation}",
                    dry_run=dry_run,
                    candidate=candidate,
                    telemetry=telemetry,
                )
                append_v51_demo_log(output_dir, result, event="no_trade")
                return result

        if dry_run:
            result = _result(
                True,
                "DRY_RUN",
                "V51 dry-run accepted; no MT5 order was submitted.",
                dry_run=True,
                candidate=candidate,
                telemetry=telemetry,
            )
            append_v51_demo_order(output_dir, result, candidate, config, spread_points=spread_points)
            append_v51_demo_log(output_dir, result, event="dry_run")
            return result

        request = _build_mt5_request(mt5, config, candidate)
        order_send = getattr(mt5, "order_send", None)
        if not callable(order_send):
            result = _result(
                False,
                "ERROR",
                "MT5 order submission function is unavailable.",
                dry_run=False,
                candidate=candidate,
                telemetry=telemetry,
            )
            append_v51_demo_log(output_dir, result, event="submit_error")
            return result

        response = order_send(request)
        result = _result_from_response(mt5, response, candidate, telemetry=telemetry)
        append_v51_demo_order(output_dir, result, candidate, config, spread_points=spread_points)
        append_v51_demo_log(output_dir, result, event="demo_order_result")
        return result
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()


def build_v51_demo_status(
    *,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR,
    mt5_module: Any | None = None,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Return a read-only V51 demo execution status snapshot."""
    config = load_v51_config(config_path)
    now = _utc_now(now)
    mt5 = mt5_module or import_mt5_module()
    status = {
        "symbol": config.symbol,
        "demo_only": config.demo_only,
        "allow_demo_execution": config.allow_demo_execution,
        "allow_real_live": config.allow_real_live,
        "execution_enabled": config.execution_enabled,
        "magic_number": config.magic_number,
        "live_candidate_window_minutes": config.live_candidate_window_minutes,
        "require_latest_closed_candle_candidate": config.require_latest_closed_candle_candidate,
        "candidate_freshness_required": config.candidate_freshness_required,
        "orders_today": _trades_for_day(load_v51_demo_orders(output_dir), now.normalize()),
        "mt5_initialized": False,
        "account_connected": False,
        "account_demo": False,
        "symbol_visible": False,
        "spread_points": None,
        "reason": "",
    }
    if mt5 is None:
        status["reason"] = "MT5_NOT_AVAILABLE"
        return status

    initialized = False
    try:
        initialized = bool(mt5.initialize()) if callable(getattr(mt5, "initialize", None)) else False
        status["mt5_initialized"] = initialized
        if not initialized:
            status["reason"] = f"MT5_NOT_INITIALIZED: {_last_error(mt5)}"
            return status
        account = mt5.account_info()
        symbol = mt5.symbol_info(config.symbol)
        tick = mt5.symbol_info_tick(config.symbol) if symbol is not None else None
        status["account_connected"] = account is not None
        status["account_demo"] = _is_demo_account(mt5, account)
        status["symbol_visible"] = bool(getattr(symbol, "visible", False)) if symbol is not None else False
        status["spread_points"] = _spread_points(symbol, tick)
        status["reason"] = _validate_mt5_demo_state(mt5, config) or "OK"
        return status
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()


def read_mt5_closed_rates(mt5: Any, config: V51DemoIntradayConfig) -> pd.DataFrame:
    """Read recent closed OHLCV candles from MT5 demo."""
    timeframe = _mt5_timeframe(mt5, config.timeframe)
    bars = max(config.warmup_candles + config.selection_lookback_candles + 5, config.warmup_candles + 20)
    copy_rates = getattr(mt5, "copy_rates_from_pos", None)
    if not callable(copy_rates):
        raise RuntimeError("MT5 copy_rates_from_pos is unavailable")
    raw_rates = copy_rates(config.symbol, timeframe, 1, bars)
    if raw_rates is None or len(raw_rates) == 0:
        raise RuntimeError(f"No MT5 closed rates returned for {config.symbol}")
    rates = pd.DataFrame(raw_rates)
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(rates.columns):
        raise ValueError("MT5 rates are missing required OHLC columns")
    volume = "tick_volume" if "tick_volume" in rates.columns else "real_volume" if "real_volume" in rates.columns else None
    result = pd.DataFrame(
        {
            "Open": pd.to_numeric(rates["open"], errors="coerce").to_numpy(),
            "High": pd.to_numeric(rates["high"], errors="coerce").to_numpy(),
            "Low": pd.to_numeric(rates["low"], errors="coerce").to_numpy(),
            "Close": pd.to_numeric(rates["close"], errors="coerce").to_numpy(),
            "Volume": pd.to_numeric(rates[volume], errors="coerce").to_numpy() if volume else 1.0,
        },
        index=pd.to_datetime(rates["time"], unit="s", utc=True),
    )
    return result.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()


def select_best_v51_candidate(
    market_data: pd.DataFrame,
    config: V51DemoIntradayConfig,
    *,
    existing_orders: pd.DataFrame | None = None,
    trades_today: int = 0,
    open_positions: int = 0,
    spread_points: float | None = None,
    latest_closed_candle_time: pd.Timestamp | None = None,
) -> tuple[V51DemoCandidate | None, str]:
    """Select the best recent V51 candidate, not the first one seen."""
    log = build_demo_intraday_decision_log(
        market_data,
        config,
        starting_trades_today=trades_today,
        open_positions=open_positions,
        enforce_daily_limit=False,
    )
    if log.empty:
        return None, "no V51 closed-candle decisions were produced"

    log["candle_time_dt"] = pd.to_datetime(log["candle_time"], errors="coerce", utc=True)
    latest_day = _utc_timestamp(market_data.index[-1]).normalize()
    latest_log = log[log["candle_time_dt"].dt.normalize() == latest_day].tail(config.selection_lookback_candles).copy()
    if latest_log.empty:
        return None, "no V51 candidates on latest MT5 trading day"

    if latest_closed_candle_time is not None:
        latest_log = _filter_live_candidate_window(latest_log, config, latest_closed_candle_time)
        if latest_log.empty:
            return None, "no fresh live candidate on latest closed candle"

    accepted = latest_log[latest_log["decision"] == "ACCEPTED"].copy()
    if latest_closed_candle_time is not None and accepted.empty:
        return None, "no fresh live candidate on latest closed candle"

    if existing_orders is not None and not existing_orders.empty:
        accepted = accepted[
            ~accepted.apply(
                lambda row: _is_duplicate_order(existing_orders, str(row["signal_id"]), str(row["candle_time"])),
                axis=1,
            )
        ]
    if accepted.empty:
        reason = _best_no_trade_reason(latest_log)
        return None, reason

    for column in ["score", "score_gap", "risk_reward", "spread_cost", "slippage_estimate"]:
        accepted[column] = pd.to_numeric(accepted[column], errors="coerce")
    accepted = accepted.sort_values(
        ["score", "score_gap", "risk_reward", "spread_cost", "slippage_estimate", "candle_time_dt"],
        ascending=[False, False, False, True, True, False],
    )
    row = accepted.iloc[0]
    selection_reason = _live_selection_reason(row["candle_time_dt"], config, latest_closed_candle_time)
    candidate = V51DemoCandidate(
        signal_id=str(row["signal_id"]),
        candle_time=pd.Timestamp(row["candle_time_dt"]),
        symbol=config.symbol,
        side=str(row["side"]),
        lot_size=float(row["lot_size"]),
        entry_price=float(row["entry_price"]),
        stop_loss=_float_or_none(row["stop_loss"]),
        take_profit=_float_or_none(row["take_profit"]),
        risk_reward=_float_or_none(row["risk_reward"]),
        score=float(row["score"]),
        score_gap=float(row["score_gap"]),
        spread_cost=float(row["spread_cost"]),
        slippage_estimate=float(row["slippage_estimate"]),
        reason=str(row["reason"]),
        session=str(row.get("session", "")),
    )
    return candidate, selection_reason


def validate_v51_demo_candidate(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    existing_orders: pd.DataFrame | None = None,
) -> str | None:
    """Validate a selected V51 candidate before dry-run or demo submission."""
    if config.allow_real_live:
        return "allow_real_live=true blocks V51 demo execution"
    if candidate.stop_loss is None or candidate.take_profit is None:
        return "SL and TP are required for V51 demo execution"
    if candidate.side == "BUY" and not (candidate.stop_loss < candidate.entry_price < candidate.take_profit):
        return "invalid BUY SL/TP geometry"
    if candidate.side == "SELL" and not (candidate.take_profit < candidate.entry_price < candidate.stop_loss):
        return "invalid SELL SL/TP geometry"
    if candidate.risk_reward is None or candidate.risk_reward < config.min_risk_reward:
        value = 0.0 if candidate.risk_reward is None else candidate.risk_reward
        return f"RR {value:.2f} below {config.min_risk_reward:.2f}"
    if candidate.spread_cost > config.max_spread_cost:
        return f"spread cost {candidate.spread_cost:.2f} above {config.max_spread_cost:.2f}"
    if candidate.slippage_estimate > config.max_slippage_estimate:
        return f"slippage estimate {candidate.slippage_estimate:.2f} above {config.max_slippage_estimate:.2f}"
    if existing_orders is not None and _is_duplicate_order(existing_orders, candidate.signal_id, candidate.candle_time.isoformat()):
        return f"duplicate V51 signal/candle already traded: {candidate.signal_id}"
    return None


def ensure_v51_demo_execution_files(output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR) -> dict[str, Path]:
    """Create V51 demo execution CSV files when needed."""
    paths = v51_demo_execution_paths(output_dir)
    for path, columns in [
        (paths["orders"], V51_DEMO_ORDER_COLUMNS),
        (paths["log"], V51_DEMO_LOG_COLUMNS),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pd.DataFrame(columns=columns).to_csv(path, index=False)
        else:
            _ensure_csv_columns(path, columns)
    return paths


def v51_demo_execution_paths(output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR) -> dict[str, Path]:
    """Return V51 demo execution CSV paths."""
    directory = Path(output_dir)
    return {
        "orders": directory / "v51_demo_orders.csv",
        "log": directory / "v51_demo_execution_log.csv",
    }


def load_v51_demo_orders(output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR) -> pd.DataFrame:
    """Load V51 demo order log without creating files."""
    path = v51_demo_execution_paths(output_dir)["orders"]
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=V51_DEMO_ORDER_COLUMNS)
    frame = pd.read_csv(path)
    for column in V51_DEMO_ORDER_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[V51_DEMO_ORDER_COLUMNS]


def load_v51_demo_execution_log(output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR) -> pd.DataFrame:
    """Load V51 demo execution events without creating files."""
    path = v51_demo_execution_paths(output_dir)["log"]
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=V51_DEMO_LOG_COLUMNS)
    frame = pd.read_csv(path)
    for column in V51_DEMO_LOG_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[V51_DEMO_LOG_COLUMNS]


def append_v51_demo_order(
    output_dir: str | Path,
    result: V51DemoExecutionResult,
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    *,
    spread_points: float | None,
) -> None:
    """Append one V51 demo order attempt."""
    paths = ensure_v51_demo_execution_files(output_dir)
    row = {
        "timestamp": pd.Timestamp.now(tz=UTC).isoformat(),
        "signal_id": candidate.signal_id,
        "candle_time": candidate.candle_time.isoformat(),
        "symbol": config.symbol,
        "side": candidate.side,
        "lot_size": candidate.lot_size,
        "entry_price": candidate.entry_price,
        "stop_loss": candidate.stop_loss,
        "take_profit": candidate.take_profit,
        "risk_reward": candidate.risk_reward,
        "score": candidate.score,
        "score_gap": candidate.score_gap,
        "spread_points": spread_points,
        "spread_cost": candidate.spread_cost,
        "slippage_estimate": candidate.slippage_estimate,
        "status": result.status,
        "reason": result.reason,
        "mt5_retcode": result.mt5_retcode,
        "mt5_order": result.mt5_order,
        "mt5_deal": result.mt5_deal,
        "magic_number": config.magic_number,
        "comment": V51_DEMO_COMMENT,
        "dry_run": result.dry_run,
    }
    _append_csv(paths["orders"], row, V51_DEMO_ORDER_COLUMNS)


def append_v51_demo_log(
    output_dir: str | Path,
    result: V51DemoExecutionResult,
    *,
    event: str,
) -> None:
    """Append one V51 execution event, including NO_TRADE decisions."""
    paths = ensure_v51_demo_execution_files(output_dir)
    row = {
        "timestamp": pd.Timestamp.now(tz=UTC).isoformat(),
        "event": event,
        "status": result.status,
        "decision": "NO_TRADE" if result.status in {"NO_TRADE", "REJECTED", "ERROR", "MT5_NOT_AVAILABLE"} else result.status,
        "reason": result.reason,
        "signal_id": result.signal_id,
        "candle_time": result.candle_time.isoformat() if result.candle_time is not None else None,
        "symbol": result.symbol,
        "side": result.side,
        "now_utc": result.now_utc.isoformat() if result.now_utc is not None else None,
        "now_local": result.now_local,
        "candidate_age_minutes": result.candidate_age_minutes,
        "latest_closed_candle_time": result.latest_closed_candle_time.isoformat()
        if result.latest_closed_candle_time is not None
        else None,
        "selected_candidate_time": result.selected_candidate_time.isoformat() if result.selected_candidate_time is not None else None,
        "candidate_time_basis": result.candidate_time_basis,
        "time_alignment_status": result.time_alignment_status,
        "live_candidate_window_minutes": result.live_candidate_window_minutes,
        "require_latest_closed_candle_candidate": result.require_latest_closed_candle_candidate,
        "selection_reason": result.selection_reason,
        "current_bid": result.current_bid,
        "current_ask": result.current_ask,
        "expected_entry_price": result.expected_entry_price,
        "live_entry_price": result.live_entry_price,
        "slippage_points": result.slippage_points,
        "adverse_slippage_points": result.adverse_slippage_points,
        "max_slippage_points": result.max_slippage_points,
        "chase_distance_points": result.chase_distance_points,
        "max_chase_points": result.max_chase_points,
        "point_size": result.point_size,
        "spread_points": result.spread_points,
        "session": result.session,
        "score": result.score,
        "risk_reward": result.risk_reward,
        "mtf_final_bias": result.mtf_final_bias,
        "mtf_filter_enabled": result.mtf_filter_enabled,
        "mtf_filter_passed": result.mtf_filter_passed,
        "mtf_filter_reason": result.mtf_filter_reason,
        "dry_run": result.dry_run,
    }
    _append_csv(paths["log"], row, V51_DEMO_LOG_COLUMNS)


def evaluate_mtf_direction_filter(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    summary_path: str | Path | None = DEFAULT_V51_MTF_CONTEXT_SUMMARY_PATH,
    *,
    audit: MTFAuditContext | None = None,
) -> MTFDirectionFilterResult:
    """Apply the optional read-only MTF directional filter to a selected candidate."""
    audit = audit or load_mtf_audit_context(config, summary_path)
    if not audit.enabled:
        return MTFDirectionFilterResult(False, True, audit.final_bias, "mtf_filter_disabled")
    if config.require_mtf_data_ok and audit.data_issues:
        return MTFDirectionFilterResult(True, False, audit.final_bias, "mtf_data_not_ok")

    allowed = config.allowed_mtf_bias_for_buy if candidate.side == "BUY" else config.allowed_mtf_bias_for_sell
    if audit.final_bias == "MIXED":
        return MTFDirectionFilterResult(True, False, audit.final_bias, "mtf_final_bias_mixed")
    if audit.final_bias not in allowed:
        return MTFDirectionFilterResult(True, False, audit.final_bias, "mtf_direction_filter_blocked")
    return MTFDirectionFilterResult(True, True, audit.final_bias, "mtf_direction_filter_passed")


def load_mtf_audit_context(
    config: V51DemoIntradayConfig,
    summary_path: str | Path | None = DEFAULT_V51_MTF_CONTEXT_SUMMARY_PATH,
) -> MTFAuditContext:
    """Load MTF context once so all execution outcomes carry audit fields."""
    enabled = bool(config.use_mtf_context_filter)
    summary = _read_mtf_summary(summary_path)
    if summary is None:
        return MTFAuditContext(enabled, "UNKNOWN", None, ("summary=UNAVAILABLE",))
    final_bias = _summary_final_bias(summary)
    data_issues = tuple(_required_mtf_data_issues(summary))
    return MTFAuditContext(enabled, final_bias, summary, data_issues)


def _read_mtf_summary(summary_path: str | Path | None) -> pd.DataFrame | None:
    if summary_path is None:
        return None
    path = Path(summary_path)
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        summary = pd.read_csv(path)
    except Exception:
        return None
    return summary if not summary.empty else None


def _summary_final_bias(summary: pd.DataFrame) -> str:
    if "final_bias" not in summary.columns:
        return "UNKNOWN"
    bias_values = summary["final_bias"].dropna()
    if bias_values.empty:
        return "UNKNOWN"
    final_bias = str(bias_values.iloc[0]).strip().upper()
    return final_bias or "UNKNOWN"


def _required_mtf_data_issues(summary: pd.DataFrame) -> list[str]:
    issues = []
    if "timeframe" not in summary.columns:
        return ["M1=MISSING", "M5=MISSING"]
    for timeframe in ("M1", "M5"):
        rows = summary[summary["timeframe"].astype(str).str.upper() == timeframe]
        if rows.empty:
            issues.append(f"{timeframe}=MISSING")
            continue
        row = rows.iloc[0]
        data_status = str(row.get("data_status", row.get("status", "UNKNOWN"))).upper()
        used = _as_logged_bool(row.get("used_in_bias", False))
        if data_status != "OK" or not used:
            issues.append(f"{timeframe}={data_status},used_in_bias={used}")
    return issues


def _with_mtf_telemetry(telemetry: dict[str, Any], mtf_filter: MTFDirectionFilterResult) -> dict[str, Any]:
    result = dict(telemetry)
    result.update(
        {
            "mtf_final_bias": mtf_filter.final_bias,
            "mtf_filter_enabled": mtf_filter.enabled,
            "mtf_filter_passed": mtf_filter.passed,
            "mtf_filter_reason": mtf_filter.reason,
        }
    )
    return result


def _mtf_audit_telemetry(
    audit: MTFAuditContext,
    *,
    passed: bool | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "mtf_final_bias": audit.final_bias,
        "mtf_filter_enabled": audit.enabled,
        "mtf_filter_passed": passed,
        "mtf_filter_reason": reason,
    }


def _validate_execution_gates(config: V51DemoIntradayConfig) -> str | None:
    if config.allow_real_live:
        return "allow_real_live=true blocks V51 demo execution"
    if not config.demo_only:
        return "demo_only=false blocks V51 demo execution"
    if not config.allow_demo_execution:
        return "allow_demo_execution=false blocks V51 demo execution"
    if not config.execution_enabled:
        return "execution_enabled=false blocks V51 demo execution"
    return None


def _validate_mt5_demo_state(mt5: Any, config: V51DemoIntradayConfig) -> str | None:
    account = mt5.account_info()
    terminal = mt5.terminal_info() if hasattr(mt5, "terminal_info") else None
    if account is None:
        return "MT5 account is not connected"
    if not _is_demo_account(mt5, account):
        return "MT5 account is not demo"
    if not bool(getattr(account, "trade_allowed", False)) or not bool(getattr(terminal, "trade_allowed", True)):
        return "MT5 demo trading is not allowed"
    symbol = mt5.symbol_info(config.symbol)
    if symbol is None:
        return f"symbol not found: {config.symbol}"
    if not bool(getattr(symbol, "visible", False)):
        return f"symbol is not visible: {config.symbol}"
    disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", None)
    if disabled_mode is not None and getattr(symbol, "trade_mode", None) == disabled_mode:
        return f"symbol is not tradable: {config.symbol}"
    if mt5.symbol_info_tick(config.symbol) is None:
        return f"symbol tick is unavailable: {config.symbol}"
    return None


def _build_mt5_request(mt5: Any, config: V51DemoIntradayConfig, candidate: V51DemoCandidate) -> dict[str, Any]:
    symbol = mt5.symbol_info(config.symbol)
    tick = mt5.symbol_info_tick(config.symbol)
    price = float(getattr(tick, "ask" if candidate.side == "BUY" else "bid"))
    order_type = getattr(mt5, "ORDER_TYPE_BUY") if candidate.side == "BUY" else getattr(mt5, "ORDER_TYPE_SELL")
    filling_mode = getattr(symbol, "filling_mode", getattr(mt5, "ORDER_FILLING_IOC", 1))
    return {
        "action": getattr(mt5, "TRADE_ACTION_DEAL"),
        "symbol": config.symbol,
        "volume": candidate.lot_size,
        "type": order_type,
        "price": price,
        "sl": float(candidate.stop_loss),
        "tp": float(candidate.take_profit),
        "deviation": int(config.max_slippage_points),
        "magic": int(config.magic_number),
        "comment": V51_DEMO_COMMENT,
        "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
        "type_filling": filling_mode,
    }


def _result_from_response(
    mt5: Any,
    response: Any,
    candidate: V51DemoCandidate,
    *,
    telemetry: dict[str, Any] | None = None,
) -> V51DemoExecutionResult:
    if response is None:
        return _result(
            False,
            "ERROR",
            f"MT5 returned no response: {_last_error(mt5)}",
            dry_run=False,
            candidate=candidate,
            telemetry=telemetry,
        )
    retcode = _int_or_none(getattr(response, "retcode", None))
    success = retcode in _success_retcode_values(mt5)
    result = _result(
        accepted=success,
        status="SENT" if success else "ERROR",
        reason="V51 demo order accepted by MT5." if success else f"MT5 rejected V51 demo order: {getattr(response, 'comment', '')}",
        dry_run=False,
        signal_id=candidate.signal_id,
        candle_time=candidate.candle_time,
        symbol=candidate.symbol,
        side=candidate.side,
        candidate=candidate,
        telemetry=telemetry,
    )
    values = result.__dict__.copy()
    values.update(
        {
            "mt5_retcode": retcode,
            "mt5_order": _int_or_none(getattr(response, "order", None)),
            "mt5_deal": _int_or_none(getattr(response, "deal", None)),
        }
    )
    return V51DemoExecutionResult(**values)


def _result(
    accepted: bool,
    status: str,
    reason: str,
    *,
    dry_run: bool,
    candidate: V51DemoCandidate | None = None,
    telemetry: dict[str, Any] | None = None,
    signal_id: str | None = None,
    candle_time: pd.Timestamp | None = None,
    symbol: str | None = None,
    side: str | None = None,
) -> V51DemoExecutionResult:
    telemetry = telemetry or {}
    return V51DemoExecutionResult(
        accepted=accepted,
        status=status,
        reason=reason,
        dry_run=dry_run,
        signal_id=candidate.signal_id if candidate is not None else signal_id,
        candle_time=candidate.candle_time if candidate is not None else candle_time,
        symbol=candidate.symbol if candidate is not None else symbol,
        side=candidate.side if candidate is not None else side,
        now_utc=telemetry.get("now_utc"),
        now_local=telemetry.get("now_local"),
        candidate_age_minutes=telemetry.get("candidate_age_minutes"),
        latest_closed_candle_time=telemetry.get("latest_closed_candle_time"),
        selected_candidate_time=telemetry.get("selected_candidate_time"),
        candidate_time_basis=telemetry.get("candidate_time_basis"),
        time_alignment_status=telemetry.get("time_alignment_status"),
        live_candidate_window_minutes=telemetry.get("live_candidate_window_minutes"),
        require_latest_closed_candle_candidate=telemetry.get("require_latest_closed_candle_candidate"),
        selection_reason=telemetry.get("selection_reason"),
        current_bid=telemetry.get("current_bid"),
        current_ask=telemetry.get("current_ask"),
        expected_entry_price=telemetry.get("expected_entry_price"),
        live_entry_price=telemetry.get("live_entry_price"),
        slippage_points=telemetry.get("slippage_points"),
        adverse_slippage_points=telemetry.get("adverse_slippage_points"),
        max_slippage_points=telemetry.get("max_slippage_points"),
        chase_distance_points=telemetry.get("chase_distance_points"),
        max_chase_points=telemetry.get("max_chase_points"),
        point_size=telemetry.get("point_size"),
        spread_points=telemetry.get("spread_points"),
        session=telemetry.get("session") if telemetry.get("session") is not None else (candidate.session if candidate is not None else None),
        score=telemetry.get("score"),
        risk_reward=telemetry.get("risk_reward"),
        mtf_final_bias=telemetry.get("mtf_final_bias"),
        mtf_filter_enabled=telemetry.get("mtf_filter_enabled"),
        mtf_filter_passed=telemetry.get("mtf_filter_passed"),
        mtf_filter_reason=telemetry.get("mtf_filter_reason"),
    )


def _latest_closed_candle_time(data: pd.DataFrame) -> pd.Timestamp:
    latest = pd.Timestamp(data.index[-1])
    return latest.tz_localize(UTC) if latest.tzinfo is None else latest.tz_convert(UTC)


def _market_telemetry(
    config: V51DemoIntradayConfig,
    tick: Any,
    *,
    spread_points: float | None,
) -> dict[str, Any]:
    return {
        "current_bid": _float_or_none(getattr(tick, "bid", None)) if tick is not None else None,
        "current_ask": _float_or_none(getattr(tick, "ask", None)) if tick is not None else None,
        "max_slippage_points": float(config.max_slippage_points),
        "max_chase_points": float(config.max_chase_points),
        "spread_points": spread_points,
    }


def _selection_telemetry(
    config: V51DemoIntradayConfig,
    *,
    latest_closed_candle_time: pd.Timestamp,
    tick: Any,
    spread_points: float | None,
    selection_reason: str,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    telemetry = _market_telemetry(config, tick, spread_points=spread_points)
    telemetry.update(
        {
            **_time_alignment_telemetry(
                _utc_now(now),
                latest_closed_candle_time=latest_closed_candle_time,
                candidate=None,
                status="no_v51_candidate_to_filter",
            ),
            "latest_closed_candle_time": latest_closed_candle_time,
            "live_candidate_window_minutes": config.live_candidate_window_minutes,
            "require_latest_closed_candle_candidate": config.require_latest_closed_candle_candidate,
            "selection_reason": selection_reason,
        }
    )
    return telemetry


def _candidate_telemetry(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    *,
    latest_closed_candle_time: pd.Timestamp,
    tick: Any,
    spread_points: float | None,
    slippage_points: float | None,
    selection_reason: str,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    telemetry = _selection_telemetry(
        config,
        latest_closed_candle_time=latest_closed_candle_time,
        tick=tick,
        spread_points=spread_points,
        selection_reason=selection_reason,
        now=now,
    )
    telemetry.update(
        {
            **_time_alignment_telemetry(
                _utc_now(now),
                latest_closed_candle_time=latest_closed_candle_time,
                candidate=candidate,
                status="OK",
            ),
            "candidate_age_minutes": _candidate_age_minutes(candidate, latest_closed_candle_time),
            "selected_candidate_time": _utc_timestamp(candidate.candle_time),
            "expected_entry_price": candidate.entry_price,
            "slippage_points": slippage_points,
            "session": candidate.session,
            "score": candidate.score,
            "risk_reward": candidate.risk_reward,
        }
    )
    return telemetry


def _candidate_age_minutes(candidate: V51DemoCandidate, latest_closed_candle_time: pd.Timestamp) -> float:
    candidate_time = _utc_timestamp(candidate.candle_time)
    latest_time = _utc_timestamp(latest_closed_candle_time)
    return (latest_time - candidate_time).total_seconds() / 60.0


def _time_alignment_telemetry(
    now: pd.Timestamp,
    *,
    latest_closed_candle_time: pd.Timestamp | None,
    candidate: V51DemoCandidate | None,
    status: str,
) -> dict[str, Any]:
    latest_time = _utc_timestamp(latest_closed_candle_time) if latest_closed_candle_time is not None else None
    candidate_time = _utc_timestamp(candidate.candle_time) if candidate is not None else None
    age = None
    if latest_time is not None and candidate_time is not None:
        age = (latest_time - candidate_time).total_seconds() / 60.0
    return {
        "now_utc": _utc_now(now),
        "now_local": _local_time_string(now),
        "latest_closed_candle_time": latest_time,
        "selected_candidate_time": candidate_time,
        "candidate_age_minutes": age,
        "candidate_time_basis": "mt5_closed_candle_utc",
        "time_alignment_status": status,
    }


def _no_candidate_telemetry(
    now: pd.Timestamp,
    mtf_audit: MTFAuditContext,
    *,
    latest_closed_candle_time: pd.Timestamp | None = None,
) -> dict[str, Any]:
    return {
        **_time_alignment_telemetry(
            now,
            latest_closed_candle_time=latest_closed_candle_time,
            candidate=None,
            status="no_v51_candidate_to_filter",
        ),
        **_mtf_audit_telemetry(
            mtf_audit,
            passed=False if mtf_audit.enabled else True,
            reason="no_v51_candidate_to_filter" if mtf_audit.enabled else "mtf_filter_disabled",
        ),
    }


def _local_time_string(now: pd.Timestamp) -> str:
    value = _utc_now(now)
    local_tz = datetime.now().astimezone().tzinfo
    return value.tz_convert(local_tz).isoformat()


def _candidate_time_guard_reason(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    latest_closed_candle_time: pd.Timestamp,
    now: pd.Timestamp,
) -> str | None:
    age_minutes = _candidate_age_minutes(candidate, latest_closed_candle_time)
    now_delta_minutes = (_utc_timestamp(candidate.candle_time) - _utc_now(now)).total_seconds() / 60.0
    if now_delta_minutes > FUTURE_CANDIDATE_TOLERANCE_MINUTES:
        return "candidate_time_in_future"
    if age_minutes < -FUTURE_CANDIDATE_TOLERANCE_MINUTES:
        return "candidate_time_in_future"
    if age_minutes > float(config.live_candidate_window_minutes):
        return "candidate_stale"
    return None


def _candidate_stale_reason(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    latest_closed_candle_time: pd.Timestamp,
) -> str | None:
    if not config.candidate_freshness_required:
        return None
    age_minutes = _candidate_age_minutes(candidate, latest_closed_candle_time)
    if _utc_timestamp(candidate.candle_time) == _utc_timestamp(latest_closed_candle_time):
        return None
    if 0 <= age_minutes <= config.max_candidate_age_minutes:
        return None
    return "candidate_stale"


def _filter_live_candidate_window(
    log: pd.DataFrame,
    config: V51DemoIntradayConfig,
    latest_closed_candle_time: pd.Timestamp,
) -> pd.DataFrame:
    latest_time = _utc_timestamp(latest_closed_candle_time)
    candidate_times = pd.to_datetime(log["candle_time_dt"], errors="coerce", utc=True)
    if config.require_latest_closed_candle_candidate:
        mask = candidate_times == latest_time
    else:
        ages = (latest_time - candidate_times).dt.total_seconds() / 60.0
        mask = (ages >= 0) & (ages <= config.live_candidate_window_minutes)
    return log[mask].copy()


def _live_selection_reason(
    candidate_time: Any,
    config: V51DemoIntradayConfig,
    latest_closed_candle_time: pd.Timestamp | None,
) -> str:
    if latest_closed_candle_time is None:
        return "V51 candidate selected"
    latest_time = _utc_timestamp(latest_closed_candle_time)
    selected_time = _utc_timestamp(candidate_time)
    if selected_time == latest_time:
        return "V51 live candidate selected on latest closed candle"
    age_minutes = (latest_time - selected_time).total_seconds() / 60.0
    return (
        "V51 live candidate selected within live candidate window: "
        f"age_minutes={age_minutes:.1f}, "
        f"live_candidate_window_minutes={config.live_candidate_window_minutes}"
    )


def _rejected_signal_cooldown_reason(
    execution_log: pd.DataFrame,
    signal_id: str,
    config: V51DemoIntradayConfig,
    now: pd.Timestamp,
) -> str | None:
    if execution_log.empty or "signal_id" not in execution_log.columns:
        return None
    same_signal = execution_log[execution_log["signal_id"].astype(str) == str(signal_id)].copy()
    if same_signal.empty:
        return None
    reasons = same_signal.get("reason", pd.Series([""] * len(same_signal), index=same_signal.index)).astype(str).str.lower()
    statuses = same_signal.get("status", pd.Series([""] * len(same_signal), index=same_signal.index)).astype(str).str.upper()
    retry_rejections = reasons.str.contains(
        "slippage|candidate_stale|candidate_time_in_future|price_chase_distance_exceeded|duplicate rejected signal cooldown",
        regex=True,
    )
    rejected_rows = same_signal[statuses.isin({"NO_TRADE", "REJECTED"}) & retry_rejections].copy()
    if rejected_rows.empty:
        return None
    timestamps = pd.to_datetime(rejected_rows["timestamp"], errors="coerce", utc=True)
    elapsed = (now - timestamps).dt.total_seconds() / 60.0
    recent = elapsed[(elapsed >= 0) & (elapsed <= config.rejected_signal_cooldown_minutes)]
    if recent.empty:
        return None
    return (
        "duplicate rejected signal cooldown: "
        f"signal_id={signal_id}, "
        f"last_rejected_minutes_ago={recent.min():.1f}, "
        f"cooldown_minutes={config.rejected_signal_cooldown_minutes}"
    )


def _stale_data_reason(data: pd.DataFrame, config: V51DemoIntradayConfig, now: pd.Timestamp) -> str | None:
    if data.empty:
        return "MT5 returned no closed candles"
    latest = _latest_closed_candle_time(data)
    age_minutes = (now - latest).total_seconds() / 60.0
    if age_minutes > config.max_data_age_minutes:
        return f"MT5 data stale: latest closed candle is {age_minutes:.1f} minutes old"
    return None


def _trades_for_day(orders: pd.DataFrame, day: pd.Timestamp) -> int:
    if orders.empty or "candle_time" not in orders.columns:
        return 0
    times = pd.to_datetime(orders["candle_time"], errors="coerce", utc=True)
    statuses = orders.get("status", pd.Series([""] * len(orders), index=orders.index)).astype(str).str.upper()
    return int(((times.dt.normalize() == day.normalize()) & statuses.isin(ACTIVE_DEMO_STATUSES)).sum())


def _is_duplicate_order(orders: pd.DataFrame, signal_id: str, candle_time: str) -> bool:
    if orders.empty:
        return False
    statuses = orders.get("status", pd.Series([""] * len(orders), index=orders.index)).astype(str).str.upper()
    active = orders[statuses.isin(ACTIVE_DEMO_STATUSES)].copy()
    if active.empty:
        return False
    if "signal_id" in active.columns and (active["signal_id"].astype(str) == str(signal_id)).any():
        return True
    if "candle_time" in active.columns:
        existing = pd.to_datetime(active["candle_time"], errors="coerce", utc=True)
        target = pd.to_datetime(candle_time, errors="coerce", utc=True)
        if pd.notna(target) and (existing == target).any():
            return True
    return False


def _has_open_v51_position(mt5: Any, config: V51DemoIntradayConfig) -> bool:
    positions = mt5.positions_get(symbol=config.symbol) if hasattr(mt5, "positions_get") else None
    if positions is None:
        return False
    for position in positions:
        magic = int(getattr(position, "magic", -1) or -1)
        comment = str(getattr(position, "comment", ""))
        if magic == int(config.magic_number) or V51_DEMO_COMMENT in comment:
            return True
    return False


def _best_no_trade_reason(log: pd.DataFrame) -> str:
    if log.empty:
        return "no V51 closed-candle candidates available"
    ranked = log.copy()
    ranked["score"] = pd.to_numeric(ranked["score"], errors="coerce").fillna(0.0)
    ranked["score_gap"] = pd.to_numeric(ranked["score_gap"], errors="coerce").fillna(0.0)
    ranked = ranked.sort_values(["score", "score_gap"], ascending=[False, False])
    reason = str(ranked.iloc[0].get("reason", "no V51 candidate passed gates"))
    if "duplicate" not in reason.lower() and (log["decision"] == "ACCEPTED").any():
        return "best V51 candidates were already traded for this signal/candle"
    return "no V51 candidate passed gates: " + reason


def _mt5_timeframe(mt5: Any, timeframe: str) -> Any:
    lookup = {
        "1m": "TIMEFRAME_M1",
        "5m": "TIMEFRAME_M5",
        "15m": "TIMEFRAME_M15",
        "30m": "TIMEFRAME_M30",
        "1h": "TIMEFRAME_H1",
    }
    attr = lookup.get(str(timeframe).lower(), "TIMEFRAME_M15")
    return getattr(mt5, attr, 15)


def _is_demo_account(mt5: Any, account: Any) -> bool:
    if account is None:
        return False
    trade_mode = getattr(account, "trade_mode", None)
    demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
    real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", None)
    if demo_mode is not None and trade_mode == demo_mode:
        return True
    if real_mode is not None and trade_mode == real_mode:
        return False
    descriptor = " ".join(str(getattr(account, field, "")) for field in ("server", "company", "name")).lower()
    return "demo" in descriptor and "real" not in descriptor


def _spread_points(symbol: Any, tick: Any) -> float | None:
    if symbol is None:
        return None
    symbol_spread = _float_or_none(getattr(symbol, "spread", None))
    point = _float_or_none(getattr(symbol, "point", None)) or 0.0
    tick_spread = None
    if tick is not None and point > 0:
        ask = _float_or_none(getattr(tick, "ask", None))
        bid = _float_or_none(getattr(tick, "bid", None))
        if ask is not None and bid is not None:
            tick_spread = max(0.0, (ask - bid) / point)
    spreads = [value for value in (symbol_spread, tick_spread) if value is not None]
    return max(spreads) if spreads else None


def _slippage_points(side: str, expected_price: float, symbol: Any, tick: Any) -> float | None:
    point = _float_or_none(getattr(symbol, "point", None)) or 0.0
    if tick is None or point <= 0:
        return None
    current = _float_or_none(getattr(tick, "ask" if side == "BUY" else "bid", None))
    if current is None:
        return None
    return abs(current - expected_price) / point


def _live_price_quality(
    candidate: V51DemoCandidate,
    config: V51DemoIntradayConfig,
    symbol: Any,
    tick: Any,
) -> LivePriceQuality:
    point = _float_or_none(getattr(symbol, "point", None)) or 0.0
    if tick is None or point <= 0:
        return LivePriceQuality(None, candidate.entry_price, None, None, point or None, "live_price_unavailable")
    live_entry = _float_or_none(getattr(tick, "ask" if candidate.side == "BUY" else "bid", None))
    if live_entry is None:
        return LivePriceQuality(None, candidate.entry_price, None, None, point, "live_price_unavailable")
    if candidate.side == "BUY":
        adverse = max(0.0, live_entry - candidate.entry_price) / point
    else:
        adverse = max(0.0, candidate.entry_price - live_entry) / point
    chase = abs(live_entry - candidate.entry_price) / point
    if adverse > float(config.max_slippage_points):
        return LivePriceQuality(live_entry, candidate.entry_price, adverse, chase, point, "adverse_slippage_exceeded")
    if chase > float(config.max_chase_points):
        return LivePriceQuality(live_entry, candidate.entry_price, adverse, chase, point, "price_chase_distance_exceeded")
    return LivePriceQuality(live_entry, candidate.entry_price, adverse, chase, point)


def _price_quality_telemetry(price_check: LivePriceQuality) -> dict[str, Any]:
    return {
        "expected_entry_price": price_check.expected_entry_price,
        "live_entry_price": price_check.live_entry_price,
        "slippage_points": price_check.adverse_slippage_points,
        "adverse_slippage_points": price_check.adverse_slippage_points,
        "chase_distance_points": price_check.chase_distance_points,
        "point_size": price_check.point_size,
    }


def _reprice_candidate_from_live_entry(
    candidate: V51DemoCandidate,
    live_entry_price: float | None,
) -> tuple[V51DemoCandidate, str | None]:
    if live_entry_price is None:
        return candidate, "live_price_unavailable"
    if candidate.stop_loss is None or candidate.take_profit is None:
        return candidate, "repriced_candidate_invalid: SL and TP are required"
    if candidate.side == "BUY":
        risk_distance = candidate.entry_price - candidate.stop_loss
        reward_distance = candidate.take_profit - candidate.entry_price
        stop_loss = live_entry_price - risk_distance
        take_profit = live_entry_price + reward_distance
    else:
        risk_distance = candidate.stop_loss - candidate.entry_price
        reward_distance = candidate.entry_price - candidate.take_profit
        stop_loss = live_entry_price + risk_distance
        take_profit = live_entry_price - reward_distance
    if risk_distance <= 0 or reward_distance <= 0:
        return candidate, "repriced_candidate_invalid: invalid original SL/TP geometry"
    risk_reward = reward_distance / risk_distance
    return (
        replace(
            candidate,
            entry_price=float(live_entry_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            risk_reward=float(risk_reward),
        ),
        None,
    )


def _success_retcode_values(mt5: Any) -> set[int]:
    values = {
        _int_or_none(getattr(mt5, "TRADE_RETCODE_DONE", None)),
        _int_or_none(getattr(mt5, "TRADE_RETCODE_PLACED", None)),
    }
    return {value for value in values if value is not None}


def _ensure_csv_columns(path: Path, columns: list[str]) -> None:
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        pd.DataFrame(columns=columns).to_csv(path, index=False)
        return
    missing = [column for column in columns if column not in frame.columns]
    if not missing:
        return
    for column in missing:
        frame[column] = pd.NA
    frame[columns].to_csv(path, index=False)


def _append_csv(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    pd.DataFrame([row], columns=columns).to_csv(path, mode="a", header=header, index=False)


def _utc_now(now: pd.Timestamp | None) -> pd.Timestamp:
    if now is None:
        return pd.Timestamp.now(tz=UTC)
    value = pd.Timestamp(now)
    return value.tz_localize(UTC) if value.tzinfo is None else value.tz_convert(UTC)


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize(UTC) if timestamp.tzinfo is None else timestamp.tz_convert(UTC)


def _last_error(mt5: Any) -> Any:
    last_error = getattr(mt5, "last_error", None)
    return last_error() if callable(last_error) else "unknown"


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_logged_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
