from pathlib import Path

import pandas as pd

from scripts import run_v51_quality_review as report
from src.analysis import v51_quality_review as review


def _outcomes() -> pd.DataFrame:
    # Mix of accepted and rejected candidates with simulated outcomes + reason.
    return pd.DataFrame(
        [
            _o("a", "ACCEPTED", "BUY", 1.25, "WIN", 1.25, "V51 demo intraday signal accepted"),
            _o("b", "ACCEPTED", "SELL", 1.25, "LOSS", -1.0, "V51 demo intraday signal accepted"),
            _o("c", "REJECTED", "BUY", 1.25, "WIN", 1.25, "BUY quality guard blocked"),
            _o("d", "REJECTED", "BUY", 1.25, "WIN", 1.25, "BUY quality guard blocked"),
            _o("e", "REJECTED", "SELL", 1.25, "LOSS", -1.0, "SELL quality guard blocked"),
            _o("f", "REJECTED", "BUY", 1.25, "WIN", 1.25, "score 58.0 below 60.0"),
            _o("g", "REJECTED", "SELL", 1.25, "LOSS", -1.0, "RR 1.10 below 1.20"),
        ]
    )


def _o(sid, decision, side, rr, outcome, r, reason) -> dict:
    return {
        "signal_id": sid,
        "session": "LONDON",
        "side": side,
        "decision": decision,
        "score": 60.0,
        "risk_reward": rr,
        "outcome": outcome,
        "r_multiple": r,
        "reason": reason,
    }


def test_classify_rejection_outcomes_excludes_accepted():
    classified = review.classify_rejection_outcomes(_outcomes())
    assert set(classified["decision"].str.upper()) == {"REJECTED"}
    assert "quality_guard" in set(classified["rejection_category"])
    assert "rr_low" in set(classified["rejection_category"])


def test_build_rr_quality_buckets():
    rr = review.build_rr_quality(_outcomes())
    assert not rr.empty
    # All RR are 1.25 → single 1.2-1.5 bucket with all 7 trades.
    assert set(rr["rr_bucket"]) == {"1.2-1.5"}
    assert int(rr.iloc[0]["trades"]) == 7


def test_build_quality_guard_false_negatives():
    fn = review.build_quality_guard_false_negatives(_outcomes())
    quality = fn[fn["rejection_category"] == "quality_guard"].iloc[0]
    assert int(quality["blocked_candidates"]) == 3
    assert int(quality["theoretical_wins"]) == 2
    assert float(quality["foregone_total_r"]) == 2.5  # two winners at +1.25R


def test_build_rejection_review_flags_profitable_non_safety_filter():
    review_table = review.build_rejection_review(_outcomes())
    quality_row = review_table[review_table["rejection_category"] == "quality_guard"].iloc[0]
    assert quality_row["disposition"] == "review_candidate"
    # 2 wins / 1 loss = +1.5R over 3 trades → positive expectancy, but < 5 trades
    # so it is NOT flagged (guard against small-sample false positives).
    assert bool(quality_row["review_flag"]) is False

    rr_row = review_table[review_table["rejection_category"] == "rr_low"].iloc[0]
    assert rr_row["disposition"] == "safety_critical"
    assert bool(rr_row["review_flag"]) is False  # safety filters never flagged


def test_review_flag_requires_min_sample():
    rows = [_o(str(i), "REJECTED", "BUY", 1.25, "WIN", 1.25, "BUY quality guard blocked") for i in range(6)]
    review_table = review.build_rejection_review(pd.DataFrame(rows))
    quality_row = review_table[review_table["rejection_category"] == "quality_guard"].iloc[0]
    assert bool(quality_row["review_flag"]) is True


def test_empty_inputs():
    assert review.build_rr_quality(pd.DataFrame()).empty
    assert review.build_rejection_review(pd.DataFrame()).empty
    assert review.build_quality_guard_false_negatives(pd.DataFrame()).empty


def test_script_generates_report(tmp_path, monkeypatch):
    csv_path = tmp_path / "xauusd.csv"
    csv_path.write_text("placeholder", encoding="utf-8")

    class _Cfg:
        warmup_candles = 0

    decision_log = pd.DataFrame(
        [
            {"signal_id": "a", "candle_time": "2026-05-20T11:00:00", "session": "LONDON", "side": "BUY",
             "decision": "REJECTED", "score": 58.0, "entry_price": 2000.0, "stop_loss": 1998.0,
             "take_profit": 2003.0, "risk_reward": 1.5, "reason": "BUY quality guard blocked"},
        ]
    )
    market = pd.DataFrame(
        {"Open": [2000, 2001, 2004], "High": [2001, 2002, 2005], "Low": [1999, 2000, 2003], "Close": [2000, 2001, 2004]},
        index=pd.to_datetime(["2026-05-20 11:00", "2026-05-20 11:15", "2026-05-20 11:30"]),
    )
    monkeypatch.setattr(report, "load_v51_config", lambda *_a, **_k: _Cfg())
    monkeypatch.setattr(report, "load_csv_data", lambda *_a, **_k: market)
    monkeypatch.setattr(report, "build_demo_intraday_decision_log", lambda *_a, **_k: decision_log)

    result = report.run_v51_quality_review(csv_path=csv_path, output_dir=tmp_path / "diag", candles=200)

    assert result.status == "OK"
    assert result.rr_path.exists()
    assert result.review_path.exists()
    assert result.false_negatives_path.exists()
    text = result.latest_path.read_text(encoding="utf-8")
    assert "Quality-guard false negatives" in text
    assert "No orders were sent" in text


def test_script_handles_missing_csv(tmp_path):
    result = report.run_v51_quality_review(csv_path=tmp_path / "missing.csv", output_dir=tmp_path / "diag")
    assert result.status == "ERROR"
    assert result.rr_path.exists()


def test_script_does_not_execute_orders():
    source = Path("scripts/run_v51_quality_review.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "v51_demo_executor" not in source
