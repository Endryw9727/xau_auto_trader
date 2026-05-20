"""Shadow strategy diagnostics for Control Room."""

from __future__ import annotations

from typing import Any

import pandas as pd


SHADOW_COLUMNS = [
    "variant",
    "potential_signals",
    "NO_TRADE",
    "PAPER_BUY",
    "PAPER_SELL",
    "PAUSE",
    "top_rejection_reasons",
    "near_miss",
]


def collect_shadow_snapshot(config: Any, *, signal_snapshot: dict) -> dict:
    """Build read-only shadow diagnostics from available signal audit data."""
    signals = signal_snapshot.get("signals")
    if not isinstance(signals, pd.DataFrame):
        signals = pd.DataFrame()

    rows = []
    for variant in config.shadow_variants:
        subset = _variant_subset(signals, variant)
        decisions = subset.get("decision", pd.Series(dtype=str)).fillna("NO_TRADE").astype(str)
        rows.append(
            {
                "variant": variant,
                "potential_signals": int(len(subset)),
                "NO_TRADE": int((decisions == "NO_TRADE").sum()),
                "PAPER_BUY": int((decisions == "PAPER_BUY").sum()),
                "PAPER_SELL": int((decisions == "PAPER_SELL").sum()),
                "PAUSE": int((decisions == "PAUSE").sum()),
                "top_rejection_reasons": _top_reasons(subset),
                "near_miss": _near_miss(subset),
            }
        )

    frame = pd.DataFrame(rows, columns=SHADOW_COLUMNS)
    return {
        "status": "OK" if not frame.empty else "WARNING",
        "reason": "shadow diagnostics generated" if not frame.empty else "no shadow variants configured",
        "snapshot": frame,
    }


def _variant_subset(signals: pd.DataFrame, variant: str) -> pd.DataFrame:
    if signals.empty or "strategy_name" not in signals.columns:
        return pd.DataFrame(columns=signals.columns)
    return signals[signals["strategy_name"].astype(str) == str(variant)].copy()


def _top_reasons(signals: pd.DataFrame) -> str:
    if signals.empty or "reason" not in signals.columns:
        return "no matching signals"
    reasons = signals["reason"].fillna("unknown").astype(str)
    if reasons.empty:
        return "no matching signals"
    return "; ".join(f"{reason} ({count})" for reason, count in reasons.value_counts().head(3).items())


def _near_miss(signals: pd.DataFrame) -> str:
    if signals.empty:
        return "n/a"
    if "score_gap" in signals.columns:
        score_gap = pd.to_numeric(signals["score_gap"], errors="coerce")
        near = signals[(score_gap >= 0) & (score_gap < 5)]
        return f"{len(near)} score_gap<5" if not near.empty else "none"
    return "not available"
