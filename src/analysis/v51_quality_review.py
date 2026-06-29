"""
Quality review of V51 candidates (read-only research, Phase 2).

Building on the theoretical outcome simulation (``v51_outcome_simulation``) and
the rejection taxonomy (``v51_rejection_taxonomy``), this module answers three
Phase-2 questions:

1. RR quality: do higher risk/reward candidates actually perform better?
2. Quality-guard false negatives: how many candidates blocked by the quality
   guard (or "setup not confirmed") would, in theory, have been winners?
3. Rejection review: which rejection categories would have been profitable if
   they had not been blocked, and are therefore worth a human review?

It is research only. It consumes a simulated-outcomes table (which already
carries ``decision``/``reason``) and never sends orders, never imports execution
code and never changes strategy gates. A positive theoretical result here is a
prompt to *review* a filter, never an instruction to weaken it.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.v51_rejection_taxonomy import categorize_rejection_reason, rejection_disposition


RR_QUALITY_COLUMNS: tuple[str, ...] = (
    "rr_bucket",
    "trades",
    "wins",
    "win_rate",
    "avg_r",
    "total_r",
    "expectancy",
)

REJECTION_REVIEW_COLUMNS: tuple[str, ...] = (
    "rejection_category",
    "disposition",
    "trades",
    "wins",
    "win_rate",
    "avg_r",
    "total_r",
    "expectancy",
    "review_flag",
)

FALSE_NEGATIVE_COLUMNS: tuple[str, ...] = (
    "rejection_category",
    "blocked_candidates",
    "theoretical_wins",
    "theoretical_win_rate",
    "foregone_total_r",
    "avg_r",
)

# Rejection categories that represent a discretionary/quality judgement rather
# than a hard capital-protection gate. These are the only ones eligible to be
# flagged as a "false negative" worth reviewing.
_QUALITY_FILTER_CATEGORIES = ("quality_guard", "setup_unconfirmed", "mtf_misaligned")

# RR buckets. Lower edge inclusive, upper edge exclusive; last bucket is open.
_RR_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("<1.2", float("-inf"), 1.2),
    ("1.2-1.5", 1.2, 1.5),
    ("1.5-2.0", 1.5, 2.0),
    ("2.0-3.0", 2.0, 3.0),
    (">=3.0", 3.0, float("inf")),
)


def classify_rejection_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Return rejected outcome rows tagged with ``rejection_category``/``disposition``."""
    if outcomes is None or outcomes.empty or "decision" not in outcomes.columns:
        return _empty(["rejection_category", "disposition"])

    decisions = outcomes["decision"].astype(str).str.upper()
    rejected = outcomes[decisions != "ACCEPTED"].copy()
    if rejected.empty:
        return _empty(["rejection_category", "disposition"])

    reasons = rejected.get("reason", pd.Series("", index=rejected.index))
    categories = [categorize_rejection_reason(reason) for reason in reasons]
    rejected["rejection_category"] = categories
    rejected["disposition"] = [rejection_disposition(category) for category in categories]
    return rejected.reset_index(drop=True)


def build_rr_quality(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Bucket simulated outcomes by risk/reward and report performance per bucket."""
    valid = _valid_outcomes(outcomes)
    if valid.empty or "risk_reward" not in valid.columns:
        return _empty(RR_QUALITY_COLUMNS)
    valid["risk_reward"] = pd.to_numeric(valid["risk_reward"], errors="coerce")
    valid = valid.dropna(subset=["risk_reward"])
    if valid.empty:
        return _empty(RR_QUALITY_COLUMNS)

    rows = []
    for label, low, high in _RR_BUCKETS:
        subset = valid[(valid["risk_reward"] >= low) & (valid["risk_reward"] < high)]
        if subset.empty:
            continue
        rows.append({"rr_bucket": label, **_performance_metrics(subset)})
    return pd.DataFrame(rows, columns=RR_QUALITY_COLUMNS)


def build_rejection_review(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Per rejection category, report theoretical performance and a review flag."""
    classified = classify_rejection_outcomes(outcomes)
    valid = _valid_outcomes(classified)
    if valid.empty:
        return _empty(REJECTION_REVIEW_COLUMNS)

    rows = []
    for category, group in valid.groupby("rejection_category"):
        metrics = _performance_metrics(group)
        disposition = rejection_disposition(str(category))
        # A review is warranted only when a non-safety-critical filter blocked
        # candidates that would have been theoretically profitable.
        review_flag = bool(
            disposition in {"review_candidate", "threshold"}
            and metrics["expectancy"] > 0
            and metrics["trades"] >= 5
        )
        rows.append(
            {
                "rejection_category": category,
                "disposition": disposition,
                **metrics,
                "review_flag": review_flag,
            }
        )
    review = pd.DataFrame(rows, columns=REJECTION_REVIEW_COLUMNS)
    return review.sort_values(["review_flag", "total_r"], ascending=[False, False]).reset_index(drop=True)


def build_quality_guard_false_negatives(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Count theoretically-winning candidates blocked by discretionary quality filters."""
    classified = classify_rejection_outcomes(outcomes)
    valid = _valid_outcomes(classified)
    if valid.empty:
        return _empty(FALSE_NEGATIVE_COLUMNS)

    subset = valid[valid["rejection_category"].isin(_QUALITY_FILTER_CATEGORIES)]
    if subset.empty:
        return _empty(FALSE_NEGATIVE_COLUMNS)

    rows = []
    for category, group in subset.groupby("rejection_category"):
        r_values = pd.to_numeric(group["r_multiple"], errors="coerce")
        wins = int((group["outcome"] == "WIN").sum())
        blocked = int(len(group))
        foregone = float(r_values[r_values > 0].sum())
        rows.append(
            {
                "rejection_category": category,
                "blocked_candidates": blocked,
                "theoretical_wins": wins,
                "theoretical_win_rate": round(100.0 * wins / blocked, 2) if blocked else 0.0,
                "foregone_total_r": round(foregone, 4),
                "avg_r": round(float(r_values.mean()), 4) if not r_values.dropna().empty else 0.0,
            }
        )
    result = pd.DataFrame(rows, columns=FALSE_NEGATIVE_COLUMNS)
    return result.sort_values("foregone_total_r", ascending=False).reset_index(drop=True)


def _valid_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes is None or outcomes.empty or "outcome" not in outcomes.columns:
        return pd.DataFrame()
    valid = outcomes[outcomes["outcome"].isin(["WIN", "LOSS", "TIMEOUT"])].copy()
    if valid.empty:
        return pd.DataFrame()
    valid["r_multiple"] = pd.to_numeric(valid["r_multiple"], errors="coerce")
    return valid


def _performance_metrics(group: pd.DataFrame) -> dict:
    r_values = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
    trades = int(len(group))
    wins = int((group["outcome"] == "WIN").sum())
    total_r = float(r_values.sum())
    return {
        "trades": trades,
        "wins": wins,
        "win_rate": round(100.0 * wins / trades, 2) if trades else 0.0,
        "avg_r": round(float(r_values.mean()), 4) if not r_values.empty else 0.0,
        "total_r": round(total_r, 4),
        "expectancy": round(total_r / trades, 4) if trades else 0.0,
    }


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))
