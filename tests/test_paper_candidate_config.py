from pathlib import Path

import pytest

from src.paper.paper_candidate import (
    PAPER_EMERGENCY_MODE,
    PAPER_MAIN_STRATEGY,
    PAPER_RESEARCH_STRATEGY,
    load_paper_candidate_config,
)


def test_paper_candidate_config_freezes_high_margin_main():
    config = load_paper_candidate_config("config/paper_candidate.yaml")

    assert config.paper_main_strategy == PAPER_MAIN_STRATEGY
    assert config.research_strategy == PAPER_RESEARCH_STRATEGY
    assert config.emergency_mode == PAPER_EMERGENCY_MODE
    assert config.allow_live is False
    assert config.paper_mode is True
    assert config.max_trades_per_day == 2
    assert config.max_daily_loss_pct == 3
    assert config.max_weekly_loss_pct == 8
    assert config.warning_drawdown_pct == 8
    assert config.stop_drawdown_pct == 12
    assert config.min_recent_50_pf_warning == 1.05
    assert config.min_recent_50_pf_stop == 1.00
    assert config.min_trade_day_required == 0.50


def test_paper_candidate_rejects_allow_live_true(tmp_path):
    path = tmp_path / "paper_candidate.yaml"
    path.write_text(
        """
paper_main_strategy: proxy_hardened_no_worst_hours_high_margin
research_strategy: proxy_hardened_no_worst_hours
emergency_mode: dynamic_normal_defensive_pause
allow_live: true
paper_mode: true
max_trades_per_day: 2
max_daily_loss_pct: 3
max_weekly_loss_pct: 8
warning_drawdown_pct: 8
stop_drawdown_pct: 12
min_recent_50_pf_warning: 1.05
min_recent_50_pf_stop: 1.00
min_trade_day_required: 0.50
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allow_live"):
        load_paper_candidate_config(path)


def test_candidate_config_sources_are_research_only():
    for path in ["config/paper_candidate.yaml", "src/paper/paper_candidate.py"]:
        source = Path(path).read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
