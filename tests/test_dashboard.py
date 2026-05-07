from src.dashboard.dashboard import DATABASE_PATH, METRICS_PATH, TRADES_PATH


def test_dashboard_paths_are_defined():
    assert str(TRADES_PATH) == "reports/backtests/trades.csv"
    assert str(METRICS_PATH) == "reports/backtests/metrics.csv"
    assert str(DATABASE_PATH) == "data/database/trading.db"
