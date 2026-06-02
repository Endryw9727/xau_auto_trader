"""Tests for signal generation."""
import pandas as pd
import pytest
from src.strategy.signals import generate_signals
from src.strategy.rules import StrategyConfig

def test_generate_signals_empty_df():
    with pytest.raises(ValueError, match="empty"):
        generate_signals(pd.DataFrame(), StrategyConfig())

def test_generate_signals_insufficient_data():
    df = pd.DataFrame({
        "Open": [1]*10, "High": [2]*10, "Low": [0.5]*10,
        "Close": [1.5]*10, "Volume": [100]*10
    })
    with pytest.raises(ValueError, match="warm up"):
        generate_signals(df, StrategyConfig())
