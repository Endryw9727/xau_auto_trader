from src.dashboard.dashboard import DATABASE_PATH, METRICS_PATH, TRADES_PATH, calculate_profit_factor
import pandas as pd
import pytest

from src.dashboard.dashboard import load_sqlite_table


def test_dashboard_paths_are_defined():
    assert str(TRADES_PATH) == "reports/backtests/trades.csv"
    assert str(METRICS_PATH) == "reports/backtests/metrics.csv"
    assert str(DATABASE_PATH) == "data/database/trading.db"


def test_calculate_profit_factor():
    df = pd.DataFrame({"profit_loss": [10.0, 5.0, -5.0]})

    assert calculate_profit_factor(df) == 3.0


def test_load_sqlite_table_returns_empty_for_missing_table(tmp_path):
    db_path = tmp_path / "dashboard.db"
    db_path.touch()

    result = load_sqlite_table(db_path, "signals")

    assert result.empty


def test_load_sqlite_table_rejects_unknown_table(tmp_path):
    db_path = tmp_path / "dashboard.db"
    db_path.touch()

    with pytest.raises(ValueError):
        load_sqlite_table(db_path, "signals; DROP TABLE trades")
