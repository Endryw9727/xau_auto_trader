"""Tests for broker safety gate and interfaces."""
from pathlib import Path

import pytest

from src.broker.safety_gate import SafetyApproval, SafetyGate
from src.broker.broker_interface import BrokerOrder


def test_safety_gate_blocks_without_live_mode(monkeypatch):
    monkeypatch.setenv("LIVE_MODE", "false")
    gate = SafetyGate()
    result = gate.check_can_trade("XAUUSD", 10.0)
    assert result["allowed"] is False
    assert "LIVE_MODE" in result["reason"]


def test_safety_gate_blocks_without_approval_file(monkeypatch):
    monkeypatch.setenv("LIVE_MODE", "true")
    gate = SafetyGate(approval_file_path=Path("/tmp/nonexistent_approval"))
    result = gate.check_can_trade("XAUUSD", 10.0)
    assert result["allowed"] is False
    assert "Approval file not found" in result["reason"]


def test_safety_gate_blocks_symbol_not_allowed(monkeypatch):
    monkeypatch.setenv("LIVE_MODE", "true")
    gate = SafetyGate()
    # Create mock approval
    gate._approval = SafetyApproval(
        approved=True,
        timestamp="2026-01-01",
        user="test",
        reason="test",
        session_hash="abc",
        max_risk_per_day=100.0,
        max_trades_per_day=5,
        allowed_symbols=["EURUSD"],
    )
    result = gate.check_can_trade("XAUUSD", 10.0)
    assert result["allowed"] is False
    assert "not in approved list" in result["reason"]


def test_safety_gate_blocks_daily_limit(monkeypatch):
    monkeypatch.setenv("LIVE_MODE", "true")
    gate = SafetyGate()
    gate._approval = SafetyApproval(
        approved=True,
        timestamp="2026-01-01",
        user="test",
        reason="test",
        session_hash="abc",
        max_risk_per_day=100.0,
        max_trades_per_day=2,
        allowed_symbols=["XAUUSD"],
    )
    gate._daily_trade_count = 2
    result = gate.check_can_trade("XAUUSD", 10.0)
    assert result["allowed"] is False
    assert "Daily trade limit" in result["reason"]


def test_safety_gate_allows(monkeypatch):
    monkeypatch.setenv("LIVE_MODE", "true")
    gate = SafetyGate()
    gate._approval = SafetyApproval(
        approved=True,
        timestamp="2026-01-01",
        user="test",
        reason="test",
        session_hash="abc",
        max_risk_per_day=100.0,
        max_trades_per_day=5,
        allowed_symbols=["XAUUSD"],
    )
    result = gate.check_can_trade("XAUUSD", 10.0)
    assert result["allowed"] is True


def test_generate_approval_file():
    path = Path("/tmp/test_approval.json")
    if path.exists():
        path.unlink()
    result = SafetyGate.generate_approval_file("test_user", path=path)
    assert path.exists()
    path.unlink()


def test_broker_order_creation():
    order = BrokerOrder(
        symbol="XAUUSD",
        side="BUY",
        order_type="MARKET",
        units=1.0,
        stop_loss=2340.0,
        take_profit=2370.0,
    )
    assert order.symbol == "XAUUSD"
    assert order.trailing_stop_distance is None
