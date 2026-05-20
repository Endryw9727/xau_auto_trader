"""Signal monitor for Control Room."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_FORWARD_SIGNALS_PATH = Path("reports/paper_forward/paper_forward_signals.csv")


def collect_signal_snapshot(config: Any, signals_path: str | Path = DEFAULT_FORWARD_SIGNALS_PATH) -> dict:
    """Summarize latest paper-forward signals from CSV."""
    path = Path(signals_path)
    if not path.exists():
        return {
            "status": "WARNING",
            "reason": "paper-forward signals CSV not found",
            "total_signals": 0,
            "decision_counts": {},
            "latest_signal": {},
            "signals": pd.DataFrame(),
        }
    try:
        signals = pd.read_csv(path)
    except Exception as exc:
        return {
            "status": "WARNING",
            "reason": f"could not read paper-forward signals: {exc}",
            "total_signals": 0,
            "decision_counts": {},
            "latest_signal": {},
            "signals": pd.DataFrame(),
        }
    if signals.empty:
        return {
            "status": "WARNING",
            "reason": "paper-forward signals CSV is empty",
            "total_signals": 0,
            "decision_counts": {},
            "latest_signal": {},
            "signals": signals,
        }
    latest = signals.iloc[-1].to_dict()
    decision_counts = signals.get("decision", pd.Series(dtype=str)).fillna("UNKNOWN").astype(str).value_counts().to_dict()
    return {
        "status": "OK",
        "reason": "paper-forward signals loaded",
        "total_signals": int(len(signals)),
        "decision_counts": decision_counts,
        "latest_signal": latest,
        "signals": signals,
    }
