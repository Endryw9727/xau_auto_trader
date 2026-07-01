from pathlib import Path

import pandas as pd

from scripts import normalize_broker_csv as norm
from src.data_feed.market_data import load_csv_data


def test_derive_symbol():
    assert norm.derive_symbol("EURUSD_M15.csv") == "eurusd"
    assert norm.derive_symbol("XAUUSD_M15.csv") == "xauusd"
    assert norm.derive_symbol("USATECHIDXUSD_M15.csv") == "nas100"
    assert norm.derive_symbol("USA500IDXUSD_M15.csv") == "sp500"
    assert norm.derive_symbol("GBPUSD.csv") == "gbpusd"


def test_normalize_headerless_combined_datetime(tmp_path):
    src = tmp_path / "EURUSD_M15.csv"
    src.write_text(
        "2022-06-27 02:00,1.05606,1.05636,1.05586,1.05596,3159\n"
        "2022-06-27 02:15,1.05597,1.0563,1.0559,1.05603,2132\n"
        "2022-06-27 02:30,1.05604,1.05667,1.05604,1.05624,2238\n",
        encoding="utf-8",
    )
    result = norm.normalize_file(src, tmp_path / "out")

    assert result.status == "OK"
    assert result.symbol == "eurusd"
    assert result.rows == 3
    # The output is loadable by the project loader (header + correct columns).
    loaded = load_csv_data(Path(result.output))
    assert list(loaded.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(loaded) == 3
    assert float(loaded.iloc[0]["Open"]) == 1.05606


def test_normalize_separate_date_time(tmp_path):
    src = tmp_path / "GBPUSD_M15.csv"
    src.write_text(
        "2022-06-27,02:00,1.2200,1.2210,1.2190,1.2205,1000\n"
        "2022-06-27,02:15,1.2205,1.2215,1.2200,1.2208,1100\n",
        encoding="utf-8",
    )
    result = norm.normalize_file(src, tmp_path / "out")
    assert result.status == "OK"
    loaded = load_csv_data(Path(result.output))
    assert len(loaded) == 2
    assert float(loaded.iloc[0]["High"]) == 1.2210


def test_normalize_with_header_and_extra_columns(tmp_path):
    src = tmp_path / "XAUUSD_M15.csv"
    # Header present, plus extra trailing columns (tick volume + spread).
    src.write_text(
        "Date,Open,High,Low,Close,Volume,Spread\n"
        "2022-06-27 02:00,1820.1,1821.0,1819.5,1820.6,500,12\n"
        "2022-06-27 02:15,1820.6,1822.0,1820.0,1821.4,480,11\n",
        encoding="utf-8",
    )
    result = norm.normalize_file(src, tmp_path / "out")
    assert result.status == "OK"
    loaded = load_csv_data(Path(result.output))
    assert len(loaded) == 2
    assert float(loaded.iloc[1]["Close"]) == 1821.4


def test_normalize_directory(tmp_path):
    (tmp_path / "EURUSD_M15.csv").write_text(
        "2022-06-27 02:00,1.05,1.06,1.04,1.055,10\n", encoding="utf-8"
    )
    (tmp_path / "USA500IDXUSD_M15.csv").write_text(
        "2022-06-27 02:00,4000,4010,3990,4005,100\n", encoding="utf-8"
    )
    out = tmp_path / "raw"
    results = norm.normalize_directory(tmp_path, out)

    symbols = {r.symbol for r in results}
    assert {"eurusd", "sp500"} <= symbols
    assert (out / "eurusd.csv").exists()
    assert (out / "sp500.csv").exists()


def test_normalizer_does_not_execute_orders():
    source = Path("scripts/normalize_broker_csv.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
