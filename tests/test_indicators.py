"""Tests for technical indicators."""
import pandas as pd
import pytest
from src.strategy.indicators import add_ema, add_rsi, add_atr, add_macd, add_adx

def test_add_ema():
    df = pd.DataFrame({"Close": [1,2,3,4,5,6,7,8,9,10]})
    result = add_ema(df, 5)
    assert "EMA_5" in result.columns
    assert not result["EMA_5"].isna().all()

def test_add_rsi():
    df = pd.DataFrame({"Close": [10]*20 + [20]*20})
    result = add_rsi(df, 14)
    assert "RSI_14" in result.columns
