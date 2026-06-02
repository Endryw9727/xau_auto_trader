"""Tests for risk manager."""
import pytest
from src.risk.risk_manager import RiskConfig, RiskManager, TradeProposal
import pandas as pd

def test_risk_manager_max_open_trades():
    config = RiskConfig(max_open_trades=1)
    rm = RiskManager(config, 1000)

    proposal = TradeProposal(
        side="BUY", entry=100, stop_loss=99, take_profit=102,
        risk_reward=2.0, timestamp=pd.Timestamp("2026-01-01")
    )

    result1 = rm.can_open_trade(proposal)
    assert result1.allowed is True

    rm.register_trade({"id": "t1"})
    result2 = rm.can_open_trade(proposal)
    assert result2.allowed is False
    assert "Max open trades" in result2.reason
