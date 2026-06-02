"""Tests for derivatives (options and futures)."""
import pytest

from src.derivatives.options_pricer import BlackScholesPricer, OptionStrategyBuilder
from src.derivatives.futures_manager import ContangoAnalyzer, FuturesCalendar


def test_black_scholes_call():
    result = BlackScholesPricer.price(
        spot=2350.0, strike=2400.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        volatility=0.20, option_type="CALL",
    )
    assert result.price > 0
    assert result.greeks.delta > 0  # Call delta positive
    assert result.greeks.delta < 1
    assert result.greeks.vega > 0  # Vega always positive


def test_black_scholes_put():
    result = BlackScholesPricer.price(
        spot=2350.0, strike=2300.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        volatility=0.20, option_type="PUT",
    )
    assert result.price > 0
    assert result.greeks.delta < 0  # Put delta negative


def test_black_scholes_at_expiry():
    result = BlackScholesPricer.price(
        spot=2350.0, strike=2300.0,
        time_to_expiry=0.0, risk_free_rate=0.05,
        volatility=0.20, option_type="CALL",
    )
    assert result.price == 50.0  # Intrinsic value
    assert result.time_value == 0.0


def test_implied_volatility():
    # First price an option
    priced = BlackScholesPricer.price(
        spot=2350.0, strike=2400.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        volatility=0.20, option_type="CALL",
    )
    # Then reverse-engineer IV
    iv = BlackScholesPricer.implied_volatility(
        market_price=priced.price,
        spot=2350.0, strike=2400.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        option_type="CALL",
    )
    assert iv is not None
    assert abs(iv - 0.20) < 0.01


def test_straddle():
    result = OptionStrategyBuilder.straddle(
        spot=2350.0, strike=2350.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        volatility=0.20,
    )
    assert result["strategy"] == "Long Straddle"
    assert result["total_cost"] > 0
    assert result["break_even_up"] > 2350.0
    assert result["break_even_down"] < 2350.0


def test_bull_call_spread():
    result = OptionStrategyBuilder.bull_call_spread(
        spot=2350.0, lower_strike=2300.0, upper_strike=2400.0,
        time_to_expiry=0.25, risk_free_rate=0.05,
        volatility=0.20,
    )
    assert result["strategy"] == "Bull Call Spread"
    assert result["max_loss"] > 0
    assert result["max_profit"] > 0


def test_futures_calendar():
    contract = FuturesCalendar.get_contract("GC")
    assert contract.symbol == "GC"
    assert contract.contract_size == 100.0
    assert contract.tick_value == 10.0


def test_futures_roll_schedule():
    schedule = FuturesCalendar.get_roll_schedule("GC", current_price=2350.0, next_price=2348.0)
    assert schedule.basis == 2.0
    assert schedule.roll_cost == 200.0  # 2 * 100 oz


def test_contango_analyzer():
    prices = {
        "front": 2350.0,
        "month2": 2355.0,
        "month3": 2360.0,
    }
    result = ContangoAnalyzer.analyze_curve(prices)
    assert result["status"] == "contango"
    assert result["average_spread"] > 0


def test_backwardation():
    prices = {
        "front": 2350.0,
        "month2": 2345.0,
        "month3": 2340.0,
    }
    result = ContangoAnalyzer.analyze_curve(prices)
    assert result["status"] == "backwardation"
    assert result["recommendation"] == "long_futures"
