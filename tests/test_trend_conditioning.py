"""Tests for trend-regime conditioning, especially the no-lookahead guard."""

import numpy as np
import pandas as pd

from src.analysis import trend_conditioning as tc


def _intraday(days: int, seed: int = 0, drift: float = 0.0) -> pd.DataFrame:
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


def test_trend_labels_only_up_or_down():
    labels = tc.entry_trend_labels(_intraday(200, drift=0.02)).dropna()
    assert set(labels.unique()).issubset({tc.UPTREND, tc.DOWNTREND})
    assert len(labels) > 0


def test_uptrend_dominates_in_rising_market():
    labels = tc.entry_trend_labels(_intraday(250, seed=3, drift=0.05)).dropna()
    # A persistent up-drift should be labelled UPTREND most of the time.
    assert (labels == tc.UPTREND).mean() > 0.6


def test_trend_label_has_no_lookahead():
    data = _intraday(160, seed=1)
    before = tc.entry_trend_labels(data)
    # Inflate an interior day's close massively; it must not change that day's own
    # label (which depends only on prior closes).
    spike_day = pd.Timestamp("2024-04-01")
    mask = data.index.normalize() == spike_day
    spiked = data.copy()
    spiked.loc[mask, "Close"] = spiked.loc[mask, "Close"] * 2.0
    after = tc.entry_trend_labels(spiked)
    assert before.get(spike_day) == after.get(spike_day)


def test_trend_series_keys():
    series = tc.trend_return_series(_intraday(300), "SYNTH")
    assert series
    for key in series:
        assert key.startswith("SYNTH/")
        assert key.endswith(tc.UPTREND) or key.endswith(tc.DOWNTREND)


def test_trend_series_empty_on_empty_input():
    assert tc.trend_return_series(pd.DataFrame(), "X") == {}
