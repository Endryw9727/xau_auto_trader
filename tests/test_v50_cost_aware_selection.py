from pathlib import Path

import pandas as pd

from scripts import analyze_v50_cost_aware_selection as selection


def make_report() -> pd.DataFrame:
    rows = []
    for profile, pf, dd, anti in [
        ("cost_none", 1.35, 120.0, True),
        ("cost_light", 1.28, 125.0, True),
        ("cost_medium", 1.22, 130.0, True),
        ("cost_heavy", 1.05, 180.0, False),
    ]:
        rows.append(
            {
                "source_variant": "v50_proxy_balanced_candidate",
                "variant_name": "costaware_balanced_combo",
                "cost_profile": profile,
                "total_trades": 900,
                "average_trades_per_day": 0.8,
                "win_rate": 40.0,
                "gross_profit_factor": 1.4,
                "net_profit_factor": pf,
                "gross_net_profit": 120.0,
                "net_profit": 100.0,
                "total_cost": 20.0,
                "average_cost_per_trade": 0.02,
                "max_drawdown": dd,
                "expectancy_net": 0.1,
                "profit_drawdown_ratio_net": 100.0 / dd,
                "max_consecutive_losses": 8,
                "positive_months": 10,
                "negative_months": 2,
                "pf_without_top_1pct": pf - 0.03,
                "pf_without_top_3pct": pf - 0.08,
                "pf_without_top_5pct": pf - 0.15,
                "pf_without_top_10pct": pf - 0.30,
                "net_profit_without_top_5pct": 70.0,
                "max_drawdown_without_top_5pct": dd + 10.0,
                "anti_overfit_pass": anti,
                "leakage_safe": True,
            }
        )
    return pd.DataFrame(rows)


def test_cost_aware_selection_helpers_choose_medium_candidate():
    ranking = selection.prepare_cost_aware_ranking(make_report())

    assert selection.best_for_profile(ranking, "cost_medium")["variant_name"] == "costaware_balanced_combo"
    assert selection.best_profit_drawdown(ranking)["cost_profile"] == "cost_medium"
    assert selection.least_top_trade_dependency(ranking)["cost_profile"] == "cost_medium"
    assert "costaware_balanced_combo" in selection.build_cost_aware_recommendation(ranking)


def test_cost_aware_selection_script_runs(monkeypatch, tmp_path, capsys):
    sweep_path = tmp_path / "sweep.csv"
    make_report().to_csv(sweep_path, index=False)

    monkeypatch.setattr(selection, "DEFAULT_COST_AWARE_SWEEP_PATH", sweep_path)
    monkeypatch.setattr(selection, "STRATEGY_COMPARISON_PATH", tmp_path / "missing.csv")

    selection.main()
    output = capsys.readouterr().out

    assert "V50 Cost-Aware Selection" in output
    assert "Best cost_medium" in output
    assert "No candidate was promoted automatically." in output


def test_cost_aware_selection_sources_are_research_only():
    path = Path("scripts/analyze_v50_cost_aware_selection.py")
    source = path.read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
