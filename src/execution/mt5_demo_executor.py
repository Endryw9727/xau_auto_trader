"""MT5 demo execution layer with strict safety gates.

This module is separate from paper-forward and real live trading. It can submit
demo-only MT5 market requests only after explicit demo execution config gates
are enabled and a demo account is verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import yaml


DEFAULT_DEMO_EXECUTION_CONFIG_PATH = Path("config/demo_execution.yaml")
DEFAULT_DEMO_EXECUTION_LOCAL_CONFIG_PATH = Path("config/demo_execution.local.yaml")
DEFAULT_DEMO_EXECUTION_OUTPUT_DIR = Path("reports/demo_execution")

DEMO_ORDER_COLUMNS = [
    "timestamp",
    "signal_id",
    "symbol",
    "side",
    "volume",
    "entry_price",
    "stop_loss",
    "take_profit",
    "status",
    "reason",
    "mt5_retcode",
    "mt5_order",
    "mt5_deal",
    "magic_number",
    "dry_run",
]
DEMO_POSITION_COLUMNS = [
    "timestamp",
    "ticket",
    "symbol",
    "side",
    "volume",
    "price_open",
    "price_current",
    "profit",
    "magic_number",
    "comment",
]
DEMO_CLOSED_TRADE_COLUMNS = [
    "timestamp",
    "ticket",
    "symbol",
    "side",
    "volume",
    "price_open",
    "price_close",
    "profit",
    "magic_number",
    "comment",
]
DEMO_EQUITY_COLUMNS = ["timestamp", "balance", "equity", "margin", "free_margin", "currency"]
DEMO_LOG_COLUMNS = ["timestamp", "event", "status", "reason", "signal_id", "symbol", "side", "dry_run"]


@dataclass(frozen=True)
class DemoExecutionConfig:
    """Config for MT5 demo execution gates."""

    broker_name: str
    platform: str
    symbol: str
    demo_only: bool
    allow_demo_execution: bool
    allow_real_live: bool
    execution_enabled: bool
    min_lot: float
    lot_step: float
    max_lot: float
    max_trades_per_day: int
    max_open_positions: int
    magic_number: int
    max_spread_points: float
    max_slippage_points: int
    require_sl: bool
    require_tp: bool


@dataclass(frozen=True)
class DemoOrderRequest:
    """Demo market request built from a closed-candle signal."""

    signal_id: str
    side: Literal["BUY", "SELL"]
    volume: float
    stop_loss: float | None
    take_profit: float | None
    expected_price: float | None = None
    comment: str = ""


@dataclass(frozen=True)
class DemoExecutionResult:
    """Result of a dry-run or demo MT5 request."""

    accepted: bool
    status: str
    reason: str
    signal_id: str
    dry_run: bool
    mt5_retcode: int | None = None
    mt5_order: int | None = None
    mt5_deal: int | None = None


@dataclass(frozen=True)
class DemoExecutionReadiness:
    """Readiness snapshot for MT5 demo execution."""

    status: str
    reason: str
    mt5_initialized: bool
    account_connected: bool
    account_demo: bool
    trade_allowed: bool
    symbol_found: bool
    symbol_visible: bool
    volume_min: float | None
    volume_step: float | None
    stops_level: int | None
    filling_mode: int | None
    spread_current: float | None


def load_demo_execution_config(
    path: str | Path = DEFAULT_DEMO_EXECUTION_CONFIG_PATH,
) -> DemoExecutionConfig:
    """Load and validate demo execution config."""
    config_path = Path(path)
    base_raw = _load_yaml_mapping(config_path)
    local_path = _local_demo_execution_config_path(config_path)
    local_raw = _load_yaml_mapping(local_path) if local_path.exists() else {}
    raw = _merge_demo_execution_config(base_raw, local_raw)
    _validate_demo_execution_config_source_safety(base_raw, local_raw, raw)

    config = DemoExecutionConfig(
        broker_name=str(raw.get("broker_name", "axi_demo")),
        platform=str(raw.get("platform", "mt5")),
        symbol=str(raw.get("symbol", "XAUUSD-P")),
        demo_only=_as_bool(raw.get("demo_only", False)),
        allow_demo_execution=_as_bool(raw.get("allow_demo_execution", False)),
        allow_real_live=_as_bool(raw.get("allow_real_live", False)),
        execution_enabled=_as_bool(raw.get("execution_enabled", False)),
        min_lot=float(raw.get("min_lot", 0.01)),
        lot_step=float(raw.get("lot_step", 0.01)),
        max_lot=float(raw.get("max_lot", 0.01)),
        max_trades_per_day=int(raw.get("max_trades_per_day", 2)),
        max_open_positions=int(raw.get("max_open_positions", 1)),
        magic_number=int(raw.get("magic_number", 502050)),
        max_spread_points=float(raw.get("max_spread_points", 80)),
        max_slippage_points=int(raw.get("max_slippage_points", 20)),
        require_sl=_as_bool(raw.get("require_sl", True)),
        require_tp=_as_bool(raw.get("require_tp", True)),
    )
    validate_demo_execution_config(config)
    return config


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid demo execution config: {path}")
    return raw


def _local_demo_execution_config_path(config_path: Path) -> Path:
    if config_path == DEFAULT_DEMO_EXECUTION_CONFIG_PATH:
        return DEFAULT_DEMO_EXECUTION_LOCAL_CONFIG_PATH
    return config_path.with_name(f"{config_path.stem}.local{config_path.suffix}")


def _merge_demo_execution_config(base: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(local)
    return merged


def _validate_demo_execution_config_source_safety(
    base: dict[str, Any],
    local: dict[str, Any],
    merged: dict[str, Any],
) -> None:
    if _as_bool(base.get("allow_real_live", False)) or _as_bool(local.get("allow_real_live", False)):
        raise PermissionError("allow_real_live must remain false")

    for field in ("allow_demo_execution", "execution_enabled"):
        if _as_bool(base.get(field, False)):
            raise PermissionError(f"{field}=true is only allowed in local demo-safe config")
        if _as_bool(merged.get(field, False)) and not _as_bool(local.get(field, False)):
            raise PermissionError(f"{field}=true is only allowed in local demo-safe config")

    demo_execution_requested = _as_bool(merged.get("allow_demo_execution", False)) or _as_bool(
        merged.get("execution_enabled", False)
    )
    if demo_execution_requested and (
        not _as_bool(merged.get("demo_only", False)) or _as_bool(merged.get("allow_real_live", False))
    ):
        raise PermissionError("demo execution can be enabled only with demo_only=true and allow_real_live=false")


def validate_demo_execution_config(config: DemoExecutionConfig) -> None:
    """Validate hard safety invariants."""
    if config.platform.lower() != "mt5":
        raise ValueError("demo execution currently supports platform=mt5 only")
    if not config.demo_only:
        raise PermissionError("demo execution requires demo_only=true")
    if config.allow_real_live:
        raise PermissionError("allow_real_live must remain false")
    if config.min_lot <= 0 or config.lot_step <= 0 or config.max_lot <= 0:
        raise ValueError("lot sizes must be positive")
    if config.max_lot < config.min_lot:
        raise ValueError("max_lot must be greater than or equal to min_lot")
    if config.max_open_positions <= 0 or config.max_trades_per_day <= 0:
        raise ValueError("max limits must be positive")
    if not config.require_sl or not config.require_tp:
        raise PermissionError("demo execution requires SL and TP")


def import_mt5_module() -> Any | None:
    """Import MetaTrader5 package if available on the host."""
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError:
        return None
    return mt5


def check_demo_execution_readiness(
    *,
    config_path: str | Path = DEFAULT_DEMO_EXECUTION_CONFIG_PATH,
    mt5_module: Any | None = None,
) -> DemoExecutionReadiness:
    """Check MT5 demo readiness without submitting any request."""
    try:
        config = load_demo_execution_config(config_path)
    except Exception as exc:
        return _readiness_error(str(exc))

    mt5 = mt5_module or import_mt5_module()
    if mt5 is None:
        return _readiness_error("MT5_NOT_AVAILABLE: Python MetaTrader5 package is not available.")

    initialized = False
    try:
        initialize = getattr(mt5, "initialize", None)
        initialized = bool(initialize()) if callable(initialize) else False
        if not initialized:
            return _readiness_error(f"MT5_NOT_INITIALIZED: {_last_error(mt5)}")

        account = mt5.account_info()
        terminal = mt5.terminal_info() if hasattr(mt5, "terminal_info") else None
        symbol = mt5.symbol_info(config.symbol)
        tick = mt5.symbol_info_tick(config.symbol) if symbol is not None and hasattr(mt5, "symbol_info_tick") else None

        account_connected = account is not None
        account_demo = _is_demo_account(mt5, account)
        trade_allowed = bool(getattr(account, "trade_allowed", False)) and bool(getattr(terminal, "trade_allowed", True))
        symbol_found = symbol is not None
        symbol_visible = bool(getattr(symbol, "visible", False)) if symbol is not None else False
        spread = _spread_points(symbol, tick)

        if not account_connected:
            status, reason = "ERROR", "MT5 account is not connected."
        elif not account_demo:
            status, reason = "ERROR", "MT5 account is not demo; demo execution is blocked."
        elif not trade_allowed:
            status, reason = "ERROR", "MT5 trading is not allowed for this demo account/terminal."
        elif not symbol_found:
            status, reason = "ERROR", f"Symbol not found: {config.symbol}"
        elif not symbol_visible:
            status, reason = "ERROR", f"Symbol is not visible: {config.symbol}"
        elif spread is not None and spread > config.max_spread_points:
            status, reason = "WARNING", f"Spread {spread:.1f} points exceeds max {config.max_spread_points:.1f}."
        else:
            status, reason = "OK", "MT5 demo execution readiness checks passed."

        return DemoExecutionReadiness(
            status=status,
            reason=reason,
            mt5_initialized=initialized,
            account_connected=account_connected,
            account_demo=account_demo,
            trade_allowed=trade_allowed,
            symbol_found=symbol_found,
            symbol_visible=symbol_visible,
            volume_min=_float_or_none(getattr(symbol, "volume_min", None)),
            volume_step=_float_or_none(getattr(symbol, "volume_step", None)),
            stops_level=_int_or_none(getattr(symbol, "trade_stops_level", None)),
            filling_mode=_int_or_none(getattr(symbol, "filling_mode", None)),
            spread_current=spread,
        )
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()


class MT5DemoExecutor:
    """Strict demo-only MT5 request executor."""

    def __init__(
        self,
        config: DemoExecutionConfig,
        *,
        mt5_module: Any | None = None,
        output_dir: str | Path = DEFAULT_DEMO_EXECUTION_OUTPUT_DIR,
    ) -> None:
        validate_demo_execution_config(config)
        self.config = config
        self.mt5 = mt5_module
        self.output_dir = Path(output_dir)

    @classmethod
    def from_config_file(
        cls,
        path: str | Path = DEFAULT_DEMO_EXECUTION_CONFIG_PATH,
        *,
        mt5_module: Any | None = None,
        output_dir: str | Path = DEFAULT_DEMO_EXECUTION_OUTPUT_DIR,
    ) -> "MT5DemoExecutor":
        """Build executor from config file."""
        return cls(load_demo_execution_config(path), mt5_module=mt5_module, output_dir=output_dir)

    def submit_demo_market_order(
        self,
        request: DemoOrderRequest,
        *,
        dry_run: bool = True,
        persist: bool = False,
    ) -> DemoExecutionResult:
        """Submit a gated demo market request or simulate it in dry-run mode."""
        local_error = self._validate_local_request(request)
        if local_error is not None:
            result = self._result(False, "REJECTED", local_error, request, dry_run)
            self._maybe_record(result, request, persist)
            return result

        if dry_run:
            result = self._result(True, "DRY_RUN", "Dry-run accepted locally; no MT5 request was submitted.", request, True)
            self._maybe_record(result, request, persist)
            return result

        gate_error = self._validate_execution_gates()
        if gate_error is not None:
            result = self._result(False, "REJECTED", gate_error, request, False)
            self._maybe_record(result, request, persist)
            return result

        mt5 = self.mt5 or import_mt5_module()
        if mt5 is None:
            result = self._result(False, "MT5_NOT_AVAILABLE", "Python MetaTrader5 package is not available.", request, False)
            self._maybe_record(result, request, persist)
            return result

        initialized = False
        try:
            initialized = bool(mt5.initialize()) if callable(getattr(mt5, "initialize", None)) else False
            if not initialized:
                result = self._result(False, "ERROR", f"MT5_NOT_INITIALIZED: {_last_error(mt5)}", request, False)
                self._maybe_record(result, request, persist)
                return result

            broker_error = self._validate_broker_state(mt5, request)
            if broker_error is not None:
                result = self._result(False, "REJECTED", broker_error, request, False)
                self._maybe_record(result, request, persist)
                return result

            mt5_request = self._build_mt5_request(mt5, request)
            mt5_submit = getattr(mt5, "order_send", None)
            if not callable(mt5_submit):
                result = self._result(False, "ERROR", "MT5 order submission function is unavailable.", request, False)
                self._maybe_record(result, request, persist)
                return result

            response = mt5_submit(mt5_request)
            if response is None:
                result = self._result(False, "ERROR", f"MT5 returned no response: {_last_error(mt5)}", request, False)
            else:
                retcode = _int_or_none(getattr(response, "retcode", None))
                success = retcode in _success_retcode_values(mt5)
                result = DemoExecutionResult(
                    accepted=success,
                    status="SENT" if success else "ERROR",
                    reason="Demo order accepted by MT5." if success else f"MT5 rejected demo order: {getattr(response, 'comment', '')}",
                    signal_id=request.signal_id,
                    dry_run=False,
                    mt5_retcode=retcode,
                    mt5_order=_int_or_none(getattr(response, "order", None)),
                    mt5_deal=_int_or_none(getattr(response, "deal", None)),
                )
            self._maybe_record(result, request, persist, mt5=mt5)
            return result
        finally:
            shutdown = getattr(mt5, "shutdown", None)
            if initialized and callable(shutdown):
                shutdown()

    def _validate_execution_gates(self) -> str | None:
        if self.config.allow_real_live:
            return "allow_real_live=true blocks demo execution."
        if not self.config.demo_only:
            return "demo_only=false blocks demo execution."
        if not self.config.allow_demo_execution:
            return "allow_demo_execution=false blocks demo execution."
        if not self.config.execution_enabled:
            return "execution_enabled=false blocks demo execution."
        return None

    def _validate_local_request(self, request: DemoOrderRequest) -> str | None:
        if request.side not in {"BUY", "SELL"}:
            return "side must be BUY or SELL"
        if not request.signal_id:
            return "signal_id is required"
        if self.config.require_sl and (request.stop_loss is None or request.stop_loss <= 0):
            return "stop loss is required"
        if self.config.require_tp and (request.take_profit is None or request.take_profit <= 0):
            return "take profit is required"
        if not _volume_matches_config(request.volume, self.config):
            return "volume violates min_lot, lot_step, or max_lot"
        if self._duplicate_in_local_log(request.signal_id):
            return f"duplicate signal_id already logged: {request.signal_id}"
        return None

    def _validate_broker_state(self, mt5: Any, request: DemoOrderRequest) -> str | None:
        account = mt5.account_info()
        terminal = mt5.terminal_info() if hasattr(mt5, "terminal_info") else None
        if account is None:
            return "MT5 account is not connected"
        if not _is_demo_account(mt5, account):
            return "MT5 account is not demo"
        if not bool(getattr(account, "trade_allowed", False)) or not bool(getattr(terminal, "trade_allowed", True)):
            return "MT5 demo trading is not allowed"

        symbol = mt5.symbol_info(self.config.symbol)
        if symbol is None:
            return f"symbol not found: {self.config.symbol}"
        if not bool(getattr(symbol, "visible", False)):
            return f"symbol is not visible: {self.config.symbol}"
        if not _volume_matches_symbol(request.volume, symbol):
            return "volume violates MT5 symbol min/step limits"
        tick = mt5.symbol_info_tick(self.config.symbol)
        spread = _spread_points(symbol, tick)
        if spread is not None and spread > self.config.max_spread_points:
            return f"spread {spread:.1f} points exceeds max {self.config.max_spread_points:.1f}"
        if request.expected_price is not None:
            slippage = _slippage_points(request.side, request.expected_price, symbol, tick)
            if slippage is not None and slippage > self.config.max_slippage_points:
                return f"slippage {slippage:.1f} points exceeds max {self.config.max_slippage_points:.1f}"
        if self._open_position_count(mt5) >= self.config.max_open_positions:
            return f"max_open_positions reached ({self.config.max_open_positions})"
        if self._trades_today_count() >= self.config.max_trades_per_day:
            return f"max_trades_per_day reached ({self.config.max_trades_per_day})"
        if self._duplicate_in_open_positions(mt5, request.signal_id):
            return f"duplicate signal_id already open: {request.signal_id}"
        return None

    def _build_mt5_request(self, mt5: Any, request: DemoOrderRequest) -> dict[str, Any]:
        symbol = mt5.symbol_info(self.config.symbol)
        tick = mt5.symbol_info_tick(self.config.symbol)
        price = float(getattr(tick, "ask" if request.side == "BUY" else "bid"))
        order_type = getattr(mt5, "ORDER_TYPE_BUY") if request.side == "BUY" else getattr(mt5, "ORDER_TYPE_SELL")
        filling_mode = getattr(symbol, "filling_mode", None)
        if filling_mode is None:
            filling_mode = getattr(mt5, "ORDER_FILLING_IOC", 1)
        return {
            "action": getattr(mt5, "TRADE_ACTION_DEAL"),
            "symbol": self.config.symbol,
            "volume": request.volume,
            "type": order_type,
            "price": price,
            "sl": float(request.stop_loss),
            "tp": float(request.take_profit),
            "deviation": int(self.config.max_slippage_points),
            "magic": int(self.config.magic_number),
            "comment": _demo_comment(request.signal_id, request.comment),
            "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
            "type_filling": filling_mode,
        }

    def _open_position_count(self, mt5: Any) -> int:
        positions = mt5.positions_get(symbol=self.config.symbol) if hasattr(mt5, "positions_get") else None
        if positions is None:
            positions = []
        return sum(1 for position in positions if _matches_magic(position, self.config.magic_number))

    def _duplicate_in_open_positions(self, mt5: Any, signal_id: str) -> bool:
        positions = mt5.positions_get(symbol=self.config.symbol) if hasattr(mt5, "positions_get") else None
        if positions is None:
            return False
        for position in positions:
            if _matches_magic(position, self.config.magic_number) and signal_id in str(getattr(position, "comment", "")):
                return True
        return False

    def _duplicate_in_local_log(self, signal_id: str) -> bool:
        path = self.output_dir / "demo_orders.csv"
        if not path.exists():
            return False
        try:
            orders = pd.read_csv(path)
        except Exception:
            return False
        if orders.empty or "signal_id" not in orders.columns:
            return False
        active_statuses = {"SENT", "ACCEPTED", "FILLED"}
        matches = orders[orders["signal_id"].astype(str) == str(signal_id)]
        if "status" in matches.columns:
            matches = matches[matches["status"].astype(str).isin(active_statuses)]
        return not matches.empty

    def _trades_today_count(self) -> int:
        path = self.output_dir / "demo_orders.csv"
        if not path.exists():
            return 0
        try:
            orders = pd.read_csv(path)
        except Exception:
            return 0
        if orders.empty or "timestamp" not in orders.columns:
            return 0
        timestamps = pd.to_datetime(orders["timestamp"], errors="coerce", utc=True)
        today = pd.Timestamp.now(tz=UTC).date()
        statuses = orders.get("status", pd.Series([""] * len(orders))).astype(str)
        return int(((timestamps.dt.date == today) & statuses.isin({"SENT", "ACCEPTED", "FILLED"})).sum())

    def _maybe_record(
        self,
        result: DemoExecutionResult,
        request: DemoOrderRequest,
        persist: bool,
        *,
        mt5: Any | None = None,
    ) -> None:
        if not persist:
            return
        paths = ensure_demo_execution_files(self.output_dir)
        now = pd.Timestamp.now(tz=UTC).isoformat()
        order_row = {
            "timestamp": now,
            "signal_id": request.signal_id,
            "symbol": self.config.symbol,
            "side": request.side,
            "volume": request.volume,
            "entry_price": request.expected_price,
            "stop_loss": request.stop_loss,
            "take_profit": request.take_profit,
            "status": result.status,
            "reason": result.reason,
            "mt5_retcode": result.mt5_retcode,
            "mt5_order": result.mt5_order,
            "mt5_deal": result.mt5_deal,
            "magic_number": self.config.magic_number,
            "dry_run": result.dry_run,
        }
        _append_csv(paths["orders"], order_row, DEMO_ORDER_COLUMNS)
        _append_csv(
            paths["log"],
            {
                "timestamp": now,
                "event": "demo_order_result",
                "status": result.status,
                "reason": result.reason,
                "signal_id": request.signal_id,
                "symbol": self.config.symbol,
                "side": request.side,
                "dry_run": result.dry_run,
            },
            DEMO_LOG_COLUMNS,
        )
        if mt5 is not None:
            record_demo_snapshots(mt5, self.config, self.output_dir)

    @staticmethod
    def _result(
        accepted: bool,
        status: str,
        reason: str,
        request: DemoOrderRequest,
        dry_run: bool,
    ) -> DemoExecutionResult:
        return DemoExecutionResult(
            accepted=accepted,
            status=status,
            reason=reason,
            signal_id=request.signal_id,
            dry_run=dry_run,
        )


def ensure_demo_execution_files(output_dir: str | Path = DEFAULT_DEMO_EXECUTION_OUTPUT_DIR) -> dict[str, Path]:
    """Create demo execution CSV files if needed."""
    paths = demo_execution_paths(output_dir)
    for key, columns in {
        "orders": DEMO_ORDER_COLUMNS,
        "positions": DEMO_POSITION_COLUMNS,
        "closed_trades": DEMO_CLOSED_TRADE_COLUMNS,
        "equity": DEMO_EQUITY_COLUMNS,
        "log": DEMO_LOG_COLUMNS,
    }.items():
        path = paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pd.DataFrame(columns=columns).to_csv(path, index=False)
    return paths


def demo_execution_paths(output_dir: str | Path = DEFAULT_DEMO_EXECUTION_OUTPUT_DIR) -> dict[str, Path]:
    """Return demo execution CSV paths."""
    directory = Path(output_dir)
    return {
        "orders": directory / "demo_orders.csv",
        "positions": directory / "demo_positions.csv",
        "closed_trades": directory / "demo_closed_trades.csv",
        "equity": directory / "demo_equity.csv",
        "log": directory / "demo_execution_log.csv",
    }


def record_demo_snapshots(mt5: Any, config: DemoExecutionConfig, output_dir: str | Path) -> None:
    """Record read-only positions and account equity after a demo execution attempt."""
    paths = ensure_demo_execution_files(output_dir)
    now = pd.Timestamp.now(tz=UTC).isoformat()
    account = mt5.account_info()
    if account is not None:
        _append_csv(
            paths["equity"],
            {
                "timestamp": now,
                "balance": getattr(account, "balance", None),
                "equity": getattr(account, "equity", None),
                "margin": getattr(account, "margin", None),
                "free_margin": getattr(account, "margin_free", None),
                "currency": getattr(account, "currency", None),
            },
            DEMO_EQUITY_COLUMNS,
        )
    positions = mt5.positions_get(symbol=config.symbol) if hasattr(mt5, "positions_get") else None
    if positions is None:
        positions = []
    rows = []
    for position in positions:
        rows.append(
            {
                "timestamp": now,
                "ticket": getattr(position, "ticket", None),
                "symbol": getattr(position, "symbol", config.symbol),
                "side": _position_side(mt5, position),
                "volume": getattr(position, "volume", None),
                "price_open": getattr(position, "price_open", None),
                "price_current": getattr(position, "price_current", None),
                "profit": getattr(position, "profit", None),
                "magic_number": getattr(position, "magic", None),
                "comment": getattr(position, "comment", ""),
            }
        )
    pd.DataFrame(rows, columns=DEMO_POSITION_COLUMNS).to_csv(paths["positions"], index=False)


def _readiness_error(reason: str) -> DemoExecutionReadiness:
    return DemoExecutionReadiness(
        status="ERROR" if not reason.startswith("MT5_NOT_AVAILABLE") else "MT5_NOT_AVAILABLE",
        reason=reason,
        mt5_initialized=False,
        account_connected=False,
        account_demo=False,
        trade_allowed=False,
        symbol_found=False,
        symbol_visible=False,
        volume_min=None,
        volume_step=None,
        stops_level=None,
        filling_mode=None,
        spread_current=None,
    )


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
    spreads = [value for value in [symbol_spread, tick_spread] if value is not None]
    return max(spreads) if spreads else None


def _slippage_points(side: str, expected_price: float, symbol: Any, tick: Any) -> float | None:
    point = _float_or_none(getattr(symbol, "point", None)) or 0.0
    if tick is None or point <= 0:
        return None
    current = _float_or_none(getattr(tick, "ask" if side == "BUY" else "bid", None))
    if current is None:
        return None
    return abs(current - expected_price) / point


def _volume_matches_config(volume: float, config: DemoExecutionConfig) -> bool:
    if volume < config.min_lot or volume > config.max_lot:
        return False
    return _matches_step(volume, config.min_lot, config.lot_step)


def _volume_matches_symbol(volume: float, symbol: Any) -> bool:
    minimum = _float_or_none(getattr(symbol, "volume_min", None))
    step = _float_or_none(getattr(symbol, "volume_step", None))
    maximum = _float_or_none(getattr(symbol, "volume_max", None))
    if minimum is not None and volume < minimum:
        return False
    if maximum is not None and volume > maximum:
        return False
    if minimum is not None and step is not None and not _matches_step(volume, minimum, step):
        return False
    return True


def _matches_step(value: float, minimum: float, step: float) -> bool:
    units = round((value - minimum) / step)
    return abs(value - (minimum + units * step)) < 1e-9


def _matches_magic(position: Any, magic_number: int) -> bool:
    return int(getattr(position, "magic", -1) or -1) == int(magic_number)


def _demo_comment(signal_id: str, comment: str) -> str:
    suffix = f":{comment}" if comment else ""
    return f"demo:{signal_id}{suffix}"[:31]


def _success_retcode_values(mt5: Any) -> set[int]:
    values = {
        _int_or_none(getattr(mt5, "TRADE_RETCODE_DONE", None)),
        _int_or_none(getattr(mt5, "TRADE_RETCODE_PLACED", None)),
    }
    return {value for value in values if value is not None}


def _position_side(mt5: Any, position: Any) -> str:
    position_type = getattr(position, "type", None)
    if position_type == getattr(mt5, "POSITION_TYPE_BUY", 0):
        return "BUY"
    if position_type == getattr(mt5, "POSITION_TYPE_SELL", 1):
        return "SELL"
    return str(position_type)


def _append_csv(path: Path, row: dict, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([row], columns=columns)
    header = not path.exists() or path.stat().st_size == 0
    frame.to_csv(path, mode="a", header=header, index=False)


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
