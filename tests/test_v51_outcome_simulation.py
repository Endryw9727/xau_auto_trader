from pathlib import Path

import pandas as pd
import pytest

from scripts import run_v51_outcome_diagnostics as report
from src.analysis import v51_outcome_simulation as sim


def _market_data() -> pd.DataFrame:
    # 15-min candles; deterministic paths for the candidates below.
    rows = [
        # 10:00 entry candle for BUY (entry 2000, SL 1998, TP 2003)
        ("2026-05-20 10:00:00", 2000, 2001, 1999, 2000),
        ("2026-05-20 10:15:00", 2000, 2002, 1999, 2001),  # no hit
        ("2026-05-20 10:30:00", 2001, 2004, 2001, 2003),  # BUY TP hit (high 2004 >= 2003)
        # 11:00 entry candle for SELL (entry 2000, SL 2002, TP 1997)
        ("2026-05-20 11:00:00", 2000, 2001, 1999, 2000),
        ("2026-05-20 11:15:00", 2000, 2003, 2000, 2002),  # SELL SL hit (high 2003 >= 2002)
        ("2026-05-20 11:30:00", 2002, 2002, 1990, 1996),
    ]
    index = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [100] * len(rows),
        },
        index=index,
    )


def _decision_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": "V51-buy",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 80.0,
                "entry_price": 2000.0,
                "stop_loss": 1998.0,
                "take_profit": 2003.0,
                "risk_reward": 1.5,
            },
            {
                "signal_id": "V51-sell",
                "candle_time": "2026-05-20T11:00:00",
                "session": "LONDON",
                "side": "SELL",
                "decision": "REJECTED",
                "score": 62.0,
                "entry_price": 2000.0,
                "stop_loss": 2002.0,
                "take_profit": 1997.0,
                "risk_reward": 1.5,
            },
        ]
    )


def test_simulate_buy_win_and_sell_loss():
    outcomes = sim.simulate_candidate_outcomes(_decision_log(), _market_data())

    buy = outcomes[outcomes["side"] == "BUY"].iloc[0]
    assert buy["outcome"] == "WIN"
    assert buy["r_multiple"] == pytest.approx(1.5)  # reward 3 / risk 2
    assert buy["bars_held"] == 2

    sell = outcomes[outcomes["side"] == "SELL"].iloc[0]
    assert sell["outcome"] == "LOSS"
    assert sell["r_multiple"] == -1.0
    assert sell["bars_held"] == 1


def test_stop_first_on_ambiguous_candle():
    # A single candle that spans both SL and TP must be scored as LOSS.
    data = pd.DataFrame(
        {
            "Open": [2000, 2000],
            "High": [2001, 2004],
            "Low": [1999, 1997],
            "Close": [2000, 2000],
            "Volume": [100, 100],
        },
        index=pd.to_datetime(["2026-05-20 10:00:00", "2026-05-20 10:15:00"]),
    )
    log = pd.DataFrame(
        [
            {
                "signal_id": "X",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 70.0,
                "entry_price": 2000.0,
                "stop_loss": 1998.0,
                "take_profit": 2003.0,
                "risk_reward": 1.5,
            }
        ]
    )
    outcomes = sim.simulate_candidate_outcomes(log, data)
    assert outcomes.iloc[0]["outcome"] == "LOSS"


def test_timeout_marks_to_market():
    data = pd.DataFrame(
        {
            "Open": [2000, 2000],
            "High": [2001, 2001],
            "Low": [1999, 1999],
            "Close": [2000, 2001],
            "Volume": [100, 100],
        },
        index=pd.to_datetime(["2026-05-20 10:00:00", "2026-05-20 10:15:00"]),
    )
    log = pd.DataFrame(
        [
            {
                "signal_id": "X",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 70.0,
                "entry_price": 2000.0,
                "stop_loss": 1998.0,
                "take_profit": 2010.0,
                "risk_reward": 5.0,
            }
        ]
    )
    outcomes = sim.simulate_candidate_outcomes(log, data, max_horizon_candles=1)
    row = outcomes.iloc[0]
    assert row["outcome"] == "TIMEOUT"
    assert row["r_multiple"] == pytest.approx(0.5)  # (2001-2000)/risk 2


def test_no_lookahead_uses_only_later_candles():
    # The entry candle itself spans SL/TP but must be ignored.
    data = pd.DataFrame(
        {
            "Open": [2000, 2000],
            "High": [2099, 2003],
            "Low": [1900, 2001],
            "Close": [2000, 2003],
            "Volume": [100, 100],
        },
        index=pd.to_datetime(["2026-05-20 10:00:00", "2026-05-20 10:15:00"]),
    )
    log = pd.DataFrame(
        [
            {
                "signal_id": "X",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 70.0,
                "entry_price": 2000.0,
                "stop_loss": 1998.0,
                "take_profit": 2003.0,
                "risk_reward": 1.5,
            }
        ]
    )
    outcomes = sim.simulate_candidate_outcomes(log, data)
    assert outcomes.iloc[0]["outcome"] == "WIN"
    assert outcomes.iloc[0]["bars_held"] == 1


def test_no_timeout_before_full_horizon():
    # Only one future candle is available but the horizon asks for 5: a still-open
    # candidate must be INVALID, not an artificial TIMEOUT that biases expectancy.
    data = pd.DataFrame(
        {
            "Open": [2000, 2000],
            "High": [2001, 2001],
            "Low": [1999, 1999],
            "Close": [2000, 2001],
            "Volume": [100, 100],
        },
        index=pd.to_datetime(["2026-05-20 10:00:00", "2026-05-20 10:15:00"]),
    )
    log = pd.DataFrame(
        [
            {
                "signal_id": "X",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 70.0,
                "entry_price": 2000.0,
                "stop_loss": 1998.0,
                "take_profit": 2010.0,
                "risk_reward": 5.0,
            }
        ]
    )
    outcomes = sim.simulate_candidate_outcomes(log, data, max_horizon_candles=5)
    assert outcomes.iloc[0]["outcome"] == "INVALID"


def test_accepted_only_filter():
    outcomes = sim.simulate_candidate_outcomes(_decision_log(), _market_data(), accepted_only=True)
    assert len(outcomes) == 1
    assert outcomes.iloc[0]["side"] == "BUY"


def test_performance_summary_by_side():
    outcomes = sim.simulate_candidate_outcomes(_decision_log(), _market_data())
    summary = sim.build_performance_summary(outcomes, by="side")

    assert set(summary["group"]) == {"BUY", "SELL"}
    buy = summary[summary["group"] == "BUY"].iloc[0]
    assert buy["wins"] == 1
    assert buy["win_rate"] == 100.0
    assert buy["total_r"] == pytest.approx(1.5)


def test_score_threshold_curve_filters():
    outcomes = sim.simulate_candidate_outcomes(_decision_log(), _market_data())
    curve = sim.build_score_threshold_curve(outcomes, thresholds=(0.0, 70.0))

    high = curve[curve["group"] == "score>=70"].iloc[0]
    assert high["trades"] == 1  # only the score=80 BUY survives


def test_empty_inputs():
    assert sim.simulate_candidate_outcomes(pd.DataFrame(), _market_data()).empty
    assert sim.build_performance_summary(pd.DataFrame(), by="session").empty


def test_script_generates_report(tmp_path, monkeypatch):
    csv_path = tmp_path / "xauusd.csv"
    csv_path.write_text("placeholder", encoding="utf-8")

    class _Cfg:
        warmup_candles = 0

    monkeypatch.setattr(report, "load_v51_config", lambda *_a, **_k: _Cfg())
    monkeypatch.setattr(report, "load_csv_data", lambda *_a, **_k: _market_data())
    monkeypatch.setattr(report, "build_demo_intraday_decision_log", lambda *_a, **_k: _decision_log())

    result = report.run_v51_outcome_diagnostics(csv_path=csv_path, output_dir=tmp_path / "diag", candles=200)

    assert result.status == "OK"
    assert result.outcomes_path.exists()
    assert result.by_session_path.exists()
    assert result.by_side_path.exists()
    assert result.score_curve_path.exists()
    text = result.latest_path.read_text(encoding="utf-8")
    assert "Per direction" in text
    assert "No orders were sent" in text


def test_script_handles_missing_csv(tmp_path):
    result = report.run_v51_outcome_diagnostics(csv_path=tmp_path / "missing.csv", output_dir=tmp_path / "diag")
    assert result.status == "ERROR"
    assert result.outcomes_path.exists()


def test_script_does_not_execute_orders():
    source = Path("scripts/run_v51_outcome_diagnostics.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "v51_demo_executor" not in source
