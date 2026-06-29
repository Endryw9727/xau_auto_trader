from pathlib import Path

import pandas as pd
import pytest

from scripts import run_v51_demo_readiness_report as report
from src.analysis import v51_demo_readiness as readiness


def _outcomes() -> pd.DataFrame:
    rows = [
        # Day 1: two wins (cap respected), a third accepted is skipped by cap.
        _o("2026-05-20T11:00:00", "ACCEPTED", "WIN", 1.5),
        _o("2026-05-20T12:00:00", "ACCEPTED", "WIN", 1.5),
        _o("2026-05-20T13:00:00", "ACCEPTED", "WIN", 1.5),
        # Day 2: two losses -> daily loss lock.
        _o("2026-05-21T11:00:00", "ACCEPTED", "LOSS", -1.0),
        _o("2026-05-21T12:00:00", "ACCEPTED", "LOSS", -1.0),
        # Rejected candidates are ignored by the readiness sim.
        _o("2026-05-21T13:00:00", "REJECTED", "WIN", 1.5),
    ]
    return pd.DataFrame(rows)


def _o(candle_time, decision, outcome, r) -> dict:
    return {
        "signal_id": candle_time,
        "candle_time": candle_time,
        "decision": decision,
        "outcome": outcome,
        "r_multiple": r,
    }


def test_simulate_daily_equity_respects_cap_and_lock():
    equity = readiness.simulate_daily_equity(_outcomes(), max_trades_per_day=2, daily_loss_limit_r=2.0)

    assert len(equity) == 2
    day1 = equity.iloc[0]
    assert int(day1["trades_taken"]) == 2  # third skipped by cap
    assert float(day1["daily_r"]) == 3.0
    day2 = equity.iloc[1]
    assert int(day2["trades_taken"]) == 2
    assert float(day2["daily_r"]) == -2.0
    assert bool(day2["hit_daily_loss_lock"]) is True


def test_evaluate_guardrails_aggregate():
    evaluation = readiness.evaluate_guardrails(
        _outcomes(), max_trades_per_day=2, daily_loss_limit_r=2.0, max_drawdown_r=4.0
    )

    assert evaluation.trading_days == 2
    assert evaluation.total_trades == 4
    assert evaluation.capped_trades == 1  # one accepted candidate skipped by cap
    assert evaluation.daily_loss_lock_days == 1
    assert evaluation.total_r == 1.0  # +3 then -2
    assert evaluation.drawdown_lock_hit is False


def test_drawdown_lock_triggers():
    evaluation = readiness.evaluate_guardrails(
        _outcomes(), max_trades_per_day=2, daily_loss_limit_r=2.0, max_drawdown_r=1.5
    )
    # Day 2 drawdown is -2.0 R, beyond a 1.5 R budget.
    assert evaluation.drawdown_lock_hit is True


def test_simulate_daily_equity_validates_params():
    with pytest.raises(ValueError):
        readiness.simulate_daily_equity(_outcomes(), max_trades_per_day=0)
    with pytest.raises(ValueError):
        readiness.simulate_daily_equity(_outcomes(), daily_loss_limit_r=0)


def test_readiness_checklist_reports_safe_flags():
    class _Cfg:
        allow_real_live = False
        demo_only = True
        allow_demo_execution = False
        execution_enabled = False
        max_open_positions = 1

    checklist = readiness.build_readiness_checklist(_Cfg())
    assert set(checklist["status"]) == {"OK"}


def test_readiness_checklist_flags_unsafe_flag():
    class _Cfg:
        allow_real_live = True  # unsafe
        demo_only = True
        allow_demo_execution = False
        execution_enabled = False
        max_open_positions = 1

    checklist = readiness.build_readiness_checklist(_Cfg())
    bad = checklist[checklist["check"] == "allow_real_live"].iloc[0]
    assert bad["status"] == "REVIEW"


def test_empty_outcomes():
    assert readiness.simulate_daily_equity(pd.DataFrame()).empty
    evaluation = readiness.evaluate_guardrails(pd.DataFrame())
    assert evaluation.trading_days == 0


def test_script_generates_report(tmp_path, monkeypatch):
    csv_path = tmp_path / "xauusd.csv"
    csv_path.write_text("placeholder", encoding="utf-8")

    class _Cfg:
        warmup_candles = 0
        max_trades_per_day = 2
        allow_real_live = False
        demo_only = True
        allow_demo_execution = False
        execution_enabled = False
        max_open_positions = 1

    decision_log = pd.DataFrame(
        [
            {"signal_id": "a", "candle_time": "2026-05-20T11:00:00", "session": "LONDON", "side": "BUY",
             "decision": "ACCEPTED", "score": 80.0, "entry_price": 2000.0, "stop_loss": 1998.0,
             "take_profit": 2003.0, "risk_reward": 1.5, "reason": "accepted"},
        ]
    )
    market = pd.DataFrame(
        {"Open": [2000, 2001, 2004], "High": [2001, 2002, 2005], "Low": [1999, 2000, 2003], "Close": [2000, 2001, 2004]},
        index=pd.to_datetime(["2026-05-20 11:00", "2026-05-20 11:15", "2026-05-20 11:30"]),
    )
    monkeypatch.setattr(report, "load_v51_config", lambda *_a, **_k: _Cfg())
    monkeypatch.setattr(report, "load_csv_data", lambda *_a, **_k: market)
    monkeypatch.setattr(report, "build_demo_intraday_decision_log", lambda *_a, **_k: decision_log)

    result = report.run_v51_demo_readiness_report(csv_path=csv_path, output_dir=tmp_path / "diag", candles=200)

    assert result.status == "OK"
    assert result.checklist_path.exists()
    text = result.latest_path.read_text(encoding="utf-8")
    assert "Execution is NOT armed" in text
    assert "No orders were sent" in text


def test_script_does_not_execute_orders():
    source = Path("scripts/run_v51_demo_readiness_report.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "v51_demo_executor" not in source
    # Read-only over config flags: the report must not assign execution flags.
    assert "execution_enabled = True" not in source
    assert "allow_real_live = True" not in source
