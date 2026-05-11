from pathlib import Path

import pandas as pd

from scripts import analyze_v50_loss_intelligence as loss_script
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_loss_intelligence import (
    LOSS_BREAKDOWN_COLUMNS,
    LOSS_CLUSTER_COLUMNS,
    PATTERN_CANDIDATE_COLUMNS,
    build_loss_breakdown,
    build_loss_clusters,
    build_loss_pattern_candidates,
    prepare_balanced_loss_trades,
)


def make_trades() -> pd.DataFrame:
    pnl = [10.0, -5.0, -6.0, 12.0, -4.0, -3.0, -2.0, 14.0, -5.0, 11.0]
    return pd.DataFrame(
        {
            "strategy_name": [FINAL_BALANCED_STRATEGY_NAME] * len(pnl),
            "entry_time": pd.date_range("2025-01-01 09:00:00", periods=len(pnl), freq="6h"),
            "side": ["BUY", "SELL", "SELL", "BUY", "BUY", "SELL", "SELL", "BUY", "SELL", "BUY"],
            "side_label": ["LONG", "SHORT", "SHORT", "LONG", "LONG", "SHORT", "SHORT", "LONG", "SHORT", "LONG"],
            "session": ["LONDON", "LONDON", "NEW YORK", "LONDON", "ASIA", "LONDON", "LONDON", "NEW YORK", "ASIA", "LONDON"],
            "pnl": pnl,
            "profit_loss": pnl,
            "score_long": [82, 30, 25, 88, 74, 40, 30, 90, 20, 86],
            "score_short": [20, 78, 76, 25, 35, 72, 68, 25, 70, 30],
            "bars_in_trade": [4, 8, 9, 3, 1, 15, 16, 4, 2, 5],
            "signal_reason": ["V50 test"] * len(pnl),
        }
    )


def make_market_data() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0],
            "High": [105.0, 103.0, 108.0, 106.0],
            "Low": [99.0, 100.0, 101.0, 102.0],
            "Close": [104.0, 102.0, 107.0, 105.0],
            "Volume": [1.0] * 4,
        },
        index=dates,
    )


def test_loss_intelligence_builds_clusters_breakdown_and_candidates():
    prepared = prepare_balanced_loss_trades(make_trades())
    clusters = build_loss_clusters(prepared)
    breakdown = build_loss_breakdown(prepared)
    candidates = build_loss_pattern_candidates(prepared, breakdown, market_data=make_market_data(), min_trades=4)

    assert set(LOSS_CLUSTER_COLUMNS).issubset(clusters.columns)
    assert set(LOSS_BREAKDOWN_COLUMNS).issubset(breakdown.columns)
    assert set(PATTERN_CANDIDATE_COLUMNS).issubset(candidates.columns)
    assert clusters["loss_count"].max() >= 2
    assert {"hour", "weekday", "session_side", "score_bucket", "bars_in_trade_bucket"}.issubset(
        set(breakdown["pattern_type"])
    )


def test_loss_intelligence_script_runs_and_exports(monkeypatch, tmp_path, capsys):
    clusters_path = tmp_path / "clusters.csv"
    breakdown_path = tmp_path / "breakdown.csv"
    candidates_path = tmp_path / "candidates.csv"

    monkeypatch.setattr(loss_script, "DEFAULT_LOSS_CLUSTERS_PATH", clusters_path)
    monkeypatch.setattr(loss_script, "DEFAULT_LOSS_BREAKDOWN_PATH", breakdown_path)
    monkeypatch.setattr(loss_script, "DEFAULT_LOSS_PATTERN_CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(loss_script, "load_loss_trade_report", lambda: make_trades())
    monkeypatch.setattr(loss_script, "_load_market_data", lambda: make_market_data())

    loss_script.main()
    output = capsys.readouterr().out

    assert clusters_path.exists()
    assert breakdown_path.exists()
    assert candidates_path.exists()
    assert "V50 Loss Intelligence" in output
    assert "No strategy was promoted automatically." in output


def test_v50_loss_intelligence_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_loss_intelligence.py"),
        Path("scripts/analyze_v50_loss_intelligence.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
