"""Control Room orchestrator for read-only demo/paper monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.control_room.account_monitor import collect_account_snapshot
from src.control_room.audit_logger import write_control_room_outputs
from src.control_room.market_monitor import collect_market_snapshot
from src.control_room.risk_monitor import collect_risk_snapshot
from src.control_room.shadow_monitor import collect_shadow_snapshot
from src.control_room.signal_monitor import collect_signal_snapshot
from src.control_room.telegram_reporter import build_telegram_report, maybe_emit_telegram_report


DEFAULT_CONTROL_ROOM_CONFIG_PATH = Path("config/control_room.yaml")
DEFAULT_CONTROL_ROOM_OUTPUT_DIR = Path("reports/control_room")


@dataclass(frozen=True)
class ControlRoomConfig:
    """Control Room static settings."""

    enabled: bool
    symbol: str
    mode: str
    allow_real_live: bool
    allow_demo_execution: bool
    telegram_enabled: bool
    max_daily_loss_pct: float
    max_open_positions: int
    max_spread_points: float
    report_interval_minutes: int
    shadow_variants: tuple[str, ...]


@dataclass(frozen=True)
class ControlRoomResult:
    """Result for one Control Room cycle."""

    status: str
    reason: str
    snapshots: dict[str, dict[str, Any]]
    output_paths: dict[str, Path]


def load_control_room_config(path: str | Path = DEFAULT_CONTROL_ROOM_CONFIG_PATH) -> ControlRoomConfig:
    """Load and validate Control Room config."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid control room config: {config_path}")

    config = ControlRoomConfig(
        enabled=_as_bool(raw.get("enabled", True)),
        symbol=str(raw.get("symbol", "XAUUSD-P")),
        mode=str(raw.get("mode", "demo_monitor")),
        allow_real_live=_as_bool(raw.get("allow_real_live", False)),
        allow_demo_execution=_as_bool(raw.get("allow_demo_execution", False)),
        telegram_enabled=_as_bool(raw.get("telegram_enabled", False)),
        max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 3.0)),
        max_open_positions=int(raw.get("max_open_positions", 1)),
        max_spread_points=float(raw.get("max_spread_points", 80)),
        report_interval_minutes=int(raw.get("report_interval_minutes", 15)),
        shadow_variants=tuple(str(item) for item in raw.get("shadow_variants", [])),
    )
    validate_control_room_config(config)
    return config


def validate_control_room_config(config: ControlRoomConfig) -> None:
    """Validate safety invariants."""
    if config.allow_real_live:
        raise PermissionError("Control Room requires allow_real_live=false.")
    if config.mode not in {"demo_monitor", "paper_monitor", "research_monitor"}:
        raise ValueError("Control Room mode must be demo_monitor, paper_monitor, or research_monitor.")
    if config.max_daily_loss_pct <= 0:
        raise ValueError("max_daily_loss_pct must be positive.")
    if config.max_open_positions < 0:
        raise ValueError("max_open_positions cannot be negative.")
    if config.max_spread_points <= 0:
        raise ValueError("max_spread_points must be positive.")
    if config.report_interval_minutes <= 0:
        raise ValueError("report_interval_minutes must be positive.")


def run_control_room_once(
    *,
    config_path: str | Path = DEFAULT_CONTROL_ROOM_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_CONTROL_ROOM_OUTPUT_DIR,
) -> ControlRoomResult:
    """Run one read-only Control Room cycle and write audit CSV outputs."""
    config = load_control_room_config(config_path)

    market = collect_market_snapshot(config)
    account = collect_account_snapshot(config)
    risk = collect_risk_snapshot(config, account_snapshot=account, market_snapshot=market)
    signals = collect_signal_snapshot(config)
    shadow = collect_shadow_snapshot(config, signal_snapshot=signals)
    telegram_report = build_telegram_report(config, market, account, risk, signals, shadow)
    telegram = maybe_emit_telegram_report(config, telegram_report)

    snapshots = {
        "market": market,
        "account": account,
        "risk": risk,
        "signals": signals,
        "shadow": shadow,
        "telegram": telegram,
    }
    status, reason = _overall_status(config, snapshots)
    output_paths = write_control_room_outputs(config, snapshots, status=status, reason=reason, output_dir=output_dir)
    return ControlRoomResult(status=status, reason=reason, snapshots=snapshots, output_paths=output_paths)


def run_control_room_cycle(
    *,
    config_path: str | Path = DEFAULT_CONTROL_ROOM_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_CONTROL_ROOM_OUTPUT_DIR,
) -> ControlRoomResult:
    """Alias for a full read-only Control Room cycle."""
    return run_control_room_once(config_path=config_path, output_dir=output_dir)


def _overall_status(config: ControlRoomConfig, snapshots: dict[str, dict[str, Any]]) -> tuple[str, str]:
    if not config.enabled:
        return "WARNING", "control room disabled"
    statuses = {name: str(snapshot.get("status", "OK")) for name, snapshot in snapshots.items()}
    stop_reasons = [f"{name}: {snapshot.get('reason', '')}" for name, snapshot in snapshots.items() if snapshot.get("status") == "STOP"]
    if stop_reasons:
        return "STOP", "; ".join(stop_reasons)
    warning_reasons = [
        f"{name}: {snapshot.get('reason', '')}"
        for name, snapshot in snapshots.items()
        if snapshot.get("status") in {"WARNING", "STALE", "ERROR", "MT5_NOT_AVAILABLE"}
    ]
    if warning_reasons:
        return "WARNING", "; ".join(warning_reasons)
    return "OK", f"all monitors OK: {statuses}"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
