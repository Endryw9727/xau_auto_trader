"""Tests for the Asia liquidity-sweep + reclaim setup."""

import numpy as np
import pandas as pd

from src.analysis import sweep_setup as sw


def _day(overrides: dict[int, tuple], date: str = "2024-03-01", flat: float = 100.0) -> pd.DataFrame:
    """One 24h day of hourly candles; ``overrides`` maps hour -> (O, H, L, C)."""
    rows = []
    base = pd.Timestamp(date)
    for hour in range(24):
        o, h, l, c = overrides.get(hour, (flat, flat, flat, flat))
        rows.append({"Date": base + pd.Timedelta(hours=hour), "Open": o, "High": h,
                     "Low": l, "Close": c, "Volume": 100})
    return pd.DataFrame(rows).set_index("Date")


def test_upside_sweep_reclaim_makes_short_win():
    # Asia (0-8) range ~[99.5, 100.5]. London hour 10 spikes to 101 then closes
    # back to 100 (sweep + reclaim -> SHORT). Hour 11 drops to the 2R target.
    overrides = {
        0: (100.0, 100.5, 100.0, 100.2),   # sets Asia high 100.5
        1: (100.0, 100.0, 99.5, 100.0),    # sets Asia low 99.5
        10: (100.2, 101.0, 100.0, 100.0),  # upside sweep + reclaim close 100.0
        11: (100.0, 100.0, 97.0, 97.5),    # drops through the short target
    }
    trades = sw.asia_sweep_trades(_day(overrides), "SYNTH", reward_risk=2.0)
    assert "SYNTH/ASIA_SWEEP/SHORT" in trades
    r = trades["SYNTH/ASIA_SWEEP/SHORT"].iloc[0]
    assert r == 2.0  # target hit -> +2R


def test_upside_sweep_then_stop_is_loss():
    overrides = {
        0: (100.0, 100.5, 100.0, 100.2),
        1: (100.0, 100.0, 99.5, 100.0),
        10: (100.2, 101.0, 100.0, 100.0),   # sweep + reclaim -> SHORT, stop ~101
        11: (100.0, 101.5, 100.0, 101.2),   # rallies back through the stop
    }
    trades = sw.asia_sweep_trades(_day(overrides), "SYNTH", reward_risk=2.0)
    assert trades["SYNTH/ASIA_SWEEP/SHORT"].iloc[0] == -1.0


def test_downside_sweep_reclaim_makes_long():
    overrides = {
        0: (100.0, 100.5, 100.0, 100.2),
        1: (100.0, 100.0, 99.5, 100.0),
        10: (99.8, 100.0, 99.0, 100.0),   # downside sweep (low 99.0 < 99.5) + reclaim
        11: (100.0, 103.0, 100.0, 102.5),  # rallies to the long target
    }
    trades = sw.asia_sweep_trades(_day(overrides), "SYNTH", reward_risk=2.0)
    assert "SYNTH/ASIA_SWEEP/LONG" in trades
    assert trades["SYNTH/ASIA_SWEEP/LONG"].iloc[0] == 2.0


def test_no_sweep_no_signal():
    # London stays inside the Asia range -> no sweep, no trade.
    overrides = {
        0: (100.0, 100.5, 100.0, 100.2),
        1: (100.0, 100.0, 99.5, 100.0),
        10: (100.0, 100.3, 99.7, 100.0),
    }
    assert sw.asia_sweep_trades(_day(overrides), "SYNTH") == {}


def test_empty_input():
    assert sw.asia_sweep_trades(pd.DataFrame(), "X") == {}


def test_invalid_reward_risk():
    import pytest
    with pytest.raises(ValueError):
        sw.asia_sweep_trades(_day({}), "X", reward_risk=0.0)
