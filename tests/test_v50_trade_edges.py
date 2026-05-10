from pathlib import Path

import pandas as pd

from scripts import analyze_v50_trade_edges
from scripts.analyze_v50_trade_edges import TARGET_STRATEGY, build_v50_edge_report


def make_v50_trade_edges() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": [
                TARGET_STRATEGY,
                TARGET_STRATEGY,
                TARGET_STRATEGY,
                TARGET_STRATEGY,
                TARGET_STRATEGY,
                "other_strategy",
            ],
            "timestamp_open": [
                "2025-01-01 01:00:00",
                "2025-01-02 14:00:00",
                "2025-02-01 02:00:00",
                "2025-02-02 03:00:00",
                "2025-02-03 04:00:00",
                "2025-01-01 01:00:00",
            ],
            "timestamp_close": [
                "2025-01-01 02:00:00",
                "2025-01-02 15:00:00",
                "2025-02-01 03:00:00",
                "2025-02-02 04:00:00",
                "2025-02-03 05:00:00",
                "2025-01-01 02:00:00",
            ],
            "side": ["BUY", "SELL", "BUY", "BUY", "BUY", "SELL"],
            "profit_loss": [12.0, 8.0, -5.0, -6.0, -7.0, 100.0],
            "bars_in_trade": [4, 3, 5, 6, 7, 1],
            "session": ["Asia", "New York", "Asia", "Asia", "Asia", "Asia"],
            "signal_reason": ["test"] * 6,
        }
    )


def test_v50_edge_report_builds_required_tables():
    report = build_v50_edge_report(make_v50_trade_edges())

    assert len(report["trades"]) == 5
    assert not report["by_side"].empty
    assert not report["by_session"].empty
    assert not report["by_year"].empty
    assert not report["by_month"].empty
    assert len(report["worst_trades"]) == 5
    assert len(report["best_trades"]) == 5
    assert not report["loss_clusters"].empty
    assert report["loss_clusters"].iloc[0]["loss_count"] == 3
    assert report["observations"]


def test_v50_trade_edges_script_runs_with_strategy_tagged_report(tmp_path, monkeypatch, capsys):
    trades_path = tmp_path / "trades_by_strategy.csv"
    make_v50_trade_edges().to_csv(trades_path, index=False)

    monkeypatch.setattr(analyze_v50_trade_edges, "TRADES_BY_STRATEGY_PATH", trades_path)
    monkeypatch.setattr(analyze_v50_trade_edges, "TRADES_PATH", tmp_path / "missing.csv")

    analyze_v50_trade_edges.main()
    output = capsys.readouterr().out

    assert "V50 Trade Edges" in output
    assert TARGET_STRATEGY in output
    assert "Performance LONG vs SHORT" in output
    assert "No strategy was promoted automatically." in output


def test_v50_trade_edges_without_broker_or_api_references():
    source = Path("scripts/analyze_v50_trade_edges.py").read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
