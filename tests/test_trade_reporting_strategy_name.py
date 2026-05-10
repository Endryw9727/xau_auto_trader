import pandas as pd

from src.analysis.trade_level_diagnostics import build_trade_level_summary
from src.backtesting.backtester import (
    BacktestConfig,
    TRADES_BY_STRATEGY_FILENAME,
    export_backtest_report,
    run_backtest,
)
from src.strategy_lab.lab import export_strategy_trades_report
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal


def make_trade_reporting_data(rows: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    close = [100.0 + index * 0.5 for index in range(rows)]
    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 2.5 for value in close],
            "Low": [value - 0.5 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def fixed_buy_signal(window: pd.DataFrame, config: StrategyConfig) -> TradingSignal:
    entry = float(window["Close"].iloc[-1])
    return TradingSignal(
        timestamp=window.index[-1].to_pydatetime(),
        symbol=config.symbol,
        timeframe=config.timeframe,
        side="BUY",
        entry_price=entry,
        stop_loss=entry - 1.0,
        take_profit=entry + 2.0,
        risk_reward=2.0,
        confidence=80.0,
        reason=(
            "V50 Pine technical approximation"
            " | Side=BUY"
            " | score=72.0"
            " | opposite_score=30.0"
            " | session=Asia"
            " | RR=2.00"
        ),
    )


def test_backtest_trade_report_contains_strategy_name_and_alias_columns(tmp_path):
    result = run_backtest(
        df=make_trade_reporting_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=5, max_consecutive_losses=10),
        signal_generator=fixed_buy_signal,
        save_signals=False,
        strategy_name="v50_pine_technical_strategy",
    )
    trades_path, _ = export_backtest_report(result, output_dir=tmp_path)
    trades_by_strategy_path = tmp_path / TRADES_BY_STRATEGY_FILENAME
    trades = pd.read_csv(trades_path)

    assert not trades.empty
    assert trades_by_strategy_path.exists()
    assert set(trades["strategy_name"]) == {"v50_pine_technical_strategy"}
    assert {
        "entry_time",
        "exit_time",
        "pnl",
        "pnl_pct",
        "bars_in_trade",
        "session",
        "setup_type",
        "score_long",
        "score_short",
        "signal_reason",
    }.issubset(trades.columns)
    assert trades.iloc[0]["side_label"] == "LONG"
    assert trades.iloc[0]["score_long"] == 72.0
    assert trades.iloc[0]["score_short"] == 30.0


def test_trade_level_diagnostics_accept_missing_optional_columns():
    minimal_trades = pd.DataFrame(
        {
            "strategy_name": ["v50_pine_technical_strategy", "v50_pine_technical_strategy"],
            "timestamp_open": ["2026-01-01 01:00:00", "2026-01-01 02:00:00"],
            "side": ["BUY", "SELL"],
            "profit_loss": [10.0, -4.0],
        }
    )

    summary = build_trade_level_summary(minimal_trades)

    assert len(summary) == 1
    assert summary.iloc[0]["total_trades"] == 2
    assert summary.iloc[0]["wins"] == 1
    assert summary.iloc[0]["losses"] == 1
    assert summary.iloc[0]["profit_factor"] == 2.5


def test_strategy_trades_report_writes_combined_alias_csv(tmp_path):
    result = run_backtest(
        df=make_trade_reporting_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=5, max_consecutive_losses=10),
        signal_generator=fixed_buy_signal,
        save_signals=False,
        strategy_name="v50_pine_technical_strategy",
    )
    trades_by_strategy_path = export_strategy_trades_report(
        {"v50_pine_technical_strategy": result},
        output_path=tmp_path / TRADES_BY_STRATEGY_FILENAME,
    )
    trades_path = tmp_path / "trades.csv"
    trades = pd.read_csv(trades_path)

    assert trades_by_strategy_path.exists()
    assert trades_path.exists()
    assert "strategy_name" in trades.columns
    assert set(trades["strategy_name"]) == {"v50_pine_technical_strategy"}
