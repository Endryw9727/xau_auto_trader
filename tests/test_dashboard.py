from src.dashboard.dashboard import DATABASE_PATH, METRICS_PATH, TRADES_PATH, calculate_profit_factor
import pandas as pd


def test_dashboard_paths_are_defined():
    assert str(TRADES_PATH) == "reports/backtests/trades.csv"
    assert str(METRICS_PATH) == "reports/backtests/metrics.csv"
    assert str(DATABASE_PATH) == "data/database/trading.db"


def test_calculate_profit_factor():
    df = pd.DataFrame({"profit_loss": [10.0, 5.0, -5.0]})

    assert calculate_profit_factor(df) == 3.0
