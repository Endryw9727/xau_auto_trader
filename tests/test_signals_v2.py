"""Tests for V2 signal generation with Smart Money."""
import pandas as pd
import pytest

from src.strategy.signals_v2 import check_smc_confluence, generate_signals_v2
from src.strategy.rules import StrategyConfig


def test_check_smc_confluence_no_trade():
    df = pd.DataFrame({
        "Open": [1]*10, "High": [2]*10, "Low": [0.5]*10,
        "Close": [1.5]*10, "Volume": [100]*10,
    })
    result = check_smc_confluence(df, "NO_TRADE", 1.5)
    assert result.smc_score == 0.0
    assert result.fvg_aligned is False


def test_generate_signals_v2_empty_df():
    with pytest.raises(ValueError, match="empty"):
        generate_signals_v2(pd.DataFrame(), StrategyConfig())


def test_generate_signals_v2_insufficient_data():
    df = pd.DataFrame({
        "Open": [1]*10, "High": [2]*10, "Low": [0.5]*10,
        "Close": [1.5]*10, "Volume": [100]*10,
    })
    with pytest.raises(ValueError, match="warm up"):
        generate_signals_v2(df, StrategyConfig())


def test_generate_signals_v2_with_smc():
    # Create data with clear trend for signal generation
    prices = list(range(1, 301))  # Strong uptrend
    df = pd.DataFrame({
        "Open": [p - 0.5 for p in prices],
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": prices,
        "Volume": [1000]*300,
    })
    result = generate_signals_v2(df, StrategyConfig(), use_smc=True, min_smc_score=0.0)
    assert "smc_score" in result.columns
    assert "smc_confluence" in result.columns
    assert len(result) == 300
