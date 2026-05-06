import pytest

from src.risk.position_sizing import (
    calculate_position_size,
    calculate_risk_amount,
    calculate_risk_reward,
    calculate_stop_distance,
)
from src.risk.risk_manager import (
    AccountState,
    RiskConfig,
    SignalForRisk,
    evaluate_signal_risk,
)


def make_valid_signal() -> SignalForRisk:
    return SignalForRisk(
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
        risk_reward=2.0,
    )


def test_calculate_risk_amount():
    risk_amount = calculate_risk_amount(account_balance=1000.0, risk_percent=0.01)

    assert risk_amount == 10.0


def test_calculate_stop_distance():
    distance = calculate_stop_distance(entry_price=2350.0, stop_loss=2345.0)

    assert distance == 5.0


def test_calculate_position_size():
    size = calculate_position_size(
        account_balance=1000.0,
        risk_percent=0.01,
        entry_price=2350.0,
        stop_loss=2345.0,
        value_per_point=1.0,
    )

    assert size == 2.0


def test_calculate_risk_reward():
    rr = calculate_risk_reward(
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2360.0,
    )

    assert rr == 2.0


def test_position_size_rejects_invalid_balance():
    with pytest.raises(ValueError):
        calculate_position_size(
            account_balance=0.0,
            risk_percent=0.01,
            entry_price=2350.0,
            stop_loss=2345.0,
        )


def test_position_size_rejects_invalid_risk_percent():
    with pytest.raises(ValueError):
        calculate_position_size(
            account_balance=1000.0,
            risk_percent=1.5,
            entry_price=2350.0,
            stop_loss=2345.0,
        )


def test_risk_manager_approves_valid_signal():
    signal = make_valid_signal()
    config = RiskConfig(account_balance=1000.0, risk_per_trade=0.01, value_per_point=1.0)

    decision = evaluate_signal_risk(signal, config)

    assert decision.approved is True
    assert decision.status == "APPROVED"
    assert decision.position_size == 2.0
    assert decision.risk_amount == 10.0
    assert decision.risk_percent == 0.01


def test_risk_manager_blocks_no_trade_signal():
    signal = SignalForRisk(
        side="NO_TRADE",
        entry_price=None,
        stop_loss=None,
        take_profit=None,
        risk_reward=None,
    )

    decision = evaluate_signal_risk(signal)

    assert decision.approved is False
    assert decision.status == "BLOCKED"
    assert "not tradable" in decision.reason


def test_risk_manager_blocks_missing_stop_loss():
    signal = SignalForRisk(
        side="BUY",
        entry_price=2350.0,
        stop_loss=None,
        take_profit=2360.0,
        risk_reward=2.0,
    )

    decision = evaluate_signal_risk(signal)

    assert decision.approved is False
    assert "Missing stop loss" in decision.reason


def test_risk_manager_blocks_low_risk_reward():
    signal = SignalForRisk(
        side="BUY",
        entry_price=2350.0,
        stop_loss=2345.0,
        take_profit=2355.0,
        risk_reward=1.0,
    )
    config = RiskConfig(min_risk_reward=2.0)

    decision = evaluate_signal_risk(signal, config)

    assert decision.approved is False
    assert "Risk/reward below minimum" in decision.reason


def test_risk_manager_blocks_excessive_risk_per_trade():
    signal = make_valid_signal()
    config = RiskConfig(risk_per_trade=0.02, max_risk_per_trade=0.01)

    decision = evaluate_signal_risk(signal, config)

    assert decision.approved is False
    assert "exceeds" in decision.reason


def test_risk_manager_blocks_daily_loss_limit():
    signal = make_valid_signal()
    config = RiskConfig(account_balance=1000.0, max_daily_loss=0.02)
    account_state = AccountState(current_daily_pnl=-20.0)

    decision = evaluate_signal_risk(signal, config, account_state)

    assert decision.approved is False
    assert "Daily loss limit" in decision.reason


def test_risk_manager_blocks_max_open_trades():
    signal = make_valid_signal()
    config = RiskConfig(max_open_trades=2)
    account_state = AccountState(open_trades_count=2)

    decision = evaluate_signal_risk(signal, config, account_state)

    assert decision.approved is False
    assert "Maximum open trades" in decision.reason


def test_risk_manager_blocks_max_consecutive_losses():
    signal = make_valid_signal()
    config = RiskConfig(max_consecutive_losses=3)
    account_state = AccountState(consecutive_losses=3)

    decision = evaluate_signal_risk(signal, config, account_state)

    assert decision.approved is False
    assert "Maximum consecutive losses" in decision.reason
