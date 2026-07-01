"""Tests for designed stop/target trade simulation."""

import numpy as np
import pandas as pd
import pytest

from src.analysis import setup_simulation as ss


def test_barrier_target_hit_is_win_with_correct_r():
    # Long: entry 100, stop 99 (risk 1), target 102 (reward 2R). Candle reaches 102.
    out = ss.simulate_barrier(
        np.array([102.0]), np.array([100.0]), np.array([101.0]),
        entry_price=100.0, stop_price=99.0, target_price=102.0, side="LONG",
    )
    assert out.outcome == "WIN"
    assert out.r_multiple == pytest.approx(2.0)


def test_barrier_stop_hit_is_minus_one_r():
    out = ss.simulate_barrier(
        np.array([100.5]), np.array([98.9]), np.array([99.0]),
        entry_price=100.0, stop_price=99.0, target_price=102.0, side="LONG",
    )
    assert out.outcome == "LOSS"
    assert out.r_multiple == -1.0


def test_barrier_ambiguous_candle_assumes_stop_first():
    # One candle spans both stop (99) and target (102): must be counted a LOSS.
    out = ss.simulate_barrier(
        np.array([103.0]), np.array([98.0]), np.array([101.0]),
        entry_price=100.0, stop_price=99.0, target_price=102.0, side="LONG",
    )
    assert out.outcome == "LOSS"


def test_barrier_timeout_marks_to_market():
    out = ss.simulate_barrier(
        np.array([100.5, 100.6]), np.array([99.5, 99.6]), np.array([100.2, 100.4]),
        entry_price=100.0, stop_price=99.0, target_price=102.0, side="LONG",
    )
    assert out.outcome == "TIMEOUT"
    # marked at last close 100.4, risk 1 -> +0.4R
    assert out.r_multiple == pytest.approx(0.4)


def test_barrier_short_side():
    out = ss.simulate_barrier(
        np.array([100.5]), np.array([97.9]), np.array([98.0]),
        entry_price=100.0, stop_price=101.0, target_price=98.0, side="SHORT",
    )
    assert out.outcome == "WIN"
    assert out.r_multiple == pytest.approx(2.0)


def _intraday(days: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2024-01-01")
    for d in range(days):
        base = start + pd.Timedelta(days=d)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            step = rng.normal(0.0, 0.2)
            o = price
            c = price * (1 + step / 100)
            rows.append({"Date": ts, "Open": o, "High": max(o, c) * 1.003,
                         "Low": min(o, c) * 0.997, "Close": c, "Volume": 100})
            price = c
    return pd.DataFrame(rows).set_index("Date")


def test_session_designed_trades_shapes_and_r_bounds():
    series = ss.session_designed_trades(_intraday(), "SYNTH", sl_pct=0.3, reward_risk=2.0)
    assert series
    for key, s in series.items():
        assert key.startswith("SYNTH/")
        assert key.endswith("LONG") or key.endswith("SHORT")
        # R-multiples are bounded below by -1 (a full stop) minus any cost.
        assert (s >= -1.0001).all()
        # and above by the designed reward (2R).
        assert (s <= 2.0001).all()


def test_session_designed_trades_validates_inputs():
    with pytest.raises(ValueError):
        ss.session_designed_trades(_intraday(5), "X", sl_pct=0.0)
    with pytest.raises(ValueError):
        ss.session_designed_trades(_intraday(5), "X", reward_risk=-1.0)


def test_session_designed_trades_empty_input():
    assert ss.session_designed_trades(pd.DataFrame(), "X") == {}
