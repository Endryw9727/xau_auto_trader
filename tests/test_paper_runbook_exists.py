from pathlib import Path


def test_paper_runbook_exists_and_documents_final_candidate():
    path = Path("docs/paper_trading_runbook.md")
    content = path.read_text(encoding="utf-8")

    assert path.exists()
    assert "proxy_hardened_no_worst_hours_high_margin" in content
    assert "dynamic_normal_defensive_pause" in content
    assert "allow_live" in content
    assert "false" in content
    assert "LIVE_MODE=false" in content
    assert "python scripts/paper_preflight_check.py" in content
    assert "python scripts/paper_end_of_day_report.py" in content
