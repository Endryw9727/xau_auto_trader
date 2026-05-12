import pandas as pd

from src.paper.paper_engine import (
    PAPER_DAILY_COLUMNS,
    PAPER_EQUITY_COLUMNS,
    PAPER_TRADE_COLUMNS,
    PaperTradingConfig,
    run_controlled_paper_simulation,
    simulate_paper_strategy,
)
from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_metrics


def make_config() -> PaperTradingConfig:
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


def make_trades(strategy_name: str = "proxy_hardened_no_worst_hours") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": [strategy_name] * 4,
            "entry_time": pd.to_datetime(
                [
                    "2025-01-01 09:00:00",
                    "2025-01-01 10:00:00",
                    "2025-01-01 11:00:00",
                    "2025-01-02 09:00:00",
                ]
            ),
            "exit_time": pd.to_datetime(
                [
                    "2025-01-01 09:30:00",
                    "2025-01-01 10:30:00",
                    "2025-01-01 11:30:00",
                    "2025-01-02 09:30:00",
                ]
            ),
            "symbol": ["XAUUSD"] * 4,
            "timeframe": ["15m"] * 4,
            "side": ["BUY", "SELL", "BUY", "BUY"],
            "session": ["LONDON", "LONDON", "LONDON", "NEW YORK"],
            "entry_price": [100.0, 100.0, 100.0, 100.0],
            "exit_price": [110.0, 95.0, 120.0, 90.0],
            "stop_loss": [95.0, 105.0, 95.0, 95.0],
            "take_profit": [110.0, 95.0, 120.0, 110.0],
            "score_long": [80.0, 50.0, 82.0, 83.0],
            "score_short": [50.0, 84.0, 52.0, 48.0],
            "risk_reward": [2.0, 2.0, 2.0, 2.0],
            "signal_reason": ["test"] * 4,
            "profit_loss": [10.0, 5.0, 20.0, -10.0],
            "pnl": [10.0, 5.0, 20.0, -10.0],
        }
    )


def make_result(strategy_name: str = "proxy_hardened_no_worst_hours") -> BacktestResult:
    trades = make_trades(strategy_name)
    return BacktestResult(
        trades=trades,
        metrics=calculate_metrics(trades, initial_balance=1000.0),
        final_balance=1025.0,
    )


def test_simulate_paper_strategy_applies_costs_and_daily_trade_limit():
    config = make_config()
    paper_trades, equity_curve, daily_summary, summary = simulate_paper_strategy(
        make_trades(),
        strategy_name=config.strategy_name,
        config=config,
        market_days=[pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")],
    )

    assert set(PAPER_TRADE_COLUMNS).issubset(paper_trades.columns)
    assert set(PAPER_EQUITY_COLUMNS).issubset(equity_curve.columns)
    assert set(PAPER_DAILY_COLUMNS).issubset(daily_summary.columns)
    assert len(paper_trades[paper_trades["entry_time"].dt.date == pd.Timestamp("2025-01-01").date()]) == 2
    assert paper_trades.iloc[0]["commission_eur"] == 0.08
    assert paper_trades.iloc[0]["lot_size"] == 0.01
    assert summary["total_trades"] == 3
    assert summary["no_trade_days"] == 0


def test_run_controlled_paper_simulation_exports_reports(tmp_path):
    config = make_config()
    summary_path = tmp_path / "summary.csv"
    trades_path = tmp_path / "trades.csv"
    equity_path = tmp_path / "equity.csv"
    daily_path = tmp_path / "daily.csv"

    summary, paper_trades, equity_curve, daily_summary = run_controlled_paper_simulation(
        {"proxy_hardened_no_worst_hours": make_result()},
        config=config,
        market_data=pd.DataFrame(index=pd.to_datetime(["2025-01-01", "2025-01-02"])),
        output_summary_path=summary_path,
        output_trades_path=trades_path,
        output_equity_path=equity_path,
        output_daily_path=daily_path,
    )

    assert summary_path.exists()
    assert trades_path.exists()
    assert equity_path.exists()
    assert daily_path.exists()
    assert "proxy_hardened_no_worst_hours" in set(summary["strategy_name"])
    assert "proxy_hardened_no_worst_hours_high_margin" in set(summary["strategy_name"])
    assert not paper_trades.empty
    assert not equity_curve.empty
    assert not daily_summary.empty


def test_paper_engine_is_research_only():
    source = open("src/paper/paper_engine.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
