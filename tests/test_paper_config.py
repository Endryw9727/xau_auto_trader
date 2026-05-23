from pathlib import Path

import pytest

from src.paper.paper_engine import load_paper_trading_config


def test_paper_trading_config_is_research_safe():
    config = load_paper_trading_config("config/paper_trading.yaml")

    assert config.strategy_name == "proxy_hardened_no_worst_hours"
    assert config.backup_strategy == "proxy_hardened_no_worst_hours_high_margin"
    assert config.symbol == "XAUUSD-P"
    assert config.base_timeframe == "15m"
    assert config.live_mode is False
    assert config.paper_mode is True
    assert config.initial_equity == 1000
    assert config.min_lot == 0.01
    assert config.lot_step == 0.01
    assert config.equity_step == 1000
    assert config.max_lot == 0.10
    assert config.commission_per_001_lot_per_side == 0.04
    assert config.spread_pips == 0.0
    assert config.slippage_pips == 0.0
    assert config.conservative_slippage_pips == 0.1
    assert config.max_trades_per_day == 2
    assert config.max_daily_loss_pct == 3.0
    assert config.max_consecutive_losses_day == 2
    assert config.max_consecutive_losses_total_warning == 8
    assert config.max_drawdown_warning_pct == 8
    assert config.max_drawdown_stop_pct == 12
    assert config.min_score_required == 72.0
    assert config.no_trade_after_daily_stop is True


def test_paper_config_rejects_live_mode(tmp_path):
    path = tmp_path / "paper_trading.yaml"
    path.write_text(
        """
strategy_name: proxy_hardened_no_worst_hours
backup_strategy: proxy_hardened_no_worst_hours_high_margin
symbol: XAUUSD
base_timeframe: 15m
live_mode: true
paper_mode: true
initial_equity: 1000
min_lot: 0.01
lot_step: 0.01
equity_step: 1000
max_lot: 0.10
commission_per_001_lot_per_side: 0.04
spread_pips: 0.0
slippage_pips: 0.0
conservative_slippage_pips: 0.1
max_trades_per_day: 2
max_daily_loss_pct: 3.0
max_consecutive_losses_day: 2
max_consecutive_losses_total_warning: 8
max_drawdown_warning_pct: 8
max_drawdown_stop_pct: 12
min_score_required: 72.0
no_trade_after_daily_stop: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="live_mode=false"):
        load_paper_trading_config(path)


def test_paper_config_does_not_reference_live_execution():
    source = Path("config/paper_trading.yaml").read_text(encoding="utf-8")
    assert "api_key" not in source.lower()
    assert ".env" not in source
    assert "live_mode: false" in source
