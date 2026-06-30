"""
Multiple-testing correction for the edge search (read-only research).

When many hypotheses are tested (instruments x sessions x directions x ...),
some will look significant by chance. This module converts edge t-stats into
p-values and applies family-wise (Bonferroni) and false-discovery-rate
(Benjamini-Hochberg) corrections, so a candidate edge is only trusted if it
survives correction for how much searching was done.

It uses a normal approximation for the t -> p mapping (valid because session
edges have hundreds of trades). It is pure statistics: no IO, no execution, no
orders.
"""

from __future__ import annotations

import math

import pandas as pd


def two_sided_p_from_t(t_stat: float) -> float:
    """Two-sided p-value for a t-stat, via the normal approximation."""
    if t_stat is None or (isinstance(t_stat, float) and math.isnan(t_stat)):
        return 1.0
    return math.erfc(abs(float(t_stat)) / math.sqrt(2.0))


def bonferroni_flags(p_values: list[float], *, alpha: float = 0.05) -> list[bool]:
    """Bonferroni: significant if p < alpha / m (m = number of tests)."""
    m = len(p_values)
    if m == 0:
        return []
    threshold = alpha / m
    return [p < threshold for p in p_values]


def benjamini_hochberg_flags(p_values: list[float], *, alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg step-up FDR control. Returns a flag per input p-value."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    threshold_rank = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= alpha * rank / m:
            threshold_rank = rank
    flags = [False] * m
    if threshold_rank > 0:
        for rank, idx in enumerate(order, start=1):
            if rank <= threshold_rank:
                flags[idx] = True
    return flags


def audit_edges(
    detail: pd.DataFrame,
    *,
    t_col: str = "oos_t_stat",
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Add p-value and multiple-testing flags to a family of candidate edges.

    The family is the whole table passed in (all instruments and combinations
    tested together). ``mtc_robust`` requires both the original walk-forward
    ``robust_edge`` (if present) and BH significance.
    """
    if detail is None or detail.empty or t_col not in detail.columns:
        result = pd.DataFrame(detail).copy() if detail is not None else pd.DataFrame()
        for column in ("p_value", "bonferroni_significant", "bh_significant", "mtc_robust"):
            result[column] = pd.Series(dtype="float64" if column == "p_value" else "bool")
        return result

    work = detail.copy().reset_index(drop=True)
    p_values = [two_sided_p_from_t(value) for value in work[t_col].tolist()]
    work["p_value"] = [round(p, 6) for p in p_values]
    work["bonferroni_significant"] = bonferroni_flags(p_values, alpha=alpha)
    bh = benjamini_hochberg_flags(p_values, alpha=alpha)
    work["bh_significant"] = bh
    if "robust_edge" in work.columns:
        work["mtc_robust"] = [bool(r) and bool(b) for r, b in zip(work["robust_edge"], bh)]
    else:
        work["mtc_robust"] = bh
    return work
