from pathlib import Path

import pandas as pd

from scripts import analyze_v50_proxy_hardening_selection as selection


def make_sweep() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": "proxy_hardened_base",
                "total_trades": 1090,
                "average_trades_per_day": 0.828,
                "profit_factor": 1.255,
                "net_profit": 1272.0,
                "max_drawdown": 133.0,
                "profit_drawdown_ratio": 9.5,
                "max_consecutive_losses": 10,
                "anti_overfit_pass": False,
                "leakage_safe": True,
                "stress_medium_profit_factor": 1.14,
                "probability_drawdown_over_20_percent": 32.4,
            },
            {
                "variant_name": "proxy_hardened_balanced",
                "total_trades": 900,
                "average_trades_per_day": 0.80,
                "profit_factor": 1.30,
                "net_profit": 1100.0,
                "max_drawdown": 120.0,
                "profit_drawdown_ratio": 9.1,
                "max_consecutive_losses": 9,
                "anti_overfit_pass": True,
                "leakage_safe": True,
                "stress_medium_profit_factor": 1.22,
                "probability_drawdown_over_20_percent": 20.0,
            },
        ]
    )


def make_stress() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"variant_name": "proxy_hardened_base", "scenario": "spread_slippage_medium", "profit_factor": 1.14},
            {"variant_name": "proxy_hardened_balanced", "scenario": "spread_slippage_medium", "profit_factor": 1.22},
        ]
    )


def make_monte_carlo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_base",
                "probability_drawdown_over_20_percent": 32.4,
                "median_max_drawdown": 178.0,
            },
            {
                "strategy_name": "proxy_hardened_balanced",
                "probability_drawdown_over_20_percent": 20.0,
                "median_max_drawdown": 150.0,
            },
        ]
    )


def test_hardening_selection_helpers_find_viable_variant():
    ranking = selection.prepare_hardening_ranking(make_sweep())

    assert selection.select_best_profit_factor(ranking)["variant_name"] == "proxy_hardened_balanced"
    assert selection.select_best_medium_stress(ranking, make_stress())["variant_name"] == "proxy_hardened_balanced"
    assert selection.select_best_monte_carlo(ranking, make_monte_carlo())["variant_name"] == "proxy_hardened_balanced"
    assert selection.exists_pf_and_medium_stress(ranking, make_stress())
    assert selection.exists_low_dd_and_mc_better(ranking, make_monte_carlo())
    assert "proxy_hardened_balanced" in selection.build_hardening_recommendation(
        ranking,
        make_stress(),
        make_monte_carlo(),
    )


def test_hardening_selection_script_runs(monkeypatch, tmp_path, capsys):
    sweep_path = tmp_path / "sweep.csv"
    stress_path = tmp_path / "stress.csv"
    mc_path = tmp_path / "mc.csv"
    make_sweep().to_csv(sweep_path, index=False)
    make_stress().to_csv(stress_path, index=False)
    make_monte_carlo().to_csv(mc_path, index=False)

    monkeypatch.setattr(selection, "DEFAULT_PROXY_HARDENING_SWEEP_PATH", sweep_path)
    monkeypatch.setattr(selection, "DEFAULT_PROXY_HARDENING_STRESS_PATH", stress_path)
    monkeypatch.setattr(selection, "DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH", mc_path)

    selection.main()
    output = capsys.readouterr().out

    assert "V50 Proxy Hardening Selection" in output
    assert "PF full >= 1.23 and stress medium >= 1.20: True" in output
    assert "No candidate was promoted automatically." in output


def test_proxy_hardening_selection_sources_are_research_only():
    path = Path("scripts/analyze_v50_proxy_hardening_selection.py")
    source = path.read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
