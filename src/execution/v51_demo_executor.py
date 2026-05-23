"""V51 demo-only MT5 execution gate.

This module connects the V51 demo intraday candidate to MT5 demo execution.
It never enables real live trading and records V51-specific execution logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
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
V51_DEMO_COMMENT = "V51_DEMO"

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


def run_v51_demo_execution_once(
    *,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR,
    mt5_module: Any | None = None,
    dry_run: bool = True,
    now: pd.Timestamp | None = None,
) -> V51DemoExecutionResult:
    """Run one gated V51 demo execution attempt."""
    config = load_v51_config(config_path)
    now = _utc_now(now)
    gate_error = _validate_execution_gates(config)
    if gate_error is not None:
        result = _result(False, "REJECTED", gate_error, dry_run=dry_run)
        append_v51_demo_log(output_dir, result, event="config_gate")
        return result

    mt5 = mt5_module or import_mt5_module()
    if mt5 is None:
        result = _result(False, "MT5_NOT_AVAILABLE", "Python MetaTrader5 package is not available.", dry_run=dry_run)
        append_v51_demo_log(output_dir, result, event="mt5_unavailable")
        return result

    initialized = False
    try:
        initialized = bool(mt5.initialize()) if callable(getattr(mt5, "initialize", None)) else False
        if not initialized:
            result = _result(False, "ERROR", f"MT5_NOT_INITIALIZED: {_last_error(mt5)}", dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="mt5_initialize")
            return result

        market_error = _validate_mt5_demo_state(mt5, config)
        if market_error is not None:
            result = _result(False, "REJECTED", market_error, dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="broker_gate")
            return result

        try:
            rates = read_mt5_closed_rates(mt5, config)
        except Exception as exc:
            result = _result(False, "NO_TRADE", f"MT5 data unavailable: {exc}", dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result
        stale_reason = _stale_data_reason(rates, config, now)
        if stale_reason is not None:
            result = _result(False, "NO_TRADE", stale_reason, dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        order_log = load_v51_demo_orders(output_dir)
        trading_day = pd.Timestamp(rates.index[-1]).normalize()
        trades_today = _trades_for_day(order_log, trading_day)
        if trades_today >= config.max_trades_per_day:
            result = _result(
                False,
                "NO_TRADE",
                f"max trades per day reached ({config.max_trades_per_day})",
                dry_run=dry_run,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        if _has_open_v51_position(mt5, config):
            result = _result(False, "NO_TRADE", "existing open V51_DEMO position blocks new demo order", dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        spread_points = _spread_points(mt5.symbol_info(config.symbol), mt5.symbol_info_tick(config.symbol))
        if spread_points is not None and spread_points > config.max_spread_points:
            result = _result(
                False,
                "NO_TRADE",
                f"spread {spread_points:.1f} points exceeds max {config.max_spread_points:.1f}",
                dry_run=dry_run,
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
        )
        if candidate is None:
            result = _result(False, "NO_TRADE", no_trade_reason, dry_run=dry_run)
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        candidate_error = validate_v51_demo_candidate(candidate, config, order_log)
        if candidate_error is not None:
            result = _result(False, "REJECTED", candidate_error, dry_run=dry_run, candidate=candidate)
            append_v51_demo_log(output_dir, result, event="candidate_gate")
            return result

        tick = mt5.symbol_info_tick(config.symbol)
        slippage = _slippage_points(candidate.side, candidate.entry_price, mt5.symbol_info(config.symbol), tick)
        if slippage is not None and slippage > config.max_slippage_points:
            result = _result(
                False,
                "NO_TRADE",
                f"slippage {slippage:.1f} points exceeds max {config.max_slippage_points:.1f}",
                dry_run=dry_run,
                candidate=candidate,
            )
            append_v51_demo_log(output_dir, result, event="no_trade")
            return result

        if dry_run:
            result = _result(True, "DRY_RUN", "V51 dry-run accepted; no MT5 order was submitted.", dry_run=True, candidate=candidate)
            append_v51_demo_order(output_dir, result, candidate, config, spread_points=spread_points)
            append_v51_demo_log(output_dir, result, event="dry_run")
            return result

        request = _build_mt5_request(mt5, config, candidate)
        order_send = getattr(mt5, "order_send", None)
        if not callable(order_send):
            result = _result(False, "ERROR", "MT5 order submission function is unavailable.", dry_run=False, candidate=candidate)
            append_v51_demo_log(output_dir, result, event="submit_error")
            return result

        response = order_send(request)
        result = _result_from_response(mt5, response, candidate)
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

    log["candle_time_dt"] = pd.to_datetime(log["candle_time"], errors="coerce")
    latest_day = pd.Timestamp(market_data.index[-1]).normalize()
    latest_log = log[log["candle_time_dt"].dt.normalize() == latest_day].tail(config.selection_lookback_candles).copy()
    if latest_log.empty:
        return None, "no V51 candidates on latest MT5 trading day"

    accepted = latest_log[latest_log["decision"] == "ACCEPTED"].copy()
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
    )
    return candidate, "V51 candidate selected"


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
        "dry_run": result.dry_run,
    }
    _append_csv(paths["log"], row, V51_DEMO_LOG_COLUMNS)


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


def _result_from_response(mt5: Any, response: Any, candidate: V51DemoCandidate) -> V51DemoExecutionResult:
    if response is None:
        return _result(False, "ERROR", f"MT5 returned no response: {_last_error(mt5)}", dry_run=False, candidate=candidate)
    retcode = _int_or_none(getattr(response, "retcode", None))
    success = retcode in _success_retcode_values(mt5)
    return V51DemoExecutionResult(
        accepted=success,
        status="SENT" if success else "ERROR",
        reason="V51 demo order accepted by MT5." if success else f"MT5 rejected V51 demo order: {getattr(response, 'comment', '')}",
        dry_run=False,
        signal_id=candidate.signal_id,
        candle_time=candidate.candle_time,
        symbol=candidate.symbol,
        side=candidate.side,
        mt5_retcode=retcode,
        mt5_order=_int_or_none(getattr(response, "order", None)),
        mt5_deal=_int_or_none(getattr(response, "deal", None)),
    )


def _result(
    accepted: bool,
    status: str,
    reason: str,
    *,
    dry_run: bool,
    candidate: V51DemoCandidate | None = None,
) -> V51DemoExecutionResult:
    return V51DemoExecutionResult(
        accepted=accepted,
        status=status,
        reason=reason,
        dry_run=dry_run,
        signal_id=candidate.signal_id if candidate is not None else None,
        candle_time=candidate.candle_time if candidate is not None else None,
        symbol=candidate.symbol if candidate is not None else None,
        side=candidate.side if candidate is not None else None,
    )


def _stale_data_reason(data: pd.DataFrame, config: V51DemoIntradayConfig, now: pd.Timestamp) -> str | None:
    if data.empty:
        return "MT5 returned no closed candles"
    latest = pd.Timestamp(data.index[-1])
    if latest.tzinfo is None:
        latest = latest.tz_localize(UTC)
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


def _success_retcode_values(mt5: Any) -> set[int]:
    values = {
        _int_or_none(getattr(mt5, "TRADE_RETCODE_DONE", None)),
        _int_or_none(getattr(mt5, "TRADE_RETCODE_PLACED", None)),
    }
    return {value for value in values if value is not None}


def _append_csv(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    pd.DataFrame([row], columns=columns).to_csv(path, mode="a", header=header, index=False)


def _utc_now(now: pd.Timestamp | None) -> pd.Timestamp:
    if now is None:
        return pd.Timestamp.now(tz=UTC)
    value = pd.Timestamp(now)
    return value.tz_localize(UTC) if value.tzinfo is None else value.tz_convert(UTC)


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


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
