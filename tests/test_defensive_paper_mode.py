import pandas as pd

from scripts import select_defensive_paper_mode as script
from src.paper import paper_degradation as degradation


def make_monitor_summary(pf_50: float = 1.04, dd: float = 10.0, current_losses: int = 0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "profit_factor_last_50": pf_50,
                "max_drawdown_pct": dd,
                "current_consecutive_losses": current_losses,
                "max_consecutive_losses": 10,
            }
        ]
    )


def test_defensive_mode_selects_defensive_for_warning_state():
    report = degradation.build_defensive_mode_report(make_monitor_summary())
    row = report.iloc[0]

    assert set(degradation.DEFENSIVE_MODE_COLUMNS).issubset(report.columns)
    assert row["recommended_mode"] == "DEFENSIVE"
    assert row["recommended_strategy"] == "proxy_hardened_no_worst_hours_high_margin"
    assert row["paper_trade_allowed"] is True or row["paper_trade_allowed"] == 1
    assert row["allow_live"] is False or row["allow_live"] == 0


def test_defensive_mode_selects_pause_for_stop_state():
    report = degradation.build_defensive_mode_report(make_monitor_summary(pf_50=0.95, dd=13.0, current_losses=11))
    row = report.iloc[0]

    assert row["recommended_mode"] == "PAUSE"
    assert row["recommended_strategy"] == "none"
    assert row["paper_trade_allowed"] is False or row["paper_trade_allowed"] == 0


def test_defensive_mode_script_exports(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "defensive.csv"

    monkeypatch.setattr(script, "DEFAULT_DEFENSIVE_MODE_PATH", output_path)
    monkeypatch.setattr(script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(script, "load_or_build_monitor_summary", lambda _reports: make_monitor_summary())

    script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "Defensive Paper Mode" in output
    assert "Recommended mode: DEFENSIVE" in output
    assert "No configuration was changed" in output


def test_defensive_mode_sources_are_research_only():
    source = open("scripts/select_defensive_paper_mode.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
