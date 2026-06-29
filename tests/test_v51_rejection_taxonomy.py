from pathlib import Path

import pandas as pd
import pytest

from scripts import run_v51_rejection_diagnostics as diagnostics
from src.analysis import v51_rejection_taxonomy as taxonomy


def sample_decision_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row("BUY", "ACCEPTED", "LONDON", "V51 demo intraday signal accepted"),
            _row("SELL", "REJECTED", "NEW YORK", "score 58.0 below 60.0"),
            _row("BUY", "REJECTED", "NEW YORK", "score gap 2.0 below 4.0"),
            _row("SELL", "REJECTED", "ASIA", "session blocked: ASIA"),
            _row("BUY", "REJECTED", "LONDON", "BUY quality guard blocked"),
            _row("SELL", "REJECTED", "LONDON", "RR 1.10 below 1.20"),
            _row("NO_TRADE", "NO_TRADE", "ASIA", "V51 no directional score candidate"),
        ]
    )


def _row(side: str, decision: str, session: str, reason: str) -> dict:
    return {
        "signal_id": f"V51-{side}-{reason[:4]}",
        "candle_time": "2026-05-20T10:00:00",
        "session": session,
        "side": side,
        "decision": decision,
        "score": 60.0,
        "score_gap": 5.0,
        "risk_reward": 1.25,
        "spread_cost": 0.0,
        "slippage_estimate": 0.1,
        "reason": reason,
    }


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("score 58.0 below 60.0", "score_low"),
        ("score gap 2.0 below 4.0", "score_gap_low"),
        ("ADX 12.0 below 14.0", "trend_weak"),
        ("BUY setup not confirmed", "setup_unconfirmed"),
        ("SELL quality guard blocked", "quality_guard"),
        ("RR 1.10 below 1.20", "rr_low"),
        ("spread cost 0.60 above 0.50", "spread_slippage"),
        ("slippage estimate 0.60 above 0.50", "spread_slippage"),
        ("session blocked: ASIA", "session_blocked"),
        ("max trades per day reached (2)", "daily_limit"),
        ("max open positions reached (1)", "daily_limit"),
        ("mtf_direction_filter_blocked", "mtf_misaligned"),
        ("candidate_stale", "freshness_time"),
        ("candidate_time_in_future", "freshness_time"),
        ("duplicate V51 signal/candle already traded: X", "duplicate"),
        ("V51 no directional score candidate", "no_directional_score"),
        ("V51 demo intraday signal accepted", "accepted"),
        ("something unexpected", "other"),
        ("", "other"),
        (None, "other"),
    ],
)
def test_categorize_rejection_reason(reason, expected):
    assert taxonomy.categorize_rejection_reason(reason) == expected


def test_score_gap_takes_priority_over_score():
    assert taxonomy.categorize_rejection_reason("score gap 2.0 below 4.0") == "score_gap_low"


def test_disposition_mapping():
    assert taxonomy.rejection_disposition("rr_low") == "safety_critical"
    assert taxonomy.rejection_disposition("quality_guard") == "review_candidate"
    assert taxonomy.rejection_disposition("score_low") == "threshold"
    assert taxonomy.rejection_disposition("accepted") == "informational"


def test_classify_decision_log_keeps_only_candidates_and_tags_accepted():
    classified = taxonomy.classify_decision_log(sample_decision_log())

    # The NO_TRADE/no-direction row is dropped (6 BUY/SELL candidates remain).
    assert len(classified) == 6
    assert set(classified["side"]) == {"BUY", "SELL"}
    accepted = classified[classified["rejection_category"] == "accepted"]
    assert len(accepted) == 1
    assert accepted.iloc[0]["disposition"] == "informational"


def test_build_rejection_taxonomy_counts_and_shares():
    summary = taxonomy.build_rejection_taxonomy(sample_decision_log())

    categories = set(summary["rejection_category"])
    assert {"accepted", "score_low", "score_gap_low", "session_blocked", "quality_guard", "rr_low"} <= categories
    assert int(summary["count"].sum()) == 6
    assert abs(float(summary["share_pct"].sum()) - 100.0) < 0.5
    assert taxonomy.top_blocking_category(summary) != "accepted"


def test_build_rejection_taxonomy_empty_input():
    assert taxonomy.build_rejection_taxonomy(pd.DataFrame()).empty


def test_script_generates_report(tmp_path, monkeypatch):
    csv_path = tmp_path / "xauusd.csv"
    csv_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "load_v51_config", lambda *_a, **_k: _fake_config())
    monkeypatch.setattr(diagnostics, "load_csv_data", lambda *_a, **_k: _fake_loaded_frame())
    monkeypatch.setattr(diagnostics, "build_demo_intraday_decision_log", lambda *_a, **_k: sample_decision_log())

    result = diagnostics.run_v51_rejection_diagnostics(csv_path=csv_path, output_dir=tmp_path / "diag", candles=200)

    assert result.status == "OK"
    assert result.summary_path.exists()
    assert result.latest_path.exists()
    summary = pd.read_csv(result.summary_path)
    assert int(summary["count"].sum()) == 6
    text = result.latest_path.read_text(encoding="utf-8")
    assert "Top blocking category" in text
    assert "No orders were sent" in text


def test_script_handles_missing_csv(tmp_path):
    result = diagnostics.run_v51_rejection_diagnostics(csv_path=tmp_path / "missing.csv", output_dir=tmp_path / "diag")

    assert result.status == "ERROR"
    assert result.summary_path.exists()


def test_script_classifies_existing_reasons_csv(tmp_path):
    reasons_csv = tmp_path / "log.csv"
    pd.DataFrame(
        [
            {"side": "BUY", "decision": "REJECTED", "session": "LONDON", "reason": "mtf_direction_filter_blocked"},
            {"side": "SELL", "decision": "REJECTED", "session": "NEW YORK", "reason": "candidate_stale"},
        ]
    ).to_csv(reasons_csv, index=False)

    result = diagnostics.run_v51_rejection_diagnostics(reasons_csv=reasons_csv, output_dir=tmp_path / "diag")

    assert result.status == "OK"
    summary = pd.read_csv(result.summary_path)
    assert set(summary["rejection_category"]) == {"mtf_misaligned", "freshness_time"}


def test_script_does_not_execute_orders():
    source = Path("scripts/run_v51_rejection_diagnostics.py").read_text(encoding="utf-8")

    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "v51_demo_executor" not in source


def _fake_config():
    class _Cfg:
        warmup_candles = 0

    return _Cfg()


def _fake_loaded_frame() -> pd.DataFrame:
    index = pd.date_range("2026-05-20", periods=5, freq="15min")
    return pd.DataFrame({"Close": [2400.0] * 5}, index=index)
