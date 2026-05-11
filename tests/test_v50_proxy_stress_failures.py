from pathlib import Path

import pandas as pd

from scripts import analyze_v50_proxy_stress_failures as script
from src.strategy_lab.v50_proxy_hardening import (
    FAILURE_ANALYSIS_COLUMNS,
    build_proxy_stress_failure_analysis,
)


def make_stress() -> pd.DataFrame:
    rows = []
    for strategy_name in [
        "v50_final_balanced_strategy",
        "v50_proxy_balanced_candidate",
        "v50_final_low_risk_strategy",
        "v50_final_growth_strategy",
    ]:
        rows.append(
            {
                "strategy_name": strategy_name,
                "scenario": "base",
                "total_trades": 1000,
                "profit_factor": 1.25,
                "net_profit": 1000.0,
                "max_drawdown": 120.0,
            }
        )
        rows.append(
            {
                "strategy_name": strategy_name,
                "scenario": "spread_slippage_medium",
                "total_trades": 1000,
                "profit_factor": 1.14 if strategy_name == "v50_proxy_balanced_candidate" else 1.09,
                "net_profit": 500.0,
                "max_drawdown": 220.0,
            }
        )
    return pd.DataFrame(rows)


def make_monte_carlo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "v50_proxy_balanced_candidate",
                "median_max_drawdown": 178.0,
                "probability_drawdown_over_20_percent": 32.4,
            }
        ]
    )


def test_proxy_stress_failure_analysis_flags_pf_below_threshold():
    report = build_proxy_stress_failure_analysis(make_stress(), make_monte_carlo(), pd.DataFrame({"x": [1]}))
    proxy_medium = report[
        (report["strategy_name"] == "v50_proxy_balanced_candidate")
        & (report["scenario"] == "spread_slippage_medium")
    ].iloc[0]

    assert list(report.columns) == FAILURE_ANALYSIS_COLUMNS
    assert bool(proxy_medium["pf_below_1_20"]) is True
    assert proxy_medium["net_profit_delta_vs_base"] == -500.0
    assert proxy_medium["max_drawdown_delta_vs_base"] == 100.0


def test_proxy_stress_failure_script_runs_and_exports(monkeypatch, tmp_path, capsys):
    stress_path = tmp_path / "v50_stress_test.csv"
    monte_path = tmp_path / "v50_monte_carlo.csv"
    comparison_path = tmp_path / "strategy_comparison.csv"
    output_path = tmp_path / "failure.csv"
    make_stress().to_csv(stress_path, index=False)
    make_monte_carlo().to_csv(monte_path, index=False)
    pd.DataFrame({"strategy_name": ["v50_proxy_balanced_candidate"]}).to_csv(comparison_path, index=False)

    monkeypatch.setattr(script, "DEFAULT_V50_STRESS_TEST_PATH", stress_path)
    monkeypatch.setattr(script, "DEFAULT_V50_MONTE_CARLO_PATH", monte_path)
    monkeypatch.setattr(script, "STRATEGY_COMPARISON_PATH", comparison_path)
    monkeypatch.setattr(script, "DEFAULT_PROXY_STRESS_FAILURE_ANALYSIS_PATH", output_path)

    script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Proxy Stress Failures" in output
    assert "No candidate was promoted automatically." in output


def test_proxy_stress_failure_sources_are_research_only():
    for path in [
        Path("scripts/analyze_v50_proxy_stress_failures.py"),
        Path("src/strategy_lab/v50_proxy_hardening.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
