import pandas as pd
import pytest

from src.backtesting.backtester import BacktestConfig, export_backtest_report, run_backtest
from src.backtesting.metrics import calculate_max_consecutive, calculate_max_drawdown, calculate_metrics
from src.database.db import get_all_signals


def make_backtest_data(rows: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=rows, freq="min")

    close = []
    price = 100.0

    for i in range(rows):
        if i < 150:
            price += 0.08
        else:
            price -= 0.04
        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.05 for value in close],
            "High": [value + 0.50 for value in close],
            "Low": [value - 0.50 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def test_calculate_metrics_empty_trades():
    trades = pd.DataFrame()

    metrics = calculate_metrics(trades, initial_balance=1000.0)

    assert metrics.total_trades == 0
    assert metrics.net_profit == 0.0


def test_calculate_metrics_with_trades():
    trades = pd.DataFrame(
        {
            "profit_loss": [10.0, -5.0, 15.0, -5.0],
        }
    )

    metrics = calculate_metrics(trades, initial_balance=1000.0)

    assert metrics.total_trades == 4
    assert metrics.wins == 2
    assert metrics.losses == 2
    assert metrics.net_profit == 15.0
    assert metrics.profit_factor == 2.5


def test_calculate_max_drawdown():
    equity = pd.Series([1000, 1010, 1005, 1020, 990, 1030])

    drawdown = calculate_max_drawdown(equity)

    assert drawdown == 30.0


def test_calculate_max_consecutive():
    pnl = pd.Series([10, 5, -2, -3, -1, 4, -5])

    assert calculate_max_consecutive(pnl, positive=True) == 2
    assert calculate_max_consecutive(pnl, positive=False) == 3


def test_run_backtest_returns_result_and_saves_signals(tmp_path):
    df = make_backtest_data()
    config = BacktestConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        warmup_candles=220,
    )
    db_path = tmp_path / "backtest_signals.db"

    result = run_backtest(df, backtest_config=config, db_path=db_path)
    saved_signals = get_all_signals(db_path)

    assert result.final_balance > 0
    assert hasattr(result, "trades")
    assert hasattr(result, "metrics")
    assert len(saved_signals) > 0


def test_run_backtest_deduplicates_saved_signals(tmp_path):
    df = make_backtest_data()
    config = BacktestConfig(warmup_candles=220)
    db_path = tmp_path / "backtest_signals.db"

    run_backtest(df, backtest_config=config, db_path=db_path)
    first_count = len(get_all_signals(db_path))

    run_backtest(df, backtest_config=config, db_path=db_path)
    second_count = len(get_all_signals(db_path))

    assert first_count > 0
    assert second_count == first_count


def test_run_backtest_rejects_small_dataset():
    df = make_backtest_data(rows=50)

    with pytest.raises(ValueError):
        run_backtest(df, backtest_config=BacktestConfig(warmup_candles=220))


def test_export_backtest_report(tmp_path):
    df = make_backtest_data()
    db_path = tmp_path / "backtest_signals.db"
    result = run_backtest(df, backtest_config=BacktestConfig(warmup_candles=220), db_path=db_path)

    trades_path, metrics_path = export_backtest_report(result, output_dir=tmp_path)

    assert trades_path.exists()
    assert metrics_path.exists()
