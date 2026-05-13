import pandas as pd

from scripts import run_dynamic_defensive_paper_simulation as run_script
from scripts import analyze_dynamic_defensive_selection as analyze_script
from src.paper import defensive_mode_engine as engine
from tests.test_defensive_mode_engine import make_config


def make_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": engine.VARIANT_MAIN_ALWAYS,
                "total_trades": 100,
                "trades_per_day": 0.6,
                "profit_factor_net": 1.2,
                "ending_equity": 1200.0,
                "max_drawdown_pct": 10.0,
                "max_drawdown_eur": 100.0,
                "win_rate": 40.0,
                "expectancy": 2.0,
                "max_consecutive_losses": 10,
                "profit_factor_last_30": 1.0,
                "profit_factor_last_50": 1.04,
                "profit_factor_last_100": 1.2,
                "months_positive": 8,
                "months_negative": 4,
                "worst_month": -50.0,
                "worst_week": -20.0,
                "worst_day": -10.0,
                "days_in_normal": 100,
                "days_in_defensive": 0,
                "days_in_pause": 0,
                "trades_avoided_by_defensive": 0,
                "trades_avoided_by_pause": 0,
                "trades_avoided_by_research_filter": 0,
                "allow_live": False,
            },
            {
                "variant_name": engine.VARIANT_HIGH_MARGIN_ALWAYS,
                "total_trades": 80,
                "trades_per_day": 0.5,
                "profit_factor_net": 1.3,
                "ending_equity": 1180.0,
                "max_drawdown_pct": 7.0,
                "max_drawdown_eur": 70.0,
                "win_rate": 42.0,
                "expectancy": 2.2,
                "max_consecutive_losses": 9,
                "profit_factor_last_30": 1.4,
                "profit_factor_last_50": 1.5,
                "profit_factor_last_100": 1.3,
                "months_positive": 8,
                "months_negative": 4,
                "worst_month": -30.0,
                "worst_week": -10.0,
                "worst_day": -5.0,
                "days_in_normal": 0,
                "days_in_defensive": 80,
                "days_in_pause": 0,
                "trades_avoided_by_defensive": 0,
                "trades_avoided_by_pause": 0,
                "trades_avoided_by_research_filter": 0,
                "allow_live": False,
            },
            {
                "variant_name": engine.VARIANT_DYNAMIC,
                "total_trades": 90,
                "trades_per_day": 0.55,
                "profit_factor_net": 1.35,
                "ending_equity": 1250.0,
                "max_drawdown_pct": 6.5,
                "max_drawdown_eur": 65.0,
                "win_rate": 43.0,
                "expectancy": 2.7,
                "max_consecutive_losses": 8,
                "profit_factor_last_30": 1.3,
                "profit_factor_last_50": 1.25,
                "profit_factor_last_100": 1.35,
                "months_positive": 8,
                "months_negative": 4,
                "worst_month": -25.0,
                "worst_week": -8.0,
                "worst_day": -4.0,
                "days_in_normal": 50,
                "days_in_defensive": 40,
                "days_in_pause": 0,
                "trades_avoided_by_defensive": 10,
                "trades_avoided_by_pause": 0,
                "trades_avoided_by_research_filter": 0,
                "allow_live": False,
            },
            {
                "variant_name": engine.VARIANT_DYNAMIC_NY18,
                "total_trades": 85,
                "trades_per_day": 0.52,
                "profit_factor_net": 1.34,
                "ending_equity": 1230.0,
                "max_drawdown_pct": 6.0,
                "max_drawdown_eur": 60.0,
                "win_rate": 43.0,
                "expectancy": 2.6,
                "max_consecutive_losses": 8,
                "profit_factor_last_30": 1.3,
                "profit_factor_last_50": 1.25,
                "profit_factor_last_100": 1.34,
                "months_positive": 8,
                "months_negative": 4,
                "worst_month": -25.0,
                "worst_week": -8.0,
                "worst_day": -4.0,
                "days_in_normal": 50,
                "days_in_defensive": 40,
                "days_in_pause": 0,
                "trades_avoided_by_defensive": 10,
                "trades_avoided_by_pause": 0,
                "trades_avoided_by_research_filter": 5,
                "allow_live": False,
            },
        ]
    )


def test_run_dynamic_defensive_script_exports(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "summary.csv"
    timeline_path = tmp_path / "timeline.csv"
    audit_path = tmp_path / "audit.csv"

    monkeypatch.setattr(run_script, "DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH", summary_path)
    monkeypatch.setattr(run_script, "DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH", timeline_path)
    monkeypatch.setattr(run_script, "DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH", audit_path)
    monkeypatch.setattr(run_script, "load_paper_trading_config", lambda: make_config())
    monkeypatch.setattr(run_script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(
        run_script,
        "run_dynamic_defensive_paper_simulation",
        lambda _reports, _config: (make_summary(), pd.DataFrame({"x": [1]}), pd.DataFrame({"x": [1]})),
    )

    run_script.main()
    output = capsys.readouterr().out

    assert summary_path.exists()
    assert timeline_path.exists()
    assert audit_path.exists()
    assert "Dynamic Defensive Paper Simulation" in output
    assert "allow_live remains false" in output


def test_analyze_dynamic_defensive_selection_script(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "summary.csv"
    make_summary().to_csv(summary_path, index=False)
    monkeypatch.setattr(analyze_script, "DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH", summary_path)

    analyze_script.main()
    output = capsys.readouterr().out

    assert "Dynamic Defensive Selection" in output
    assert "Dynamic vs main" in output
    assert "allow_live remains false" in output


def test_dynamic_scripts_are_research_only():
    for path in [
        "scripts/run_dynamic_defensive_paper_simulation.py",
        "scripts/analyze_dynamic_defensive_selection.py",
    ]:
        source = open(path, encoding="utf-8").read()
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
