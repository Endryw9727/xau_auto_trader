from pathlib import Path

import pytest

from src.paper.paper_candidate import PaperCandidateConfig
from src.paper.paper_engine import PaperTradingConfig
from src.paper.paper_forward_engine import validate_forward_safety


def make_candidate_config() -> PaperCandidateConfig:
    return PaperCandidateConfig(
        paper_main_strategy="proxy_hardened_no_worst_hours_high_margin",
        research_strategy="proxy_hardened_no_worst_hours",
        emergency_mode="dynamic_normal_defensive_pause",
        allow_live=False,
        paper_mode=True,
        max_trades_per_day=2,
        max_daily_loss_pct=3.0,
        max_weekly_loss_pct=8.0,
        warning_drawdown_pct=8.0,
        stop_drawdown_pct=12.0,
        min_recent_50_pf_warning=1.05,
        min_recent_50_pf_stop=1.00,
        min_trade_day_required=0.50,
    )


def make_paper_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        strategy_name="proxy_hardened_no_worst_hours",
        backup_strategy="proxy_hardened_no_worst_hours_high_margin",
        symbol="XAUUSD",
        base_timeframe="15m",
        live_mode=False,
        paper_mode=True,
        initial_equity=1000.0,
        min_lot=0.01,
        lot_step=0.01,
        equity_step=1000.0,
        max_lot=0.10,
        commission_per_001_lot_per_side=0.04,
        spread_pips=0.0,
        slippage_pips=0.0,
        conservative_slippage_pips=0.1,
        max_trades_per_day=2,
        max_daily_loss_pct=3.0,
        max_consecutive_losses_day=2,
        max_consecutive_losses_total_warning=8,
        max_drawdown_warning_pct=8.0,
        max_drawdown_stop_pct=12.0,
        min_score_required=72.0,
        no_trade_after_daily_stop=True,
    )


def test_paper_forward_sources_do_not_use_live_broker():
    for path in [
        "src/paper/paper_forward_engine.py",
        "scripts/run_paper_forward_once.py",
        "scripts/paper_forward_status.py",
    ]:
        source = Path(path).read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "place_order" not in source
        assert "broker API" not in source


def test_forward_safety_rejects_live_mode():
    candidate = make_candidate_config()
    paper_config = make_paper_config()
    unsafe = paper_config.__class__(**{**paper_config.__dict__, "live_mode": True})

    with pytest.raises(ValueError, match="live_mode"):
        validate_forward_safety(candidate, unsafe)


def test_forward_safety_keeps_allow_live_false():
    candidate = make_candidate_config()
    unsafe_candidate = candidate.__class__(**{**candidate.__dict__, "allow_live": True})

    with pytest.raises(ValueError, match="allow_live"):
        validate_forward_safety(unsafe_candidate, make_paper_config())
