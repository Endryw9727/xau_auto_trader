"""Tests for volatility-regime conditioning, especially the no-lookahead guard."""

import numpy as np
import pandas as pd

from src.analysis import regime_conditioning as rc


def _intraday(days: int, seed: int = 0, vol: float = 0.1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2024-01-01")
    for d in range(days):
        base = start + pd.Timedelta(days=d)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            step = rng.normal(0.0, vol)
            o = price
            c = price * (1 + step / 100)
            rows.append({"Date": ts, "Open": o, "High": max(o, c) * 1.002,
                         "Low": min(o, c) * 0.998, "Close": c, "Volume": 100})
            price = c
    return pd.DataFrame(rows).set_index("Date")


def test_daily_true_range_is_positive():
    tr = rc.daily_true_range(_intraday(30))
    assert len(tr) == 30
    assert (tr.dropna() >= 0).all()


def test_regime_labels_only_high_or_low():
    labels = rc.entry_regime_labels(_intraday(200)).dropna()
    assert set(labels.unique()).issubset({rc.HIGH_VOL, rc.LOW_VOL})
    assert len(labels) > 0


def test_regime_label_has_no_lookahead():
    # A volatility spike on day D must NOT change day D's own label — only later
    # days. Build a calm series, then inject a huge range on one interior day.
    data = _intraday(160, seed=1, vol=0.1)
    labels_before = rc.entry_regime_labels(data)

    spike_day = pd.Timestamp("2024-04-01")  # interior day with history
    mask = data.index.normalize() == spike_day
    spiked = data.copy()
    spiked.loc[mask, "High"] = spiked.loc[mask, "High"] * 1.5
    spiked.loc[mask, "Low"] = spiked.loc[mask, "Low"] * 0.5
    labels_after = rc.entry_regime_labels(spiked)

    # Same day's label unchanged; a later day's label is allowed to change.
    assert labels_before.get(spike_day) == labels_after.get(spike_day)
    next_day = spike_day + pd.Timedelta(days=1)
    assert next_day in labels_after.index


def test_conditional_series_keys_and_regime_split():
    series = rc.conditional_return_series(_intraday(300), "SYNTH")
    assert series  # non-empty
    for key in series:
        assert key.startswith("SYNTH/")
        assert key.endswith(rc.HIGH_VOL) or key.endswith(rc.LOW_VOL)
    # A base strategy can split into at most 2 regimes.
    asia_long = [k for k in series if k.startswith("SYNTH/ASIA/LONG/")]
    assert len(asia_long) <= 2


def test_conditional_series_empty_on_empty_input():
    assert rc.conditional_return_series(pd.DataFrame(), "X") == {}
