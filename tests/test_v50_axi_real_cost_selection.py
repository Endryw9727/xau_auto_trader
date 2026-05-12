from pathlib import Path

import pandas as pd

from scripts import analyze_v50_axi_real_cost_selection as selection


def make_report() -> pd.DataFrame:
    rows = []
    for strategy, pf in [
        ("v50_final_balanced_strategy", 1.18),
        ("v50_proxy_balanced_candidate", 1.25),
        ("proxy_hardened_score_plus", 1.27),
    ]:
        for profile in ["axi_pro_realistic", "axi_pro_conservative", "cost_medium"]:
            profile_pf = pf if profile != "cost_medium" else 1.02
            rows.append(
                {
                    "strategy_name": strategy,
                    "cost_profile": profile,
                    "total_trades": 900,
                    "average_trades_per_day": 0.8,
                    "win_rate": 40.0,
                    "gross_profit_factor": pf + 0.01,
                    "net_profit_factor": profile_pf,
                    "gross_net_profit": 120.0,
                    "net_profit_after_costs": 100.0,
                    "total_commission": 8.0,
                    "total_spread_cost": 0.0,
                    "total_slippage_cost": 1.0,
                    "total_cost": 9.0,
                    "average_cost_per_trade": 0.09,
                    "average_trade_after_costs": 0.11,
                    "max_drawdown_after_costs": 100.0,
                    "expectancy_after_costs": 0.11,
                    "profit_drawdown_ratio_after_costs": 1.0,
                    "max_consecutive_losses": 8,
                    "positive_months": 10,
                    "negative_months": 2,
                    "average_lot": 0.01,
                    "max_lot": 0.02,
                    "commission_round_turn_per_001_lot": 0.08,
                    "profile_note": "test",
                }
            )
    return pd.DataFrame(rows)


def test_axi_real_cost_selection_helpers():
    ranking = selection.prepare_axi_real_cost_ranking(make_report())

    assert selection.best_for_profile(ranking, "axi_pro_realistic")["strategy_name"] == "proxy_hardened_score_plus"
    assert selection.row_for_strategy_profile(
        ranking,
        "v50_proxy_balanced_candidate",
        "axi_pro_realistic",
    )["net_profit_factor"] == 1.25
    assert "paper" in selection.build_axi_real_cost_recommendation(ranking).lower()


def test_axi_real_cost_selection_script_runs(monkeypatch, tmp_path, capsys):
    report_path = tmp_path / "axi.csv"
    make_report().to_csv(report_path, index=False)
    monkeypatch.setattr(selection, "DEFAULT_AXI_REAL_COST_BACKTEST_PATH", report_path)

    selection.main()
    output = capsys.readouterr().out

    assert "V50 Axi Real-Cost Selection" in output
    assert "Best axi_pro_realistic" in output
    assert "No candidate was promoted automatically." in output


def test_axi_real_cost_selection_sources_are_research_only():
    path = Path("scripts/analyze_v50_axi_real_cost_selection.py")
    source = path.read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
