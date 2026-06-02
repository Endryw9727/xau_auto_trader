"""Tests for macro snapshot model."""
from src.macro.macro_snapshot import MacroSnapshot

def test_macro_snapshot_creation():
    snapshot = MacroSnapshot(dxy_value=105.5, dxy_trend="BULLISH")
    assert snapshot.dxy_value == 105.5
    assert snapshot.dxy_trend == "BULLISH"
