from src.main import REPORT_DIR, RAW_DATA_PATH


def test_main_paths_are_defined():
    assert str(RAW_DATA_PATH) == "data/raw/xauusd.csv"
    assert str(REPORT_DIR) == "reports/backtests"
