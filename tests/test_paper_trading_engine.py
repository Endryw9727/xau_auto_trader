import pandas as pd
import pytest

from src.database.db import get_all_signals
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


def test_run_paper_trading_on_data_returns_result_and_saves_signals(tmp_path):
    df = make_paper_test_data()
    config = PaperTradingConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        warmup_candles=220,
    )
    db_path = tmp_path / "paper_signals.db"

    result = run_paper_trading_on_data(df, paper_config=config, db_path=db_path)
    saved_signals = get_all_signals(db_path)

    assert result.final_balance > 0
    assert hasattr(result, "trades")
    assert result.total_trades >= 0
    assert len(saved_signals) > 0


def test_run_paper_trading_rejects_small_dataset():
    df = make_paper_test_data(rows=50)

    with pytest.raises(ValueError):
        run_paper_trading_on_data(df, paper_config=PaperTradingConfig(warmup_candles=220))


def test_export_paper_trading_report(tmp_path):
    df = make_paper_test_data()
    db_path = tmp_path / "paper_signals.db"
    result = run_paper_trading_on_data(
        df,
        paper_config=PaperTradingConfig(warmup_candles=220),
        db_path=db_path,
    )

    path = export_paper_trading_report(result, output_dir=tmp_path)

    assert path.exists()


def test_paper_trading_does_not_save_no_trade_signals_to_db(monkeypatch):
    saved_signals = []

    def fake_save_signal_to_db(signal, db_path="data/database/trading.db", approved_by_risk_manager=False, blocked_reason=None):
        saved_signals.append(signal.side)
        return len(saved_signals)

    monkeypatch.setattr(
        "src.execution.paper_trading_engine.save_signal_to_db",
        fake_save_signal_to_db,
    )

    df = make_paper_test_data(rows=260)
    config = PaperTradingConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        warmup_candles=220,
    )

    run_paper_trading_on_data(df, paper_config=config)

    assert "NO_TRADE" not in saved_signals
