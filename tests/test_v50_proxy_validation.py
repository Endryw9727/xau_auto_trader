from pathlib import Path

import pandas as pd

from scripts import analyze_v50_proxy_candidate_selection as selection
from src.strategy_lab.strategy_v50_candidates import (
    FINAL_BALANCED_STRATEGY_NAME,
    FINAL_GROWTH_STRATEGY_NAME,
    FINAL_LOW_RISK_STRATEGY_NAME,
)
from src.strategy_lab.strategy_v50_proxy_candidate import STRATEGY_NAME as PROXY_CANDIDATE_NAME


def make_comparison() -> pd.DataFrame:
    rows = [
        (FINAL_LOW_RISK_STRATEGY_NAME, 800, 39.0, 1.18, 700.0, 80.0, 0.88, 8.75, 9, 0.61),
        (FINAL_BALANCED_STRATEGY_NAME, 1156, 37.5, 1.20, 1012.0, 158.0, 0.88, 6.40, 11, 0.88),
        (FINAL_GROWTH_STRATEGY_NAME, 1400, 37.0, 1.10, 1200.0, 210.0, 0.86, 5.71, 13, 1.06),
        (PROXY_CANDIDATE_NAME, 1090, 38.5, 1.26, 1272.0, 133.0, 1.17, 9.56, 10, 0.83),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "strategy_name",
            "total_trades",
            "win_rate",
            "profit_factor",
            "net_profit",
            "max_drawdown",
            "expectancy",
            "profit_drawdown_ratio",
            "max_consecutive_losses",
            "average_trades_per_day",
        ],
    )


def make_stress() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": PROXY_CANDIDATE_NAME,
                "scenario": "spread_slippage_medium",
                "profit_factor": 1.21,
            }
        ]
    )


def make_monte_carlo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
                "median_max_drawdown": 200.0,
            },
            {
                "strategy_name": PROXY_CANDIDATE_NAME,
                "median_max_drawdown": 150.0,
            },
        ]
    )


def test_proxy_candidate_selection_helpers_compare_against_balanced():
    comparison = selection.prepare_strategy_comparison(make_comparison())
    balanced = comparison[comparison["strategy_name"] == FINAL_BALANCED_STRATEGY_NAME].iloc[0]
    proxy = comparison[comparison["strategy_name"] == PROXY_CANDIDATE_NAME].iloc[0]

    assert selection.proxy_beats_balanced_profit_factor(proxy, balanced)
    assert selection.proxy_beats_balanced_drawdown(proxy, balanced)
    assert selection.proxy_beats_balanced_net_profit(proxy, balanced)
    assert selection.proxy_medium_stress_pf_ok(make_stress())
    assert selection.proxy_monte_carlo_dd_20pct_better(make_monte_carlo())
    assert "paper-trading validation" in selection.build_paper_trading_recommendation(
        comparison,
        make_stress(),
        make_monte_carlo(),
    )


def test_proxy_candidate_selection_script_runs(monkeypatch, tmp_path, capsys):
    comparison_path = tmp_path / "strategy_comparison.csv"
    stress_path = tmp_path / "v50_stress_test.csv"
    monte_path = tmp_path / "v50_monte_carlo.csv"
    make_comparison().to_csv(comparison_path, index=False)
    make_stress().to_csv(stress_path, index=False)
    make_monte_carlo().to_csv(monte_path, index=False)

    monkeypatch.setattr(selection, "STRATEGY_COMPARISON_PATH", comparison_path)
    monkeypatch.setattr(selection, "DEFAULT_V50_STRESS_TEST_PATH", stress_path)
    monkeypatch.setattr(selection, "DEFAULT_V50_MONTE_CARLO_PATH", monte_path)

    selection.main()
    output = capsys.readouterr().out

    assert "V50 Proxy Candidate Selection" in output
    assert "Proxy beats balanced on PF: True" in output
    assert "No candidate was promoted automatically." in output


def test_proxy_validation_sources_are_research_only():
    checked_files = [
        Path("scripts/analyze_v50_proxy_candidate_selection.py"),
        Path("src/strategy_lab/strategy_v50_proxy_candidate.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
