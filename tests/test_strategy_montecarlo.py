"""Tests for per-strategy Monte Carlo outcome tables."""

import numpy as np
import pandas as pd

from src.analysis import strategy_montecarlo as smc


def _series(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx)


def test_realised_profile_basic():
    win_rate, rr = smc._realised_profile(np.array([1.0, 1.0, -0.5, -0.5]))
    assert win_rate == 0.5
    assert rr == 2.0  # avg win 1.0 / avg loss 0.5


def test_outcome_table_skips_short_history():
    short = {"a": _series([0.1, -0.2, 0.3])}  # < _MIN_TRADES
    assert smc.strategy_outcome_table(short) == []


def test_outcome_table_ranks_by_expectancy():
    rng = np.random.default_rng(0)
    # Winner: positive-drift returns; loser: negative-drift returns.
    winner = _series(rng.normal(0.05, 0.5, size=300))
    loser = _series(rng.normal(-0.05, 0.5, size=300))
    rows = smc.strategy_outcome_table({"WIN": winner, "LOSE": loser}, n_sims=300)
    assert [r["strategy"] for r in rows][0] == "WIN"
    win_row = next(r for r in rows if r["strategy"] == "WIN")
    lose_row = next(r for r in rows if r["strategy"] == "LOSE")
    assert win_row["prob_profit"] > lose_row["prob_profit"]
    assert win_row["expectancy_r"] > lose_row["expectancy_r"]


def test_outcome_table_is_json_and_has_columns():
    import json

    rng = np.random.default_rng(1)
    series = {f"S{i}": _series(rng.normal(0.0, 0.4, size=120)) for i in range(3)}
    rows = smc.strategy_outcome_table(series, n_sims=200)
    for row in rows:
        assert set(smc.STRATEGY_MC_COLUMNS).issubset(row.keys())
    json.dumps(rows, allow_nan=False)


def test_summary_counts_profitable():
    rng = np.random.default_rng(2)
    series = {
        "GOOD": _series(rng.normal(0.06, 0.4, size=300)),
        "BAD": _series(rng.normal(-0.06, 0.4, size=300)),
    }
    rows = smc.strategy_outcome_table(series, n_sims=300)
    summary = smc.montecarlo_summary(rows)
    assert summary["status"] == "OK"
    assert summary["n_strategies"] == 2
    assert 0 <= summary["n_profitable"] <= 2
    assert summary["best_expectancy_r"] >= 0


def test_summary_empty():
    assert smc.montecarlo_summary([])["status"] == "INSUFFICIENT_DATA"
