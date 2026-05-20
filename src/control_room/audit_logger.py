"""CSV audit logger for Control Room outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


STATUS_COLUMNS = [
    "timestamp",
    "symbol",
    "mode",
    "status",
    "reason",
    "market_status",
    "account_status",
    "risk_status",
    "signal_status",
    "shadow_status",
    "telegram_status",
    "allow_real_live",
]
EVENT_COLUMNS = ["timestamp", "component", "status", "reason", "details"]
WARNING_COLUMNS = ["timestamp", "component", "status", "reason"]


def write_control_room_outputs(config: Any, snapshots: dict, *, status: str, reason: str, output_dir: str | Path) -> dict[str, Path]:
    """Write Control Room status, events, warnings, and shadow snapshot CSVs."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = pd.Timestamp.now(tz="UTC").isoformat()
    paths = {
        "status": directory / "control_room_status.csv",
        "events": directory / "control_room_events.csv",
        "warnings": directory / "control_room_warnings.csv",
        "shadow": directory / "shadow_strategy_snapshot.csv",
    }

    status_row = {
        "timestamp": timestamp,
        "symbol": config.symbol,
        "mode": config.mode,
        "status": status,
        "reason": reason,
        "market_status": snapshots["market"].get("status"),
        "account_status": snapshots["account"].get("status"),
        "risk_status": snapshots["risk"].get("status"),
        "signal_status": snapshots["signals"].get("status"),
        "shadow_status": snapshots["shadow"].get("status"),
        "telegram_status": snapshots["telegram"].get("status"),
        "allow_real_live": config.allow_real_live,
    }
    _append(paths["status"], status_row, STATUS_COLUMNS)

    event_rows = []
    warning_rows = []
    for component, snapshot in snapshots.items():
        details = _details_without_frames(snapshot)
        event_rows.append(
            {
                "timestamp": timestamp,
                "component": component,
                "status": snapshot.get("status", "OK"),
                "reason": snapshot.get("reason", ""),
                "details": details,
            }
        )
        if snapshot.get("status") not in {"OK", None}:
            warning_rows.append(
                {
                    "timestamp": timestamp,
                    "component": component,
                    "status": snapshot.get("status", "WARNING"),
                    "reason": snapshot.get("reason", ""),
                }
            )

    _append_many(paths["events"], event_rows, EVENT_COLUMNS)
    _append_many(paths["warnings"], warning_rows, WARNING_COLUMNS)

    shadow_frame = snapshots["shadow"].get("snapshot")
    if isinstance(shadow_frame, pd.DataFrame):
        shadow_frame.to_csv(paths["shadow"], index=False)
    else:
        pd.DataFrame().to_csv(paths["shadow"], index=False)

    return paths


def _append(path: Path, row: dict, columns: list[str]) -> None:
    _append_many(path, [row], columns)


def _append_many(path: Path, rows: list[dict], columns: list[str]) -> None:
    frame = pd.DataFrame(rows, columns=columns)
    header = not path.exists() or path.stat().st_size == 0
    frame.to_csv(path, mode="a", header=header, index=False)


def _details_without_frames(snapshot: dict) -> str:
    safe = {key: value for key, value in snapshot.items() if not isinstance(value, pd.DataFrame)}
    return str(safe)
