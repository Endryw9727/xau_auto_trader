from pathlib import Path

import pandas as pd

from scripts import analyze_v50_candidate_edges
from src.strategy_lab.strategy_v50_candidates import V50_CANDIDATE_STRATEGY_NAMES


def make_candidate_trades() -> pd.DataFrame:
    rows = []
    for index, strategy_name in enumerate(V50_CANDIDATE_STRATEGY_NAMES):
        rows.extend(
            [
                {
                    "strategy_name": strategy_name,
                    "entry_time": f"2025-01-{index + 1:02d} 10:00:00",
                    "exit_time": f"2025-01-{index + 1:02d} 11:00:00",
                    "side": "BUY",
                    "pnl": 12.0 + index,
                    "bars_in_trade": 4,
                    "session": "LONDON",
                    "score_long": 80.0,
                    "score_short": 20.0,
                    "signal_reason": "test win",
                },
                {
                    "strategy_name": strategy_name,
                    "entry_time": f"2025-02-{index + 1:02d} 14:00:00",
                    "exit_time": f"2025-02-{index + 1:02d} 15:00:00",
                    "side": "SELL",
                    "pnl": -5.0,
                    "bars_in_trade": 3,
                    "session": "NEW YORK",
                    "score_long": 25.0,
                    "score_short": 75.0,
                    "signal_reason": "test loss",
                },
            ]
        )
    return pd.DataFrame(rows)


def make_candidate_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": list(V50_CANDIDATE_STRATEGY_NAMES),
            "profit_factor": [1.1, 1.2, 1.3, 1.4],
            "net_profit": [10.0, 20.0, 30.0, 40.0],
            "max_drawdown": [5.0, 6.0, 7.0, 8.0],
            "expectancy": [0.5, 0.6, 0.7, 0.8],
        }
    )


def test_v50_candidate_edges_report_contains_required_sections_and_strategies():
    report = analyze_v50_candidate_edges.build_v50_candidate_edges_report(
        make_candidate_trades(),
        make_candidate_comparison(),
    )

    assert set(report["strategy_name"]) == set(V50_CANDIDATE_STRATEGY_NAMES)
    assert {"overall", "side", "session", "year", "month"}.issubset(set(report["section"]))
    assert {
        "total_trades",
        "win_rate",
        "profit_factor",
        "net_profit",
        "profit_drawdown_ratio",
        "max_consecutive_losses",
    }.issubset(report.columns)


def test_v50_candidate_edges_script_runs_and_exports_csv(tmp_path, monkeypatch, capsys):
    trades_path = tmp_path / "trades_by_strategy.csv"
    comparison_path = tmp_path / "strategy_comparison.csv"
    edges_path = tmp_path / "v50_candidate_edges.csv"
    candidate_comparison_path = tmp_path / "v50_candidate_comparison.csv"
    make_candidate_trades().to_csv(trades_path, index=False)
    make_candidate_comparison().to_csv(comparison_path, index=False)

    monkeypatch.setattr(analyze_v50_candidate_edges, "TRADES_BY_STRATEGY_PATH", trades_path)
    monkeypatch.setattr(analyze_v50_candidate_edges, "TRADES_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(analyze_v50_candidate_edges, "STRATEGY_COMPARISON_PATH", comparison_path)
    monkeypatch.setattr(analyze_v50_candidate_edges, "V50_CANDIDATE_EDGES_PATH", edges_path)
    monkeypatch.setattr(
        analyze_v50_candidate_edges,
        "V50_CANDIDATE_COMPARISON_PATH",
        candidate_comparison_path,
    )

    analyze_v50_candidate_edges.main()
    output = capsys.readouterr().out
    exported = pd.read_csv(edges_path)

    assert "V50 Candidate Edges" in output
    assert "No strategy was promoted automatically." in output
    assert edges_path.exists()
    assert candidate_comparison_path.exists()
    assert set(exported["strategy_name"]) == set(V50_CANDIDATE_STRATEGY_NAMES)


def test_v50_candidate_edges_script_is_research_only_without_broker_or_api_references():
    source = Path("scripts/analyze_v50_candidate_edges.py").read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
