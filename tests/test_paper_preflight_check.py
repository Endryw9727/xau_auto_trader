from dataclasses import replace

import pandas as pd

from scripts import paper_preflight_check as script
from src.paper.paper_candidate import load_paper_candidate_config
from src.paper.paper_engine import load_paper_trading_config


def make_monitor(status: str = "OK") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
                "status": status,
                "warning_reasons": "drawdown warning" if status == "WARNING" else "",
                "stop_reasons": "stop reason" if status == "STOP" else "",
            }
        ]
    )


def test_run_preflight_checks_passes_with_safe_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("trading:\n  live_mode: false\n", encoding="utf-8")
    reports_dir = tmp_path / "paper"
    reports_dir.mkdir()

    monkeypatch.setattr(script, "CONFIG_PATH", config_path)
    monkeypatch.setattr(script, "DEFAULT_PAPER_OUTPUT_DIR", reports_dir)
    monkeypatch.setenv("LIVE_MODE", "false")
    monkeypatch.setattr(script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(script, "build_monitor_summary", lambda _reports, strategy_name: make_monitor("OK"))

    checks = script.run_preflight_checks()

    assert all(item["passed"] for item in checks)


def test_run_preflight_checks_fails_on_stop_monitor(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("trading:\n  live_mode: false\n", encoding="utf-8")
    reports_dir = tmp_path / "paper"
    reports_dir.mkdir()

    monkeypatch.setattr(script, "CONFIG_PATH", config_path)
    monkeypatch.setattr(script, "DEFAULT_PAPER_OUTPUT_DIR", reports_dir)
    monkeypatch.setattr(script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(script, "build_monitor_summary", lambda _reports, strategy_name: make_monitor("STOP"))

    checks = script.run_preflight_checks()

    monitor_check = next(item for item in checks if item["name"] == "monitor_status")
    assert monitor_check["passed"] is False


def test_paper_preflight_script_prints(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {"name": "live_mode_false", "passed": True, "detail": "ok"},
            {"name": "monitor_status", "passed": True, "detail": "WARNING: watch"},
        ],
    )

    script.main()
    output = capsys.readouterr().out

    assert "Paper Preflight Check" in output
    assert "Preflight status: PASS" in output
    assert "allow_live remains false" in output


def test_paper_preflight_sources_are_research_only():
    source = open("scripts/paper_preflight_check.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
