"""Tests for expectancy + Monte Carlo trade-outcome simulation."""

import numpy as np
import pytest

from src.analysis import trade_simulation as ts


# --------------------------------------------------------------------------- #
# Expectancy (closed form)
# --------------------------------------------------------------------------- #
def test_breakeven_win_rate_known_values():
    assert ts.breakeven_win_rate(1.0) == pytest.approx(0.5)
    assert ts.breakeven_win_rate(2.0) == pytest.approx(1.0 / 3.0)
    assert ts.breakeven_win_rate(3.0) == pytest.approx(0.25)


def test_expectancy_and_required_win_rate_are_consistent():
    # At the break-even win rate the expectancy is exactly 0.
    rr = 2.0
    be = ts.breakeven_win_rate(rr)
    assert ts.expectancy_r(be, rr) == pytest.approx(0.0, abs=1e-9)
    assert ts.required_win_rate(rr) == pytest.approx(be)
    # A positive edge above break-even yields positive expectancy.
    assert ts.expectancy_r(be + 0.1, rr) > 0


def test_kelly_zero_when_no_edge():
    # Positive edge (win rate 0.5 > break-even 0.333): raw Kelly = 0.5 - 0.5/2.
    assert ts.kelly_fraction(0.5, 2.0) == pytest.approx(0.5 - 0.5 / 2.0)
    # Exactly at break-even -> 0.
    assert ts.kelly_fraction(ts.breakeven_win_rate(2.0), 2.0) == pytest.approx(0.0, abs=1e-9)
    # Negative edge is floored at 0 (never suggests risking capital without edge).
    assert ts.kelly_fraction(0.3, 2.0) == 0.0
    assert ts.kelly_fraction(0.2, 1.0) == 0.0


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def test_monte_carlo_positive_expectancy_is_usually_profitable():
    res = ts.monte_carlo_fixed(0.50, 2.0, n_trades=200, n_sims=2000, risk_per_trade=0.01, seed=1)
    assert res.expectancy_r > 0
    assert res.prob_profit > 0.8
    assert res.median_return > 0


def test_monte_carlo_negative_expectancy_usually_loses():
    res = ts.monte_carlo_fixed(0.30, 1.0, n_trades=200, n_sims=2000, risk_per_trade=0.01, seed=2)
    assert res.expectancy_r < 0
    assert res.prob_profit < 0.2
    assert res.median_return < 0


def test_monte_carlo_is_deterministic_with_seed():
    a = ts.monte_carlo_fixed(0.45, 2.0, seed=7).as_dict()
    b = ts.monte_carlo_fixed(0.45, 2.0, seed=7).as_dict()
    assert a == b


def test_monte_carlo_ruin_rises_with_risk():
    low = ts.monte_carlo_fixed(0.40, 1.5, risk_per_trade=0.01, n_trades=300, seed=3, ruin_drawdown=0.5)
    high = ts.monte_carlo_fixed(0.40, 1.5, risk_per_trade=0.15, n_trades=300, seed=3, ruin_drawdown=0.5)
    assert high.prob_ruin > low.prob_ruin


def test_monte_carlo_validates_inputs():
    with pytest.raises(ValueError):
        ts.monte_carlo_fixed(1.5, 2.0)
    with pytest.raises(ValueError):
        ts.monte_carlo_fixed(0.5, 2.0, n_trades=0)


def test_bootstrap_all_positive_returns_is_profitable():
    returns = [0.01, 0.02, 0.015, 0.008, 0.012]
    res = ts.bootstrap_monte_carlo(returns, n_trades=50, n_sims=500, seed=0)
    assert res.prob_profit == pytest.approx(1.0)


def test_bootstrap_mixed_returns_reflect_distribution():
    rng = np.random.default_rng(0)
    # Negative-expectancy trade sample: small wins, occasional big losses.
    returns = np.where(rng.random(1000) < 0.6, 0.01, -0.03)
    res = ts.bootstrap_monte_carlo(returns, n_trades=200, n_sims=1000, seed=1)
    assert res.prob_profit < 0.3


def test_bootstrap_rejects_empty():
    with pytest.raises(ValueError):
        ts.bootstrap_monte_carlo([])


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def test_expectancy_report_flags_edge():
    report = ts.expectancy_report(reward_risk=2.0, win_rate=0.45)
    assert report["breakeven_win_rate"] == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert report["profitable"] is True
    assert report["edge"] > 0

    losing = ts.expectancy_report(reward_risk=1.0, win_rate=0.40)
    assert losing["profitable"] is False
    assert losing["edge"] < 0
