"""Tests for backtester."""
import pandas as pd
import pytest
from src.backtesting.backtester import run_backtest, BacktestConfig
from src.strategy.rules import StrategyConfig

def test_backtest_empty_df():
    with pytest.raises(ValueError, match="empty"):
        run_backtest(pd.DataFrame(), StrategyConfig(), BacktestConfig())
