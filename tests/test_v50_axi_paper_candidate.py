from pathlib import Path

import pandas as pd

from scripts import analyze_v50_axi_paper_candidate as analysis


def make_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_score_plus",
                "scenario": "axi_realistic_slippage_0_0",
                "starting_equity": 1000.0,
                "ending_equity": 1400.0,
                "net_profit_eur": 400.0,
                "max_drawdown_eur": 80.0,
                "max_drawdown_percent": 7.0,
                "total_trades": 900,
                "trades_per_day": 0.8,
                "win_rate": 40.0,
                "profit_factor_net": 1.3,
                "average_trade_eur": 0.44,
                "average_win_eur": 3.0,
                "average_loss_eur": -1.2,
                "max_consecutive_losses": 8,
                "worst_day": -10.0,
                "worst_week": -25.0,
                "worst_month": -50.0,
                "best_month": 120.0,
                "months_positive": 10,
                "months_negative": 2,
                "time_to_2000_if_reached": pd.NA,
                "trades_to_2000_if_reached": pd.NA,
                "equity_min": 980.0,
                "equity_max": 1400.0,
                "lot_min": 0.01,
                "lot_max": 0.01,
            },
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "scenario": "axi_realistic_slippage_0_0",
                "starting_equity": 1000.0,
                "ending_equity": 1350.0,
                "net_profit_eur": 350.0,
                "max_drawdown_eur": 70.0,
                "max_drawdown_percent": 6.5,
                "total_trades": 800,
                "trades_per_day": 0.7,
                "win_rate": 40.0,
                "profit_factor_net": 1.25,
                "average_trade_eur": 0.44,
                "average_win_eur": 3.0,
                "average_loss_eur": -1.2,
                "max_consecutive_losses": 8,
                "worst_day": -10.0,
                "worst_week": -25.0,
                "worst_month": -50.0,
                "best_month": 120.0,
                "months_positive": 10,
                "months_negative": 2,
                "time_to_2000_if_reached": pd.NA,
                "trades_to_2000_if_reached": pd.NA,
                "equity_min": 980.0,
                "equity_max": 1350.0,
                "lot_min": 0.01,
                "lot_max": 0.01,
            },
        ]
    )


def test_paper_candidate_helpers_choose_candidate():
    ranking = analysis.prepare_paper_candidate_ranking(make_summary())
    best = analysis.best_paper_candidate(ranking)

    assert best["strategy_name"] == "proxy_hardened_score_plus"
    assert analysis.is_drawdown_acceptable(best)
    assert "Paper trading: yes" in analysis.build_paper_recommendation(best)


def test_paper_candidate_script_runs(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "summary.csv"
    monthly_path = tmp_path / "monthly.csv"
    make_summary().to_csv(summary_path, index=False)
    pd.DataFrame({"month": ["2025-01"]}).to_csv(monthly_path, index=False)

    monkeypatch.setattr(analysis, "DEFAULT_AXI_EQUITY_SIMULATION_PATH", summary_path)
    monkeypatch.setattr(analysis, "DEFAULT_AXI_MONTHLY_EQUITY_PATH", monthly_path)

    analysis.main()
    output = capsys.readouterr().out

    assert "V50 Axi Paper Candidate" in output
    assert "Best paper candidate" in output
    assert "No candidate was promoted automatically." in output


def test_paper_candidate_sources_are_research_only():
    path = Path("scripts/analyze_v50_axi_paper_candidate.py")
    source = path.read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
