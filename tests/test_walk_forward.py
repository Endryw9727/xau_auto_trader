"""Tests for walk-forward analysis."""
import pandas as pd
import pytest

from src.lab.walk_forward_ai import run_walk_forward_analysis, summarize_walk_forward


def test_walk_forward_insufficient_data():
    df = pd.DataFrame({
        "Open": [1]*100, "High": [2]*100, "Low": [0.5]*100,
        "Close": [1.5]*100, "Volume": [100]*100,
    })
    with pytest.raises(ValueError, match="Need at least"):
        run_walk_forward_analysis(df, window_size=1000, step_size=500)


def test_walk_forward_basic():
    prices = list(range(1, 3001))
    df = pd.DataFrame({
        "Open": [p - 0.5 for p in prices],
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": prices,
        "Volume": [1000]*3000,
    })
    results = run_walk_forward_analysis(df, window_size=500, step_size=500)
    assert isinstance(results, list)


def test_summarize_empty():
    summary = summarize_walk_forward([])
    assert summary.empty
