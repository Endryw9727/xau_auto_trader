"""
Read-only taxonomy for V51 rejection reasons.

This module classifies the free-text ``reason`` strings produced by the V51
demo intraday decision log (and by the V51 demo execution log) into a small set
of stable categories, so rejections can be aggregated and reviewed.

It is diagnostics only: it never imports execution code, never sends orders and
never changes strategy gates or thresholds. It only reads decision/log data that
already exists.
"""

from __future__ import annotations

import re

import pandas as pd


# Stable category identifiers. Order is also the tie-break priority used when a
# reason could match more than one pattern (more specific patterns come first).
REJECTION_CATEGORY_ORDER: tuple[str, ...] = (
    "accepted",
    "score_gap_low",
    "score_low",
    "trend_weak",
    "setup_unconfirmed",
    "quality_guard",
    "rr_low",
    "spread_slippage",
    "session_blocked",
    "daily_limit",
    "mtf_misaligned",
    "liquidity_sweep",
    "distance_from_level",
    "freshness_time",
    "duplicate",
    "no_directional_score",
    "other",
)

# How each category should be read operationally:
# - safety_critical: protects capital/execution; do NOT relax without review.
# - review_candidate: may produce false negatives; worth statistical review.
# - threshold: a tunable score/strength threshold.
# - informational: not a blocking rejection.
CATEGORY_DISPOSITION: dict[str, str] = {
    "accepted": "informational",
    "no_directional_score": "informational",
    "other": "informational",
    "score_low": "threshold",
    "score_gap_low": "threshold",
    "trend_weak": "threshold",
    "setup_unconfirmed": "review_candidate",
    "quality_guard": "review_candidate",
    "mtf_misaligned": "review_candidate",
    "liquidity_sweep": "review_candidate",
    "distance_from_level": "review_candidate",
    "rr_low": "safety_critical",
    "spread_slippage": "safety_critical",
    "session_blocked": "safety_critical",
    "daily_limit": "safety_critical",
    "freshness_time": "safety_critical",
    "duplicate": "safety_critical",
}

# Ordered (category, compiled pattern) pairs. The first match wins, so more
# specific patterns (e.g. "score gap") must precede broader ones ("score").
_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("accepted", re.compile(r"signal accepted|dry-run accepted|accepted by mt5", re.I)),
    ("score_gap_low", re.compile(r"score\s*gap", re.I)),
    ("score_low", re.compile(r"\bscore\b.*\bbelow\b", re.I)),
    ("trend_weak", re.compile(r"\badx\b", re.I)),
    ("setup_unconfirmed", re.compile(r"setup not confirmed", re.I)),
    ("quality_guard", re.compile(r"quality guard", re.I)),
    ("rr_low", re.compile(r"\brr\b.*\bbelow\b|risk[_ ]?reward.*below", re.I)),
    ("spread_slippage", re.compile(r"spread|slippage", re.I)),
    ("session_blocked", re.compile(r"session blocked", re.I)),
    (
        "daily_limit",
        re.compile(r"max trades per day|max open positions|existing open .*position", re.I),
    ),
    ("mtf_misaligned", re.compile(r"mtf", re.I)),
    ("liquidity_sweep", re.compile(r"liquidity|sweep", re.I)),
    (
        "distance_from_level",
        re.compile(r"distance|support|resistance|\blevel\b|reachab", re.I),
    ),
    (
        "freshness_time",
        re.compile(
            r"stale|candidate_time_in_future|cooldown|no fresh live candidate|"
            r"no closed candles|no mt5 closed rates|data unavailable|data_stale|"
            r"not initialized|not available|not connected|future",
            re.I,
        ),
    ),
    ("duplicate", re.compile(r"duplicate", re.I)),
    ("no_directional_score", re.compile(r"no directional score|no setup", re.I)),
)

TAXONOMY_SUMMARY_COLUMNS: tuple[str, ...] = (
    "rejection_category",
    "disposition",
    "count",
    "share_pct",
    "buy_count",
    "sell_count",
    "top_sessions",
    "example_reason",
)


def categorize_rejection_reason(reason: object) -> str:
    """Map a free-text reason string to a stable rejection category."""
    if reason is None:
        return "other"
    text = str(reason).strip()
    if not text or text.lower() == "nan":
        return "other"
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(text):
            return category
    return "other"


def rejection_disposition(category: str) -> str:
    """Return the operational disposition for a rejection category."""
    return CATEGORY_DISPOSITION.get(category, "informational")


def classify_decision_log(decision_log: pd.DataFrame) -> pd.DataFrame:
    """Return candidate rows with ``rejection_category`` and ``disposition``.

    Only BUY/SELL rows are kept (NO_TRADE rows without a direction are not
    candidates). ACCEPTED rows are tagged with the ``accepted`` category so the
    distribution covers the full candidate population.
    """
    if decision_log is None or decision_log.empty or "side" not in decision_log.columns:
        return _empty_classified_frame()

    candidates = decision_log[decision_log["side"].astype(str).isin(["BUY", "SELL"])].copy()
    if candidates.empty:
        return _empty_classified_frame()

    decisions = candidates.get("decision", pd.Series("", index=candidates.index)).astype(str)
    reasons = candidates.get("reason", pd.Series("", index=candidates.index))
    categories = []
    for decision, reason in zip(decisions, reasons):
        if decision.upper() == "ACCEPTED":
            categories.append("accepted")
        else:
            categories.append(categorize_rejection_reason(reason))
    candidates["rejection_category"] = categories
    candidates["disposition"] = [rejection_disposition(category) for category in categories]
    return candidates.reset_index(drop=True)


def build_rejection_taxonomy(decision_log: pd.DataFrame) -> pd.DataFrame:
    """Build a per-category taxonomy summary from a V51 decision log."""
    classified = classify_decision_log(decision_log)
    if classified.empty:
        return pd.DataFrame(columns=TAXONOMY_SUMMARY_COLUMNS)

    total = int(len(classified))
    rows = []
    for category in REJECTION_CATEGORY_ORDER:
        subset = classified[classified["rejection_category"] == category]
        if subset.empty:
            continue
        sides = subset.get("side", pd.Series(dtype=str)).astype(str)
        rows.append(
            {
                "rejection_category": category,
                "disposition": rejection_disposition(category),
                "count": int(len(subset)),
                "share_pct": round(100.0 * len(subset) / total, 2),
                "buy_count": int((sides == "BUY").sum()),
                "sell_count": int((sides == "SELL").sum()),
                "top_sessions": _top_sessions(subset),
                "example_reason": _example_reason(subset),
            }
        )
    summary = pd.DataFrame(rows, columns=TAXONOMY_SUMMARY_COLUMNS)
    return summary.sort_values("count", ascending=False).reset_index(drop=True)


def top_blocking_category(taxonomy_summary: pd.DataFrame) -> str:
    """Return the most frequent non-accepted blocking category, or ''."""
    if taxonomy_summary is None or taxonomy_summary.empty:
        return ""
    blocking = taxonomy_summary[taxonomy_summary["rejection_category"] != "accepted"]
    if blocking.empty:
        return ""
    return str(blocking.iloc[0]["rejection_category"])


def _top_sessions(subset: pd.DataFrame, *, limit: int = 3) -> str:
    if "session" not in subset.columns:
        return ""
    sessions = subset["session"].astype(str).replace({"": pd.NA, "nan": pd.NA}).dropna()
    if sessions.empty:
        return ""
    counts = sessions.value_counts().head(limit)
    return "; ".join(f"{session} ({count})" for session, count in counts.items())


def _example_reason(subset: pd.DataFrame) -> str:
    if "reason" not in subset.columns:
        return ""
    reasons = subset["reason"].astype(str).replace({"": pd.NA, "nan": pd.NA}).dropna()
    return reasons.iloc[0] if not reasons.empty else ""


def _empty_classified_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["side", "decision", "reason", "rejection_category", "disposition"])
