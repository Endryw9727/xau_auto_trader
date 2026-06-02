"""Tests for portfolio risk management."""
import pandas as pd

from src.risk.portfolio_risk import PortfolioPosition, PortfolioRiskConfig, PortfolioRiskManager


def test_portfolio_heat_empty():
    manager = PortfolioRiskManager()
    manager.update_equity(10000)
    heat = manager._calculate_portfolio_heat()
    assert heat == 0.0


def test_portfolio_heat_with_positions():
    manager = PortfolioRiskManager()
    manager.update_equity(10000)
    manager.add_position(PortfolioPosition(
        symbol="XAUUSD", side="BUY", units=1.0,
        entry_price=2350.0, current_price=2350.0,
        stop_loss=2340.0, risk_amount=100.0, unrealized_pnl=0.0,
        asset_class="commodity",
    ))
    heat = manager._calculate_portfolio_heat()
    assert heat == 0.01  # 100/10000


def test_check_new_trade_allowed():
    config = PortfolioRiskConfig(max_portfolio_heat=0.10)
    manager = PortfolioRiskManager(config)
    manager.update_equity(10000)
    result = manager.check_new_trade("XAUUSD", "BUY", 1.0, 2350.0, 2340.0, 100.0)
    assert result.allowed is True
    assert result.heat_after_trade == 0.01


def test_check_new_trade_blocked_by_heat():
    config = PortfolioRiskConfig(max_portfolio_heat=0.05)
    manager = PortfolioRiskManager(config)
    manager.update_equity(10000)
    # Add existing position using 4% heat
    manager.add_position(PortfolioPosition(
        symbol="EURUSD", side="BUY", units=1.0,
        entry_price=1.10, current_price=1.10,
        stop_loss=1.09, risk_amount=400.0, unrealized_pnl=0.0,
        asset_class="forex",
    ))
    # New trade would exceed 5%
    result = manager.check_new_trade("XAUUSD", "BUY", 1.0, 2350.0, 2340.0, 200.0)
    assert result.allowed is False
    assert "Portfolio heat" in result.reason


def test_portfolio_summary():
    manager = PortfolioRiskManager()
    manager.update_equity(10000)
    manager.add_position(PortfolioPosition(
        symbol="XAUUSD", side="BUY", units=1.0,
        entry_price=2350.0, current_price=2350.0,
        stop_loss=2340.0, risk_amount=100.0, unrealized_pnl=0.0,
        asset_class="commodity",
    ))
    summary = manager.get_portfolio_summary()
    assert summary["total_positions"] == 1
    assert summary["portfolio_heat"] == 0.01


def test_asset_class_concentration():
    config = PortfolioRiskConfig(max_asset_class_heat=0.05)
    manager = PortfolioRiskManager(config)
    manager.update_equity(10000)
    # Add 3 forex positions = 6% heat
    for _ in range(3):
        manager.add_position(PortfolioPosition(
            symbol="EURUSD", side="BUY", units=1.0,
            entry_price=1.10, current_price=1.10,
            stop_loss=1.09, risk_amount=200.0, unrealized_pnl=0.0,
            asset_class="forex",
        ))
    result = manager.check_new_trade("GBPUSD", "BUY", 1.0, 1.30, 1.29, 100.0)
    assert result.allowed is False
    assert "Asset class heat" in result.reason
