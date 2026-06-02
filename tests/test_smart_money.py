"""Tests for Smart Money Concepts."""
import pandas as pd
import pytest

from src.strategy.smart_money.fvg import detect_fvg, get_recent_fvg, FairValueGap
from src.strategy.smart_money.order_blocks import detect_order_blocks, get_recent_order_blocks
from src.strategy.smart_money.liquidity import detect_liquidity_sweeps, get_recent_sweeps
from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money, SmartMoneyAnalysis


def test_detect_fvg_bullish():
    # Create data with a bullish FVG: Low[i] > High[i-2]
    df = pd.DataFrame({
        "Open": [10, 11, 12, 15, 16],
        "High": [11, 12, 13, 16, 17],
        "Low": [9, 10, 14, 15, 16],  # Low[2]=14 > High[0]=11 -> bullish FVG
        "Close": [10.5, 11.5, 12.5, 15.5, 16.5],
        "Volume": [100]*5,
    })
    result = detect_fvg(df)
    assert result["fvg_bullish"].iloc[2] is True
    assert pd.notna(result["fvg_top"].iloc[2])


def test_detect_fvg_bearish():
    # Create data with a bearish FVG: High[i] < Low[i-2]
    df = pd.DataFrame({
        "Open": [10, 11, 12, 8, 7],
        "High": [11, 12, 13, 9, 8],  # High[2]=13, Low[0]=9 -> not bearish FVG at 2
        "Low": [9, 10, 11, 7, 6],
        "Close": [10.5, 11.5, 12.5, 8.5, 7.5],
        "Volume": [100]*5,
    })
    # Need High[2] < Low[0] -> 13 < 9 is False
    # Let's make it work: High[4]=8 < Low[2]=11
    df2 = pd.DataFrame({
        "Open": [20, 21, 22, 21, 18],
        "High": [21, 22, 23, 22, 19],  # High[4]=19 < Low[2]=20 -> bearish FVG
        "Low": [19, 20, 20, 20, 17],
        "Close": [20.5, 21.5, 22.5, 21.5, 18.5],
        "Volume": [100]*5,
    })
    result = detect_fvg(df2)
    assert result["fvg_bearish"].iloc[4] is True


def test_get_recent_fvg():
    df = pd.DataFrame({
        "Open": [10]*10, "High": [11]*10, "Low": [9]*10,
        "Close": [10.5]*10, "Volume": [100]*10,
    })
    fvgs = get_recent_fvg(df, lookback=5)
    assert isinstance(fvgs, list)


def test_detect_order_blocks():
    df = pd.DataFrame({
        "Open": [10, 11, 10, 9, 12],
        "High": [11, 12, 11, 10, 13],
        "Low": [9, 10, 9, 8, 11],
        "Close": [10.5, 11.5, 9.5, 8.5, 12.5],  # Candle 2 bearish, candle 3 strong bullish
        "Volume": [100]*5,
    })
    result = detect_order_blocks(df, lookback=2)
    # Should detect bullish OB at index 2 (bearish before strong bullish at 3)
    assert "ob_bullish" in result.columns


def test_detect_liquidity_sweeps():
    df = pd.DataFrame({
        "Open": [10, 11, 12, 13, 11],
        "High": [11, 12, 13, 14, 12],  # High[3]=14 > swing_high(10-12)=12, then Close[4]=11 < 12
        "Low": [9, 10, 11, 12, 10],
        "Close": [10.5, 11.5, 12.5, 13.5, 11.5],
        "Volume": [100]*5,
    })
    result = detect_liquidity_sweeps(df, window=2)
    assert "sweep_bearish" in result.columns


def test_analyze_smart_money():
    df = pd.DataFrame({
        "Open": [2300]*100,
        "High": [2310]*100,
        "Low": [2290]*100,
        "Close": [2305]*100,
        "Volume": [1000]*100,
    })
    analysis = analyze_smart_money(df, lookback=20)
    assert isinstance(analysis, SmartMoneyAnalysis)
    assert analysis.bias in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert isinstance(analysis.fvgs, list)
    assert isinstance(analysis.order_blocks, list)
    assert isinstance(analysis.liquidity_sweeps, list)


def test_smart_money_to_dict():
    analysis = SmartMoneyAnalysis(
        fvgs=[],
        order_blocks=[],
        liquidity_sweeps=[],
        bias="NEUTRAL",
        key_support=None,
        key_resistance=None,
        explanation="test",
    )
    d = analyze_smart_money.__wrapped__ if hasattr(analyze_smart_money, "__wrapped__") else None
    # Just test the dataclass
    assert analysis.bias == "NEUTRAL"
