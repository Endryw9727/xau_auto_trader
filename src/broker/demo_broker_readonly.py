"""Safe demo broker read-only snapshots.

This module prepares a future MetaTrader/Axi demo read-only boundary. It never
opens positions and intentionally exposes no order-sending methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from src.broker.demo_broker_guardrails import (
    assert_allow_live_false,
    assert_demo_only,
    assert_execution_disabled,
    assert_no_real_order_method_available,
)


DEFAULT_DEMO_BROKER_CONFIG_PATH = Path("config/demo_broker.yaml")
MT5_MOCK_STATUS = "MT5_NOT_CONNECTED_MOCK_ONLY"


@dataclass(frozen=True)
class DemoBrokerConfig:
    """Static safety config for demo broker read-only checks."""

    demo_only: bool
    allow_live: bool
    execution_enabled: bool
    broker_name: str
    platform: str
    symbol: str
    max_lot: float
    max_trades_per_day: int
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    kill_switch: bool


@dataclass(frozen=True)
class DemoBrokerSnapshot:
    """Read-only account-level snapshot."""

    broker_name: str
    platform: str
    mode: str
    connected: bool
    status: str
    balance: float | None
    equity: float | None
    margin: float | None
    free_margin: float | None
    currency: str | None
    positions_count: int
    orders_history_count: int
    message: str
    captured_at: datetime


@dataclass(frozen=True)
class DemoSymbolSnapshot:
    """Read-only symbol quote/symbol metadata snapshot."""

    symbol: str
    bid: float | None
    ask: float | None
    spread: float | None
    point: float | None
    digits: int | None
    trade_mode: str
    visible: bool
    has_real_quote: bool
    status: str
    message: str
    captured_at: datetime


@dataclass(frozen=True)
class DemoPositionSnapshot:
    """Read-only open position snapshot."""

    ticket: str
    symbol: str
    side: str
    volume: float
    price_open: float
    current_price: float | None
    profit: float | None
    opened_at: datetime | None


class DemoBrokerReadOnlyClient:
    """Read account, symbol, and position-like state without execution."""

    def __init__(self, config: DemoBrokerConfig | dict[str, Any], mode: str = "mock") -> None:
        self.config = _coerce_config(config)
        assert_demo_only(self.config)
        assert_allow_live_false(self.config)
        assert_execution_disabled(self.config)

        self.mode = mode.strip().lower()
        if self.mode not in {"mock", "mt5"}:
            raise ValueError(f"Unsupported demo broker read-only mode: {mode}")
        assert_no_real_order_method_available(self)

    @classmethod
    def from_config_file(
        cls,
        path: str | Path = DEFAULT_DEMO_BROKER_CONFIG_PATH,
        mode: str | None = None,
    ) -> "DemoBrokerReadOnlyClient":
        """Build a read-only client from YAML config."""
        config = load_demo_broker_config(path)
        return cls(config=config, mode=mode or "mock")

    def account_snapshot(self) -> DemoBrokerSnapshot:
        """Return account state, using a safe mock placeholder when MT5 is absent."""
        return DemoBrokerSnapshot(
            broker_name=self.config.broker_name,
            platform=self.config.platform,
            mode=self.mode,
            connected=False,
            status=MT5_MOCK_STATUS,
            balance=None,
            equity=None,
            margin=None,
            free_margin=None,
            currency=None,
            positions_count=0,
            orders_history_count=0,
            message="MT5 is not connected in this research build; using read-only mock snapshot.",
            captured_at=datetime.now(tz=UTC),
        )

    def symbol_snapshot(self) -> DemoSymbolSnapshot:
        """Return symbol quote state, using a safe mock placeholder when MT5 is absent."""
        return DemoSymbolSnapshot(
            symbol=self.config.symbol,
            bid=None,
            ask=None,
            spread=None,
            point=None,
            digits=None,
            trade_mode="READ_ONLY",
            visible=False,
            has_real_quote=False,
            status=MT5_MOCK_STATUS,
            message="No live/demo quote connection is configured; quote values are unavailable.",
            captured_at=datetime.now(tz=UTC),
        )

    def open_positions(self) -> list[DemoPositionSnapshot]:
        """Return open demo positions if available; mock mode returns no positions."""
        return []

    def order_history(self) -> list[dict[str, Any]]:
        """Return read-only historical order-like rows if available."""
        return []


def load_demo_broker_config(path: str | Path = DEFAULT_DEMO_BROKER_CONFIG_PATH) -> DemoBrokerConfig:
    """Load and validate demo broker YAML config."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid demo broker config: {config_path}")

    config = _coerce_config(raw)
    assert_demo_only(config)
    assert_allow_live_false(config)
    assert_execution_disabled(config)
    return config


def _coerce_config(config: DemoBrokerConfig | dict[str, Any]) -> DemoBrokerConfig:
    """Convert a mapping into a typed demo broker config."""
    if isinstance(config, DemoBrokerConfig):
        return config

    return DemoBrokerConfig(
        demo_only=bool(config.get("demo_only", False)),
        allow_live=bool(config.get("allow_live", True)),
        execution_enabled=bool(config.get("execution_enabled", True)),
        broker_name=str(config.get("broker_name", "axi_demo")),
        platform=str(config.get("platform", "mt5")),
        symbol=str(config.get("symbol", "XAUUSD")),
        max_lot=float(config.get("max_lot", 0.01)),
        max_trades_per_day=int(config.get("max_trades_per_day", 2)),
        max_daily_loss_pct=float(config.get("max_daily_loss_pct", 3)),
        max_weekly_loss_pct=float(config.get("max_weekly_loss_pct", 8)),
        kill_switch=bool(config.get("kill_switch", True)),
    )
