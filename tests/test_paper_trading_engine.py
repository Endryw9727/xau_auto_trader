import pandas as pd
import pytest

from src.execution.paper_trading_engine import (
    PaperTradingConfig,
    export_paper_trading_report,
    run_paper_trading_on_data,
)


def make_paper_test_data(rows: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=rows, freq="15min")

    price = 2350.0
    close = []

    for i in range(rows):
        if i < 120:
            price += 0.35
        elif i < 220:
            price -= 0.25
        else:
            price += 0.15

        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 1.5 for value in close],
            "Low": [value - 1.5 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def test_run_paper_trading_on_data_returns_result():
    df = make_paper_test_data()
    config = PaperTradingConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        warmup_candles=220,
    )

    result = run_paper_trading_on_data(df, paper_config=config)

    assert result.final_balance > 0
    assert hasattr(result, "trades")
    assert result.total_trades >= 0


def test_run_paper_trading_rejects_small_dataset():
    df = make_paper_test_data(rows=50)

    with pytest.raises(ValueError):
        run_paper_trading_on_data(df, paper_config=PaperTradingConfig(warmup_candles=220))


def test_export_paper_trading_report(tmp_path):
    df = make_paper_test_data()
    result = run_paper_trading_on_data(
        df,
        paper_config=PaperTradingConfig(warmup_candles=220),
    )

    path = export_paper_trading_report(result, output_dir=tmp_path)

    assert path.exists()
