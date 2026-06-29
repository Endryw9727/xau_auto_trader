"""
Join V51 candidates with per-day market structure (read-only).

This module annotates the V51 decision log with the Asia/London/New York market
structure computed in ``session_structure``: was Asia liquidity swept, on which
side, was it reclaimed, which way New York went, and how far the candidate entry
sits from the nearest key level. It then summarizes how V51 candidates (accepted
and rejected) distribute across those structure contexts.

It is diagnostics only. It reads the decision log and OHLCV candles, never sends
orders, never imports execution code and never changes strategy gates.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_structure import build_daily_structure, distance_from_levels


STRUCTURE_CONTEXT_COLUMNS: tuple[str, ...] = (
    "signal_id",
    "candle_time",
    "day",
    "session",
    "side",
    "decision",
    "score",
    "entry_price",
    "sweep_side",
    "reclaimed_range",
    "manipulation_label",
    "ny_direction",
    "in_asia_range",
    "nearest_level_name",
    "nearest_level_price",
    "distance_to_level",
    "structure_alignment",
)

STRUCTURE_SUMMARY_COLUMNS: tuple[str, ...] = (
    "manipulation_label",
    "structure_alignment",
    "candidates",
    "accepted",
    "rejected",
    "buy",
    "sell",
)


def annotate_candidates_with_structure(
    decision_log: pd.DataFrame,
    market_data: pd.DataFrame,
) -> pd.DataFrame:
    """Return V51 candidate rows enriched with market-structure context."""
    if decision_log is None or decision_log.empty or "side" not in decision_log.columns:
        return pd.DataFrame(columns=STRUCTURE_CONTEXT_COLUMNS)

    candidates = decision_log[decision_log["side"].astype(str).isin(["BUY", "SELL"])].copy()
    if candidates.empty:
        return pd.DataFrame(columns=STRUCTURE_CONTEXT_COLUMNS)

    structure = build_daily_structure(market_data)
    structure_by_day = {pd.Timestamp(row["day"]): row for _, row in structure.iterrows()}

    candidate_times = pd.to_datetime(candidates["candle_time"], errors="coerce")
    rows = []
    for (_, candidate), candle_time in zip(candidates.iterrows(), candidate_times):
        day = candle_time.normalize() if pd.notna(candle_time) else None
        structure_row = structure_by_day.get(day)
        rows.append(_annotate_row(candidate, candle_time, day, structure_row))
    return pd.DataFrame(rows, columns=STRUCTURE_CONTEXT_COLUMNS)


def build_structure_context_summary(annotated: pd.DataFrame) -> pd.DataFrame:
    """Summarize candidate counts by manipulation label and alignment."""
    if annotated is None or annotated.empty:
        return pd.DataFrame(columns=STRUCTURE_SUMMARY_COLUMNS)

    decisions = annotated.get("decision", pd.Series("", index=annotated.index)).astype(str).str.upper()
    sides = annotated.get("side", pd.Series("", index=annotated.index)).astype(str)
    work = annotated.copy()
    work["_accepted"] = (decisions == "ACCEPTED").to_numpy()
    work["_buy"] = (sides == "BUY").to_numpy()
    work["_sell"] = (sides == "SELL").to_numpy()

    rows = []
    grouped = work.groupby(["manipulation_label", "structure_alignment"], dropna=False)
    for (label, alignment), group in grouped:
        accepted = int(group["_accepted"].sum())
        rows.append(
            {
                "manipulation_label": label,
                "structure_alignment": alignment,
                "candidates": int(len(group)),
                "accepted": accepted,
                "rejected": int(len(group) - accepted),
                "buy": int(group["_buy"].sum()),
                "sell": int(group["_sell"].sum()),
            }
        )
    summary = pd.DataFrame(rows, columns=STRUCTURE_SUMMARY_COLUMNS)
    return summary.sort_values("candidates", ascending=False).reset_index(drop=True)


def _annotate_row(candidate: pd.Series, candle_time: pd.Timestamp, day, structure_row) -> dict:
    side = str(candidate.get("side", ""))
    entry_price = _float_or_none(candidate.get("entry_price"))
    base = {
        "signal_id": candidate.get("signal_id"),
        "candle_time": candidate.get("candle_time"),
        "day": pd.Timestamp(day) if day is not None else None,
        "session": candidate.get("session"),
        "side": side,
        "decision": candidate.get("decision"),
        "score": candidate.get("score"),
        "entry_price": entry_price,
        "sweep_side": "UNKNOWN",
        "reclaimed_range": None,
        "manipulation_label": "unknown",
        "ny_direction": "UNKNOWN",
        "in_asia_range": None,
        "nearest_level_name": "none",
        "nearest_level_price": None,
        "distance_to_level": None,
        "structure_alignment": "unknown",
    }
    if structure_row is None:
        return base

    manipulation = str(structure_row.get("manipulation_label", "unknown"))
    base.update(
        {
            "sweep_side": structure_row.get("sweep_side", "UNKNOWN"),
            "reclaimed_range": bool(structure_row.get("reclaimed_range", False)),
            "manipulation_label": manipulation,
            "ny_direction": structure_row.get("ny_direction", "UNKNOWN"),
            "structure_alignment": _alignment(side, manipulation),
        }
    )
    if entry_price is not None:
        distance = distance_from_levels(entry_price, structure_row)
        base.update(
            {
                "in_asia_range": distance.in_asia_range,
                "nearest_level_name": distance.nearest_level_name,
                "nearest_level_price": distance.nearest_level_price,
                "distance_to_level": distance.distance,
            }
        )
    return base


def _alignment(side: str, manipulation_label: str) -> str:
    """Is the candidate direction aligned with the manipulation (V-formation logic)?

    A sell-side sweep that is reclaimed is a bullish context (favours BUY); a
    buy-side sweep that is reclaimed is a bearish context (favours SELL).
    """
    if manipulation_label == "london_sweep_low_reclaimed":
        return "aligned" if side == "BUY" else "counter"
    if manipulation_label == "london_sweep_high_reclaimed":
        return "aligned" if side == "SELL" else "counter"
    if manipulation_label in {"no_sweep", "unknown"}:
        return "neutral"
    return "neutral"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
