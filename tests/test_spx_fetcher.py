"""Tests for SPX fetcher."""
import pandas as pd
import pytest

from src.macro.spx_fetcher import get_spx_bias, get_spx_current_value


def test_get_spx_bias_bullish():
    df = pd.DataFrame({
        "Close": [4000, 4100, 4200, 4300, 4400, 4500],
    })
    bias = get_spx_bias(df, fast_ema=3, slow_ema=5)
    assert bias == "BULLISH"


def test_get_spx_bias_bearish():
    df = pd.DataFrame({
        "Close": [4500, 4400, 4300, 4200, 4100, 4000],
    })
    bias = get_spx_bias(df, fast_ema=3, slow_ema=5)
    assert bias == "BEARISH"


def test_get_spx_current_value():
    df = pd.DataFrame({"Close": [4000, 4100, 4200]})
    value = get_spx_current_value(df)
    assert value == 4200.0
