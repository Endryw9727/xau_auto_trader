"""Tests for cross-asset correlation."""
import pandas as pd

from src.risk.cross_asset_correlation import CrossAssetCorrelation


def test_correlation_matrix():
    corr = CrossAssetCorrelation()
    corr.add_price_data("XAUUSD", pd.Series([2300, 2310, 2320, 2330, 2340]))
    corr.add_price_data("DXY", pd.Series([105, 104, 103, 102, 101]))
    matrix = corr.calculate_correlation_matrix()
    assert not matrix.empty
    assert "XAUUSD" in matrix.columns
    assert "DXY" in matrix.columns


def test_get_correlation():
    corr = CrossAssetCorrelation()
    corr.add_price_data("XAUUSD", pd.Series([2300, 2310, 2320, 2330, 2340, 2350, 2360, 2370, 2380, 2390]))
    corr.add_price_data("DXY", pd.Series([105, 104, 103, 102, 101, 100, 99, 98, 97, 96]))
    c = corr.get_correlation("XAUUSD", "DXY")
    assert c is not None
    assert c < 0  # Negative correlation expected


def test_diversification_score():
    corr = CrossAssetCorrelation()
    corr.add_price_data("XAUUSD", pd.Series([2300]*50))
    corr.add_price_data("DXY", pd.Series([100]*50))
    score = corr.get_diversification_score()
    assert 0 <= score <= 1


def test_hedge_candidates():
    corr = CrossAssetCorrelation()
    corr.add_price_data("XAUUSD", pd.Series([2300, 2310, 2320, 2330, 2340]))
    corr.add_price_data("DXY", pd.Series([105, 104, 103, 102, 101]))
    candidates = corr.get_hedge_candidates("XAUUSD")
    assert len(candidates) > 0
    assert candidates[0]["correlation"] < 0
