"""Tests for the overfitting-resistance engine.

The engine only matters if it is correct, so these check known-answer cases:
pure noise must look like noise (PBO ~ 0.5, DSR ~ 0.5), and genuine persistent
skill must be recognised (DSR high, PBO low).
"""

import math

import numpy as np
import pytest

from src.analysis import overfitting as of


# --------------------------------------------------------------------------- #
# PSR / DSR
# --------------------------------------------------------------------------- #
def test_psr_at_zero_sharpe_is_half():
    # Observed Sharpe exactly at the benchmark -> 50/50.
    assert of.probabilistic_sharpe_ratio(0.0, 500, benchmark=0.0) == pytest.approx(0.5, abs=1e-9)


def test_psr_increases_with_sharpe_and_sample():
    low = of.probabilistic_sharpe_ratio(0.05, 250)
    high = of.probabilistic_sharpe_ratio(0.20, 250)
    assert high > low > 0.5
    # More observations -> more confident for the same Sharpe.
    small_n = of.probabilistic_sharpe_ratio(0.10, 100)
    big_n = of.probabilistic_sharpe_ratio(0.10, 2000)
    assert big_n > small_n


def test_psr_short_sample_is_nan():
    assert math.isnan(of.probabilistic_sharpe_ratio(0.2, 1))


def test_expected_max_sharpe_grows_with_trials():
    e1 = of.expected_maximum_sharpe(1, 1.0)
    e10 = of.expected_maximum_sharpe(10, 1.0)
    e1000 = of.expected_maximum_sharpe(1000, 1.0)
    assert e1 == 0.0
    assert e1000 > e10 > 0.0
    # Zero dispersion across trials -> no deflation benchmark.
    assert of.expected_maximum_sharpe(1000, 0.0) == 0.0


def test_deflation_lowers_the_probability():
    # With many trials, the same Sharpe must clear a *higher* bar, so DSR < PSR.
    psr = of.probabilistic_sharpe_ratio(0.15, 1000)
    dsr = of.deflated_sharpe_ratio(0.15, 1000, n_trials=200, sharpe_variance=0.01)
    assert dsr < psr


def test_sharpe_moments_recovers_normal_shape():
    rng = np.random.default_rng(0)
    r = rng.normal(0.01, 1.0, size=20000)
    m = of.sharpe_moments(r)
    assert m.n == 20000
    assert m.skew == pytest.approx(0.0, abs=0.1)
    assert m.kurtosis == pytest.approx(3.0, abs=0.15)  # non-excess kurtosis
    assert m.sharpe == pytest.approx(0.01, abs=0.02)


# --------------------------------------------------------------------------- #
# PBO via CSCV
# --------------------------------------------------------------------------- #
def test_pbo_pure_noise_is_around_half():
    # The CSCV estimator is unbiased but noisy per realisation, so average over
    # several pure-noise draws: the mean PBO must sit near 0.5.
    pbos = []
    for seed in range(12):
        rng = np.random.default_rng(seed)
        perf = rng.normal(0.0, 1.0, size=(1200, 40))
        result = of.probability_of_backtest_overfitting(perf, n_splits=10)
        assert result.n_combinations == math.comb(10, 5)
        pbos.append(result.pbo)
    assert 0.40 < float(np.mean(pbos)) < 0.60


def test_pbo_persistent_skill_is_low():
    rng = np.random.default_rng(11)
    perf = rng.normal(0.0, 1.0, size=(1200, 40))
    # One strategy has a real, persistent positive drift across the whole sample.
    perf[:, 0] += 0.30
    result = of.probability_of_backtest_overfitting(perf, n_splits=10)
    assert result.pbo < 0.15


def test_pbo_rejects_bad_shapes():
    assert math.isnan(of.probability_of_backtest_overfitting(np.zeros((5, 3)), n_splits=10).pbo)
    with pytest.raises(ValueError):
        of.probability_of_backtest_overfitting(np.zeros((100, 3)), n_splits=5)


# --------------------------------------------------------------------------- #
# CPCV splits
# --------------------------------------------------------------------------- #
def test_cpcv_split_count_and_disjoint():
    splits = list(of.cpcv_splits(1000, n_groups=6, test_groups=2))
    assert len(splits) == math.comb(6, 2)
    for train, test in splits:
        assert set(train.tolist()).isdisjoint(test.tolist())
        assert len(test) > 0


def test_cpcv_embargo_removes_adjacent_train():
    no_embargo = list(of.cpcv_splits(1000, n_groups=5, test_groups=1, embargo=0.0))
    with_embargo = list(of.cpcv_splits(1000, n_groups=5, test_groups=1, embargo=0.05))
    # Embargo can only shrink (or keep) the train set.
    assert len(with_embargo[0][0]) < len(no_embargo[0][0])


def test_cpcv_validates_arguments():
    with pytest.raises(ValueError):
        list(of.cpcv_splits(10, n_groups=1, test_groups=1))
    with pytest.raises(ValueError):
        list(of.cpcv_splits(100, n_groups=5, test_groups=5))


# --------------------------------------------------------------------------- #
# Top-level report
# --------------------------------------------------------------------------- #
def test_overfitting_report_flags_noise_vs_skill():
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 1.0, size=(1500, 30))
    noise_report = of.overfitting_report(noise, n_splits=10)
    assert noise_report["status"] == "OK"
    assert noise_report["deflated_sharpe_ratio"] < 0.9
    assert noise_report["probability_of_backtest_overfitting"] > 0.3

    skill = noise.copy()
    skill[:, 0] += 0.20  # one genuine edge
    skill_report = of.overfitting_report(skill, n_splits=10)
    assert skill_report["best_strategy_index"] == 0
    assert skill_report["deflated_sharpe_ratio"] > skill_report["expected_max_sharpe_under_null"] * 0 + 0.5
    assert skill_report["probability_of_backtest_overfitting"] < noise_report["probability_of_backtest_overfitting"]


def test_overfitting_report_insufficient_data():
    assert of.overfitting_report(np.zeros((100, 1)))["status"] == "INSUFFICIENT_DATA"
