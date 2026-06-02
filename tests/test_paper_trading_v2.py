"""Tests for Paper Trading Engine V2."""
import pandas as pd
import pytest
from pathlib import Path

from src.paper.paper_trading_v2 import PaperTradingEngineV2, PaperTradeV2
from src.settings import load_settings


def test_paper_engine_init():
    settings = load_settings()
    engine = PaperTradingEngineV2(settings, initial_balance=2000)
    assert engine.risk_manager.balance == 2000
    assert engine.settings.trading.symbol == "XAUUSD"


def test_paper_engine_no_data():
    settings = load_settings()
    engine = PaperTradingEngineV2(settings)
    result = engine.run_cycle(csv_path=Path("nonexistent.csv"))
    assert "error" in result


def test_paper_engine_stats():
    settings = load_settings()
    engine = PaperTradingEngineV2(settings)
    stats = engine.get_stats()
    assert "balance" in stats
    assert "open_trades" in stats
    assert "total_trades" in stats


def test_paper_trade_dataclass():
    trade = PaperTradeV2(
        id="test_1",
        timestamp="2026-01-01",
        side="BUY",
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        risk_reward=2.0,
        units=1.0,
        risk_amount=10.0,
        macro_score=0.3,
        macro_label="BULLISH",
        news_allowed=True,
        smc_score=0.5,
        ai_score=0.7,
        ai_recommendation="BUY",
        ai_warnings=[],
        ai_explanation="test",
    )
    assert trade.side == "BUY"
    assert trade.macro_score == 0.3
    assert trade.smc_score == 0.5
