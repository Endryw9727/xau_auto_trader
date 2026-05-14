from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from src.market_data.data_freshness import analyze_data_freshness
from src.market_data.mt5_readonly_data_updater import (
    MT5DataUpdateResult,
    load_market_data_config,
    update_market_data_from_mt5_readonly,
)


class FakeMT5:
    TIMEFRAME_M15 = 15

    def __init__(self, rows):
        self.rows = rows
        self.shutdown_called = False
        self.execution_called = False
        self.last_start_pos = None

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self.last_start_pos = start_pos
        return self.rows[:count]

    def last_error(self):
        return "fake error"

    def order_send(self, *_args, **_kwargs):
        self.execution_called = True


def write_market_config(path: Path, *, timeframes=("M15",), auto_update=False):
    path.write_text(
        yaml.safe_dump(
            {
                "symbol": "XAUUSD",
                "source": "mt5_demo_readonly",
                "auto_update_data": auto_update,
                "timeframes": list(timeframes),
                "max_bars": {"M15": 10},
            }
        ),
        encoding="utf-8",
    )


def write_demo_config(path: Path):
    path.write_text(
        yaml.safe_dump(
            {
                "demo_only": True,
                "allow_live": False,
                "execution_enabled": False,
                "broker_name": "axi_demo",
                "platform": "mt5",
                "symbol": "XAUUSD",
                "max_lot": 0.01,
                "max_trades_per_day": 2,
                "max_daily_loss_pct": 3,
                "max_weekly_loss_pct": 8,
                "kill_switch": True,
            }
        ),
        encoding="utf-8",
    )


def test_market_data_config_defaults_keep_auto_update_disabled():
    config = load_market_data_config("config/market_data.yaml")

    assert config.symbol == "XAUUSD"
    assert config.auto_update_data is False
    assert "M15" in config.timeframes


def test_mt5_unavailable_exits_safely(monkeypatch, tmp_path):
    market_config = tmp_path / "market_data.yaml"
    demo_config = tmp_path / "demo_broker.yaml"
    write_market_config(market_config, timeframes=("M15",))
    write_demo_config(demo_config)
    monkeypatch.setattr("src.market_data.mt5_readonly_data_updater.import_mt5_module", lambda: None)

    results = update_market_data_from_mt5_readonly(
        market_config_path=market_config,
        demo_config_path=demo_config,
        timeframe_dir=tmp_path / "timeframes",
        m15_csv_path=tmp_path / "xauusd.csv",
    )

    assert len(results) == 1
    assert isinstance(results[0], MT5DataUpdateResult)
    assert results[0].status == "MT5_NOT_AVAILABLE"
    assert results[0].added_rows == 0


def test_fake_mt5_updates_m15_and_freshness_can_use_updated_csv(tmp_path):
    market_config = tmp_path / "market_data.yaml"
    demo_config = tmp_path / "demo_broker.yaml"
    timeframe_dir = tmp_path / "timeframes"
    m15_path = tmp_path / "xauusd.csv"
    write_market_config(market_config, timeframes=("M15",))
    write_demo_config(demo_config)

    base_time = datetime(2026, 5, 15, 10, 0)
    rows = [
        {
            "time": int(pd.Timestamp(base_time + timedelta(minutes=15 * index), tz="UTC").timestamp()),
            "open": 2400.0 + index,
            "high": 2401.0 + index,
            "low": 2399.0 + index,
            "close": 2400.5 + index,
            "tick_volume": 100 + index,
        }
        for index in range(3)
    ]
    fake_mt5 = FakeMT5(rows)

    results = update_market_data_from_mt5_readonly(
        market_config_path=market_config,
        demo_config_path=demo_config,
        timeframe_dir=timeframe_dir,
        m15_csv_path=m15_path,
        mt5_module=fake_mt5,
    )

    assert results[0].status == "OK"
    assert results[0].added_rows == 3
    assert fake_mt5.shutdown_called is True
    assert fake_mt5.execution_called is False
    assert fake_mt5.last_start_pos == 1
    assert m15_path.exists()
    assert (timeframe_dir / "XAUUSD_M15.csv").exists()

    freshness = analyze_data_freshness(
        m15_path,
        now=pd.Timestamp(base_time + timedelta(minutes=40)),
        symbol="XAUUSD",
    )
    assert freshness.status == "OK"
