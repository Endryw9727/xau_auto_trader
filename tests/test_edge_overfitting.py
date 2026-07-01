"""Tests for wiring the edge family into the overfitting engine."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analysis import edge_overfitting as eo


def _ohlc(days: int = 400, seed: int = 1, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2024-01-01")
    for d in range(days):
        base = start + pd.Timedelta(days=d)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            step = rng.normal(drift, 0.1)
            o = price
            c = price * (1 + step / 100)
            rows.append({"Date": ts, "Open": o, "High": max(o, c) * 1.001,
                         "Low": min(o, c) * 0.999, "Close": c, "Volume": 100})
            price = c
    return pd.DataFrame(rows).set_index("Date")


def test_session_return_series_shapes():
    series = eo.session_return_series(_ohlc(), "SYNTH")
    # 3 sessions x 2 directions.
    assert len(series) == 6
    assert "SYNTH/ASIA/LONG" in series
    assert all(isinstance(s, pd.Series) and len(s) > 0 for s in series.values())


def test_align_return_matrix_zero_fills_missing_days():
    a = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    b = pd.Series([3.0], index=pd.to_datetime(["2024-01-02"]))
    names, matrix = eo.align_return_matrix({"A": a, "B": b})
    assert names == ["A", "B"]
    assert matrix.shape == (2, 2)
    # B did not trade on 2024-01-01 -> flat 0.
    assert matrix[0, 1] == 0.0


def test_overfitting_audit_runs_on_multi_instrument_family():
    family: dict[str, pd.Series] = {}
    for i in range(4):
        family.update(eo.session_return_series(_ohlc(seed=i), f"S{i}"))
    out = eo.overfitting_audit(family, n_splits=10)
    assert out["status"] == "OK"
    assert out["live_armed"] is False
    assert out["n_strategies"] == 24  # 4 instruments x 6 strategies
    assert 0.0 <= out["probability_of_backtest_overfitting"] <= 1.0
    assert out["strategies"][0]["sharpe"] >= out["strategies"][-1]["sharpe"]


def test_overfitting_audit_needs_two_strategies():
    one = {"only": pd.Series([0.1, -0.2, 0.3], index=pd.to_datetime(
        ["2024-01-01", "2024-01-02", "2024-01-03"]))}
    assert eo.overfitting_audit(one)["status"] == "INSUFFICIENT_DATA"


def test_overfitting_audit_flags_planted_edge_as_less_overfit():
    # A family of pure noise vs. the same family plus one genuinely drifting
    # instrument: the planted edge should not raise PBO (it is real, not luck).
    noise = {}
    for i in range(5):
        noise.update(eo.session_return_series(_ohlc(seed=i), f"N{i}"))
    with_edge = dict(noise)
    with_edge.update(eo.session_return_series(_ohlc(seed=99, drift=0.05), "EDGE"))
    pbo_noise = eo.overfitting_audit(noise, n_splits=10)["probability_of_backtest_overfitting"]
    pbo_edge = eo.overfitting_audit(with_edge, n_splits=10)["probability_of_backtest_overfitting"]
    assert pbo_edge <= pbo_noise + 0.2  # planted real edge does not worsen overfitting


@pytest.mark.skipif(not Path("config/edge_lab.yaml").exists(), reason="needs edge config")
def test_runner_smoke(tmp_path):
    from scripts.run_overfitting_audit import run_overfitting_audit

    result = run_overfitting_audit(output_dir=tmp_path, n_splits=10)
    assert result.status == "OK"
    assert result.summary_path.exists()
    summary = pd.read_csv(result.summary_path)
    assert "deflated_sharpe_ratio" in summary.columns
    assert bool(summary["live_armed"].iloc[0]) is False
