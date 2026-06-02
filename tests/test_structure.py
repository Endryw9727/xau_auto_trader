"""Tests for market structure."""
import pandas as pd
from src.strategy.structure import detect_swing_highs, detect_swing_lows

def test_detect_swing_highs():
    highs = [1,2,3,4,5,4,3,2,1,2,3,4,5,6,5,4,3,2,1]
    df = pd.DataFrame({
        "Open": [0]*len(highs), "High": highs, "Low": [0]*len(highs),
        "Close": [0]*len(highs), "Volume": [100]*len(highs)
    })
    result = detect_swing_highs(df, window=2)
    assert result["swing_high"].sum() > 0
