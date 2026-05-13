from pathlib import Path

import pandas as pd

from src.paper.paper_candidate import PaperCandidateConfig
from src.paper.paper_engine import PaperTradingConfig
from src.paper.paper_forward_engine import (
    CLOSED_TRADE_COLUMNS,
    ForwardSignalCandidate,
    calculate_forward_state,
    ensure_forward_files,
    load_forward_tables,
    run_paper_forward_once,
)
from src.strategy.signals import TradingSignal


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


def write_configs(tmp_path: Path) -> tuple[Path, Path]:
    candidate_path = tmp_path / "paper_candidate.yaml"
    candidate_path.write_text(
        """
paper_main_strategy: proxy_hardened_no_worst_hours_high_margin
research_strategy: proxy_hardened_no_worst_hours
emergency_mode: dynamic_normal_defensive_pause
allow_live: false
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
    paper_path = tmp_path / "paper_trading.yaml"
    paper_path.write_text(
        """
strategy_name: proxy_hardened_no_worst_hours
backup_strategy: proxy_hardened_no_worst_hours_high_margin
symbol: XAUUSD
base_timeframe: 15m
live_mode: false
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
    return candidate_path, paper_path


def make_market_data() -> pd.DataFrame:
    index = pd.to_datetime(["2025-01-01 10:00", "2025-01-01 10:15", "2025-01-01 10:30"])
    return pd.DataFrame(
        {
            "Open": [100.0, 100.5, 101.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 100.5],
            "Close": [100.5, 101.0, 102.0],
            "Volume": [1, 1, 1],
        },
        index=index,
    )


def bullish_signal_builder(_data, strategy_config, _paper_config, _equity):
    signal = TradingSignal(
        timestamp=pd.Timestamp("2025-01-01 10:30"),
        symbol=strategy_config.symbol,
        timeframe=strategy_config.timeframe,
        side="BUY",
        entry_price=102.0,
        stop_loss=100.0,
        take_profit=106.0,
        risk_reward=2.0,
        confidence=82.0,
        reason="test paper buy",
    )
    return ForwardSignalCandidate(
        signal=signal,
        allowed=True,
        reason="accepted",
        metadata={
            "session": "LONDON",
            "score": 82.0,
            "opposite_score": 40.0,
            "score_gap": 42.0,
            "lot_size": 0.01,
            "commission_eur": 0.08,
            "spread_cost_eur": 0.0,
            "slippage_cost_eur": 0.0,
            "total_cost_eur": 0.08,
        },
    )


def no_trade_signal_builder(_data, strategy_config, _paper_config, _equity):
    signal = TradingSignal(
        timestamp=pd.Timestamp("2025-01-01 10:30"),
        symbol=strategy_config.symbol,
        timeframe=strategy_config.timeframe,
        side="NO_TRADE",
        entry_price=None,
        stop_loss=None,
        take_profit=None,
        risk_reward=None,
        confidence=0.0,
        reason="no setup",
    )
    return ForwardSignalCandidate(signal=signal, allowed=False, reason="no setup", metadata={})


def test_paper_forward_creates_files_and_open_trade(tmp_path):
    candidate_path, paper_path = write_configs(tmp_path)

    result = run_paper_forward_once(
        make_market_data(),
        output_dir=tmp_path / "forward",
        candidate_config_path=candidate_path,
        paper_config_path=paper_path,
        signal_builder=bullish_signal_builder,
        now=pd.Timestamp("2025-01-01 10:31"),
    )

    tables = load_forward_tables(tmp_path / "forward")
    assert result.decision == "PAPER_BUY"
    assert result.strategy_name == "proxy_hardened_no_worst_hours_high_margin"
    assert not tables.signals.empty
    assert not tables.open_trades.empty
    assert tables.open_trades.iloc[0]["status"] == "OPEN"


def test_paper_forward_is_idempotent_per_candle(tmp_path):
    candidate_path, paper_path = write_configs(tmp_path)
    output_dir = tmp_path / "forward"

    run_paper_forward_once(
        make_market_data(),
        output_dir=output_dir,
        candidate_config_path=candidate_path,
        paper_config_path=paper_path,
        signal_builder=no_trade_signal_builder,
        now=pd.Timestamp("2025-01-01 10:31"),
    )
    result = run_paper_forward_once(
        make_market_data(),
        output_dir=output_dir,
        candidate_config_path=candidate_path,
        paper_config_path=paper_path,
        signal_builder=bullish_signal_builder,
        now=pd.Timestamp("2025-01-01 10:32"),
    )

    assert result.decision == "NO_TRADE"
    assert "already evaluated" in result.reason
    assert len(load_forward_tables(output_dir).signals) == 1


def test_forward_state_stops_on_daily_loss(tmp_path):
    ensure_forward_files(tmp_path / "forward")
    tables = load_forward_tables(tmp_path / "forward")
    loss_trade = {column: None for column in CLOSED_TRADE_COLUMNS}
    loss_trade.update(
        {
            "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
            "entry_time": "2025-01-01 10:00",
            "exit_time": "2025-01-01 10:15",
            "pnl_eur": -40.0,
        }
    )
    tables = tables.__class__(
        signals=tables.signals,
        open_trades=tables.open_trades,
        closed_trades=pd.DataFrame([loss_trade], columns=CLOSED_TRADE_COLUMNS),
        equity=pd.DataFrame(
            [
                {
                    "equity": 960.0,
                    "running_equity_high": 1000.0,
                }
            ]
        ),
        daily_log=tables.daily_log,
    )

    state = calculate_forward_state(
        tables,
        make_candidate_config(),
        make_paper_config(),
        as_of=pd.Timestamp("2025-01-01 10:30"),
    )

    assert state["status"] == "STOP"
    assert state["daily_loss_pct"] > 3.0
