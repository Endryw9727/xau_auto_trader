from pathlib import Path

import pandas as pd

from scripts import run_v51_market_structure_diagnostics as report
from src.analysis import v51_structure_context as context


def _market_data() -> pd.DataFrame:
    rows = [
        ("2026-05-20 02:00:00", 2005, 2010, 2000, 2006),  # ASIA
        ("2026-05-20 05:00:00", 2006, 2009, 2001, 2004),  # ASIA
        ("2026-05-20 11:00:00", 2004, 2005, 1990, 1992),  # LONDON sweep low
        ("2026-05-20 12:00:00", 1992, 2007, 1991, 2006),  # LONDON reclaim
        ("2026-05-20 20:00:00", 2006, 2020, 2005, 2018),  # NY up
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
                "candle_time": "2026-05-20T12:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 80.0,
                "entry_price": 2002.0,
            },
            {
                "signal_id": "V51-sell",
                "candle_time": "2026-05-20T20:00:00",
                "session": "NEW YORK",
                "side": "SELL",
                "decision": "REJECTED",
                "score": 55.0,
                "entry_price": 2018.0,
            },
            {
                "signal_id": "V51-none",
                "candle_time": "2026-05-20T05:00:00",
                "session": "ASIA",
                "side": "NO_TRADE",
                "decision": "NO_TRADE",
                "score": 0.0,
                "entry_price": None,
            },
        ]
    )


def test_annotate_aligns_long_with_sell_side_sweep():
    annotated = context.annotate_candidates_with_structure(_decision_log(), _market_data())

    assert len(annotated) == 2  # NO_TRADE row dropped
    buy = annotated[annotated["side"] == "BUY"].iloc[0]
    assert buy["manipulation_label"] == "london_sweep_low_reclaimed"
    assert buy["structure_alignment"] == "aligned"
    assert buy["sweep_side"] == "SELL_SIDE"
    assert buy["ny_direction"] == "UP"

    sell = annotated[annotated["side"] == "SELL"].iloc[0]
    assert sell["structure_alignment"] == "counter"


def test_annotate_distance_to_nearest_level():
    annotated = context.annotate_candidates_with_structure(_decision_log(), _market_data())
    buy = annotated[annotated["side"] == "BUY"].iloc[0]
    # Entry 2002 nearest to asia_low 2000 → distance 2.0, inside Asia range.
    assert buy["nearest_level_name"] == "asia_low"
    assert float(buy["distance_to_level"]) == 2.0
    assert bool(buy["in_asia_range"]) is True


def test_build_structure_context_summary_counts():
    annotated = context.annotate_candidates_with_structure(_decision_log(), _market_data())
    summary = context.build_structure_context_summary(annotated)

    assert int(summary["candidates"].sum()) == 2
    assert int(summary["accepted"].sum()) == 1
    aligned = summary[summary["structure_alignment"] == "aligned"]
    assert int(aligned["candidates"].sum()) == 1


def test_annotate_empty_inputs():
    assert context.annotate_candidates_with_structure(pd.DataFrame(), _market_data()).empty
    assert context.build_structure_context_summary(pd.DataFrame()).empty


def test_script_generates_report(tmp_path, monkeypatch):
    csv_path = tmp_path / "xauusd.csv"
    csv_path.write_text("placeholder", encoding="utf-8")

    class _Cfg:
        warmup_candles = 0

    monkeypatch.setattr(report, "load_v51_config", lambda *_a, **_k: _Cfg())
    monkeypatch.setattr(report, "load_csv_data", lambda *_a, **_k: _market_data())
    monkeypatch.setattr(report, "build_demo_intraday_decision_log", lambda *_a, **_k: _decision_log())

    result = report.run_v51_market_structure_diagnostics(csv_path=csv_path, output_dir=tmp_path / "diag", candles=200)

    assert result.status == "OK"
    assert result.context_path.exists()
    assert result.summary_path.exists()
    text = result.latest_path.read_text(encoding="utf-8")
    assert "Aligned with sweep-reclaim" in text
    assert "No orders were sent" in text


def test_script_handles_missing_csv(tmp_path):
    result = report.run_v51_market_structure_diagnostics(csv_path=tmp_path / "missing.csv", output_dir=tmp_path / "diag")
    assert result.status == "ERROR"
    assert result.context_path.exists()


def test_script_does_not_execute_orders():
    source = Path("scripts/run_v51_market_structure_diagnostics.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "v51_demo_executor" not in source
