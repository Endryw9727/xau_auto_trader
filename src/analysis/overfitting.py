"""
Overfitting-resistance engine for the edge search (read-only research).

Bonferroni/Benjamini-Hochberg (``multiple_testing.py``) correct a *family of
p-values*. This module adds the complementary, stronger tools from Bailey &
López de Prado that judge whether a discovered strategy is real once you account
for *how much searching was done* and for the non-normal shape of returns:

- Probabilistic Sharpe Ratio (PSR): probability the true Sharpe exceeds a
  benchmark, correcting the observed Sharpe for sample length, skewness and
  kurtosis.
- Expected Maximum Sharpe Ratio: how good the *best* of N zero-skill trials
  looks by pure luck — the benchmark a real edge must beat.
- Deflated Sharpe Ratio (DSR): PSR evaluated against that luck benchmark. A DSR
  well above 0.95 is the bar for "this survived the search".
- Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric
  Cross-Validation (CSCV): how often the in-sample best strategy lands *below
  the median* out-of-sample. PBO near 0.5 means the selection is noise.
- Combinatorial Purged Cross-Validation (CPCV) index splitter with embargo, for
  building overlap-safe backtest paths.

Pure statistics: no IO, no execution, no orders. Everything here can only make
the acceptance bar *higher*, never lower.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import e, sqrt
from statistics import NormalDist
from typing import Callable

import numpy as np

_NORM = NormalDist()
_EULER_MASCHERONI = 0.5772156649015329


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return _NORM.cdf(x)


def _phi_inv(p: float) -> float:
    """Standard normal inverse CDF (quantile), clamped to a safe open interval."""
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    return _NORM.inv_cdf(p)


# --------------------------------------------------------------------------- #
# Sharpe-based statistics
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SharpeMoments:
    """Per-observation Sharpe and the higher moments PSR/DSR need."""

    sharpe: float          # per-observation (NOT annualised) Sharpe ratio
    n: int                 # number of observations
    skew: float            # skewness (gamma_3)
    kurtosis: float        # kurtosis (gamma_4, normal == 3.0)


def sharpe_moments(returns: np.ndarray | list[float]) -> SharpeMoments:
    """Per-observation Sharpe, sample size, skewness and (non-excess) kurtosis."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n < 2:
        return SharpeMoments(sharpe=0.0, n=n, skew=0.0, kurtosis=3.0)
    mean = float(r.mean())
    # Sample std (ddof=1) for the Sharpe point estimate.
    std = float(r.std(ddof=1))
    if std == 0.0:
        return SharpeMoments(sharpe=0.0, n=n, skew=0.0, kurtosis=3.0)
    sharpe = mean / std
    # Biased central moments for skew/kurt (fine for the large samples here).
    dev = r - mean
    m2 = float((dev ** 2).mean())
    m3 = float((dev ** 3).mean())
    m4 = float((dev ** 4).mean())
    if m2 == 0.0:
        return SharpeMoments(sharpe=sharpe, n=n, skew=0.0, kurtosis=3.0)
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 ** 2)
    return SharpeMoments(sharpe=sharpe, n=n, skew=skew, kurtosis=kurt)


def probabilistic_sharpe_ratio(
    sharpe: float,
    n: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark: float = 0.0,
) -> float:
    """P(true Sharpe > ``benchmark``) given the observed Sharpe and its moments.

    All Sharpe inputs are per-observation (same frequency as the returns). The
    estimator variance follows Mertens/Lo and Bailey & López de Prado:

        sigma(SR)^2 = (1 - skew*SR + ((kurt-1)/4)*SR^2) / (n - 1)
    """
    if n < 2:
        return float("nan")
    variance_term = 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe
    if variance_term <= 0.0:
        # Degenerate moments; fall back to the normal-returns approximation.
        variance_term = 1.0 + 0.5 * sharpe * sharpe
    z = (sharpe - benchmark) * sqrt(n - 1) / sqrt(variance_term)
    return _phi(z)


def expected_maximum_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Expected max Sharpe of ``n_trials`` independent zero-skill strategies.

    ``sharpe_variance`` is the variance of the Sharpe ratios across the trials.
    Uses the extreme-value approximation from Bailey & López de Prado (2014).
    """
    if n_trials < 1 or sharpe_variance <= 0.0:
        return 0.0
    if n_trials == 1:
        return 0.0
    max_z = (1.0 - _EULER_MASCHERONI) * _phi_inv(1.0 - 1.0 / n_trials) \
        + _EULER_MASCHERONI * _phi_inv(1.0 - 1.0 / (n_trials * e))
    return sqrt(sharpe_variance) * max_z


def deflated_sharpe_ratio(
    sharpe: float,
    n: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    n_trials: int,
    sharpe_variance: float,
) -> float:
    """Deflated Sharpe Ratio: PSR against the expected-max-Sharpe luck benchmark.

    ``n_trials`` = how many strategies were tried; ``sharpe_variance`` = variance
    of their Sharpe ratios. DSR >> 0.95 is the bar for a real, search-adjusted
    edge.
    """
    benchmark = expected_maximum_sharpe(n_trials, sharpe_variance)
    return probabilistic_sharpe_ratio(
        sharpe, n, skew=skew, kurtosis=kurtosis, benchmark=benchmark
    )


def deflated_sharpe_ratio_from_trials(
    returns: np.ndarray | list[float],
    trial_sharpes: np.ndarray | list[float],
) -> float:
    """Convenience DSR: moments from ``returns`` of the selected strategy, and the
    trial count / Sharpe variance from all ``trial_sharpes`` that were searched."""
    moments = sharpe_moments(returns)
    trials = np.asarray(trial_sharpes, dtype=float)
    trials = trials[np.isfinite(trials)]
    n_trials = int(trials.size)
    variance = float(trials.var(ddof=1)) if n_trials > 1 else 0.0
    return deflated_sharpe_ratio(
        moments.sharpe,
        moments.n,
        skew=moments.skew,
        kurtosis=moments.kurtosis,
        n_trials=n_trials,
        sharpe_variance=variance,
    )


# --------------------------------------------------------------------------- #
# Probability of Backtest Overfitting (CSCV)
# --------------------------------------------------------------------------- #
def _block_sharpe(sum1: np.ndarray, sum2: np.ndarray, count: float) -> np.ndarray:
    """Per-strategy Sharpe from pooled block sums (population std, vectorised)."""
    if count <= 1:
        return np.zeros_like(sum1)
    mean = sum1 / count
    var = sum2 / count - mean * mean
    var = np.where(var <= 0.0, np.nan, var)
    sharpe = mean / np.sqrt(var)
    return np.nan_to_num(sharpe, nan=0.0, posinf=0.0, neginf=0.0)


@dataclass
class PBOResult:
    """Outcome of a CSCV probability-of-backtest-overfitting analysis."""

    pbo: float                        # P(IS-best strategy is below OOS median)
    n_combinations: int
    logits: list[float] = field(default_factory=list)
    oos_ranks: list[float] = field(default_factory=list)  # relative rank in [0,1]


def probability_of_backtest_overfitting(
    performance: np.ndarray,
    *,
    n_splits: int = 16,
    metric: Callable[[np.ndarray], np.ndarray] | None = None,
) -> PBOResult:
    """PBO via Combinatorially Symmetric Cross-Validation (Bailey et al. 2017).

    ``performance`` is a (T observations x N strategies) matrix of per-period
    performance (e.g. returns). Rows are split into ``n_splits`` contiguous
    blocks; for every way of choosing half the blocks as in-sample (the rest
    out-of-sample) we find the IS-best strategy and record its OOS rank. PBO is
    the fraction of splits where that strategy lands below the OOS median.

    PBO ~ 0.5 means the selection carries no out-of-sample information.
    """
    perf = np.asarray(performance, dtype=float)
    if perf.ndim != 2 or perf.shape[1] < 2 or perf.shape[0] < n_splits:
        return PBOResult(pbo=float("nan"), n_combinations=0)
    if n_splits < 2 or n_splits % 2 != 0:
        raise ValueError("n_splits must be an even number >= 2")

    n_obs, n_strats = perf.shape
    # Contiguous, near-equal blocks.
    bounds = np.linspace(0, n_obs, n_splits + 1).astype(int)
    default_metric = metric is None

    # Precompute per-block sums so each split is O(n_splits * n_strats).
    block_sum1 = np.empty((n_splits, n_strats))
    block_sum2 = np.empty((n_splits, n_strats))
    block_count = np.empty(n_splits)
    block_rows: list[np.ndarray] = []
    for b in range(n_splits):
        rows = perf[bounds[b]:bounds[b + 1]]
        block_rows.append(rows)
        block_sum1[b] = rows.sum(axis=0)
        block_sum2[b] = (rows * rows).sum(axis=0)
        block_count[b] = rows.shape[0]

    def score(block_idx: tuple[int, ...]) -> np.ndarray:
        if default_metric:
            s1 = block_sum1[list(block_idx)].sum(axis=0)
            s2 = block_sum2[list(block_idx)].sum(axis=0)
            cnt = float(block_count[list(block_idx)].sum())
            return _block_sharpe(s1, s2, cnt)
        stacked = np.vstack([block_rows[i] for i in block_idx])
        return metric(stacked)

    all_blocks = set(range(n_splits))
    logits: list[float] = []
    ranks: list[float] = []
    overfit = 0
    n_combos = 0
    for is_blocks in combinations(range(n_splits), n_splits // 2):
        oos_blocks = tuple(sorted(all_blocks - set(is_blocks)))
        is_score = score(is_blocks)
        oos_score = score(oos_blocks)
        best = int(np.argmax(is_score))
        # Relative OOS rank of the IS-best strategy in (0, 1); higher == better.
        rank = float((oos_score < oos_score[best]).sum() + 1) / (n_strats + 1)
        omega = min(max(rank, 1e-6), 1.0 - 1e-6)
        logit = float(np.log(omega / (1.0 - omega)))
        logits.append(logit)
        ranks.append(rank)
        if logit <= 0.0:
            overfit += 1
        n_combos += 1

    pbo = overfit / n_combos if n_combos else float("nan")
    return PBOResult(pbo=pbo, n_combinations=n_combos, logits=logits, oos_ranks=ranks)


# --------------------------------------------------------------------------- #
# Combinatorial Purged Cross-Validation splits
# --------------------------------------------------------------------------- #
def cpcv_splits(
    n_samples: int,
    *,
    n_groups: int = 6,
    test_groups: int = 2,
    embargo: float = 0.0,
):
    """Yield (train_idx, test_idx) for Combinatorial Purged Cross-Validation.

    Samples are cut into ``n_groups`` contiguous groups; every combination of
    ``test_groups`` groups becomes a test fold (the rest train). Train samples
    within ``embargo`` (a fraction of the series) of any test group are purged to
    avoid look-ahead/overlap leakage. Produces C(n_groups, test_groups) folds.
    """
    if n_samples < n_groups or n_groups < 2:
        raise ValueError("need n_samples >= n_groups >= 2")
    if not (1 <= test_groups < n_groups):
        raise ValueError("need 1 <= test_groups < n_groups")
    bounds = np.linspace(0, n_samples, n_groups + 1).astype(int)
    groups = [np.arange(bounds[g], bounds[g + 1]) for g in range(n_groups)]
    embargo_len = int(round(embargo * n_samples))

    for combo in combinations(range(n_groups), test_groups):
        test_idx = np.concatenate([groups[g] for g in combo])
        test_set = set(test_idx.tolist())
        blocked = set(test_set)
        if embargo_len > 0:
            lo, hi = int(test_idx.min()), int(test_idx.max())
            for j in range(hi + 1, min(hi + 1 + embargo_len, n_samples)):
                blocked.add(j)
            for j in range(max(lo - embargo_len, 0), lo):
                blocked.add(j)
        train_idx = np.array([i for i in range(n_samples) if i not in blocked])
        yield train_idx, np.sort(test_idx)


# --------------------------------------------------------------------------- #
# Top-level convenience report
# --------------------------------------------------------------------------- #
def overfitting_report(
    performance: np.ndarray,
    *,
    n_splits: int = 16,
) -> dict:
    """Run PBO + DSR (for the full-sample best strategy) over a performance matrix.

    Returns JSON-friendly summary fields. ``performance`` is (T x N) per-period
    returns for N searched strategies.
    """
    perf = np.asarray(performance, dtype=float)
    if perf.ndim != 2 or perf.shape[1] < 2:
        return {"status": "INSUFFICIENT_DATA", "n_strategies": 0}

    n_strats = perf.shape[1]
    full_sharpes = np.array([sharpe_moments(perf[:, j]).sharpe for j in range(n_strats)])
    best = int(np.argmax(full_sharpes))
    dsr = deflated_sharpe_ratio_from_trials(perf[:, best], full_sharpes)
    pbo = probability_of_backtest_overfitting(perf, n_splits=n_splits)
    sharpe_variance = float(full_sharpes.var(ddof=1)) if n_strats > 1 else 0.0
    return {
        "status": "OK",
        "n_strategies": n_strats,
        "best_strategy_index": best,
        "best_sharpe": round(float(full_sharpes[best]), 4),
        "expected_max_sharpe_under_null": round(
            expected_maximum_sharpe(n_strats, sharpe_variance), 4
        ),
        "deflated_sharpe_ratio": round(float(dsr), 4),
        "probability_of_backtest_overfitting": (
            round(float(pbo.pbo), 4) if pbo.n_combinations else None
        ),
        "pbo_n_combinations": pbo.n_combinations,
    }
