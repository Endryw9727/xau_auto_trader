from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from src.execution import v51_demo_executor as executor
from src.strategy_lab.strategy_v51_demo_intraday import load_v51_config, validate_v51_config


NOW = pd.Timestamp("2026-05-23 12:00:00", tz="UTC")


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TIMEFRAME_M15 = 15
    SYMBOL_TRADE_MODE_DISABLED = 0

    def __init__(self, *, equity=1000.0, deals=None, has_history=False):
        self.equity = equity
        self.deals = deals or []
        self.has_history = has_history or deals is not None
        self.order_send_called = False

    def initialize(self):
        return True

    def shutdown(self):
        return None

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO, trade_allowed=True, server="Demo", balance=1000.0, equity=self.equity
        )

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=True)

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol, visible=True, trade_mode=1, filling_mode=1, spread=10, point=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=2400.0, ask=2400.10)

    def positions_get(self, symbol=None):
        return []

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        latest = NOW - pd.Timedelta(minutes=15)
        index = pd.date_range(end=latest, periods=count, freq="15min")
        price = 2390.0
        rates = []
        for timestamp in index:
            price += 0.05
            rates.append(
                {"time": int(timestamp.timestamp()), "open": price - 0.1, "high": price + 0.6, "low": price - 0.6,
                 "close": price, "tick_volume": 1000}
            )
        return rates

    def order_send(self, request):
        self.order_send_called = True
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=1, deal=2, comment="done")

    def last_error(self):
        return "fake"

    def history_deals_get(self, start, end):
        if not self.has_history:
            raise AttributeError("history not available")
        return self.deals


def _deal(profit, *, magic=510051, comment="V51_DEMO"):
    return SimpleNamespace(profit=profit, commission=0.0, swap=0.0, magic=magic, comment=comment)


def write_config(tmp_path, **overrides):
    raw = yaml.safe_load(open("config/strategy_v51.yaml", encoding="utf-8"))
    raw.update({"allow_demo_execution": True, "execution_enabled": True, "allow_real_live": False, "demo_only": True})
    raw.update(overrides)
    path = tmp_path / "strategy_v51.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _config(tmp_path, **overrides):
    return load_v51_config(write_config(tmp_path, **overrides))


# --- unit tests of the gate helpers ---------------------------------------


def test_parse_news_window():
    assert executor._parse_news_window("12:25-12:35") == (745, 755)
    assert executor._parse_news_window("bad") is None
    assert executor._parse_news_window("25:00-26:00") is None


def test_news_block_reason_active_and_inactive(tmp_path):
    blocking = _config(tmp_path, news_block_enabled=True, news_block_windows=["11:55-12:05"])
    assert executor._news_block_reason(blocking, NOW) is not None

    outside = _config(tmp_path, news_block_enabled=True, news_block_windows=["09:00-09:30"])
    assert executor._news_block_reason(outside, NOW) is None

    disabled = _config(tmp_path, news_block_enabled=False, news_block_windows=["11:55-12:05"])
    assert executor._news_block_reason(disabled, NOW) is None


def test_news_window_wraps_midnight(tmp_path):
    cfg = _config(tmp_path, news_block_enabled=True, news_block_windows=["23:30-00:30"])
    assert executor._news_block_reason(cfg, pd.Timestamp("2026-05-23 00:10:00", tz="UTC")) is not None
    assert executor._news_block_reason(cfg, pd.Timestamp("2026-05-23 02:00:00", tz="UTC")) is None


def test_daily_loss_lock_reason(tmp_path):
    cfg = _config(tmp_path, daily_loss_lock_enabled=True, max_daily_loss_currency=50.0)
    losing = FakeMT5(deals=[_deal(-60.0)])
    assert executor._daily_loss_lock_reason(losing, cfg, NOW) is not None

    winning = FakeMT5(deals=[_deal(20.0)])
    assert executor._daily_loss_lock_reason(winning, cfg, NOW) is None

    # Deals from another strategy magic are ignored.
    other = FakeMT5(deals=[_deal(-99.0, magic=999, comment="other")])
    assert executor._daily_loss_lock_reason(other, cfg, NOW) is None


def test_daily_loss_lock_fails_open_without_history(tmp_path):
    cfg = _config(tmp_path, daily_loss_lock_enabled=True, max_daily_loss_currency=50.0)
    no_history = FakeMT5(has_history=False)
    assert executor._daily_loss_lock_reason(no_history, cfg, NOW) is None


def test_drawdown_lock_reason(tmp_path):
    cfg = _config(tmp_path, drawdown_lock_enabled=True, min_equity_floor=900.0)
    assert executor._drawdown_lock_reason(FakeMT5(equity=800.0), cfg) is not None
    assert executor._drawdown_lock_reason(FakeMT5(equity=950.0), cfg) is None


def test_guardrails_disabled_by_default(tmp_path):
    cfg = _config(tmp_path)
    assert cfg.news_block_enabled is False
    assert cfg.daily_loss_lock_enabled is False
    assert cfg.drawdown_lock_enabled is False
    assert executor._guardrail_block_reason(FakeMT5(), cfg, NOW, NOW.normalize()) is None


# --- integration through run_v51_demo_execution_once ----------------------


def test_news_block_stops_dry_run_order(tmp_path):
    config_path = write_config(tmp_path, news_block_enabled=True, news_block_windows=["11:55-12:05"])
    mt5 = FakeMT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path, output_dir=tmp_path / "demo", mtf_context_summary_path=None,
        mt5_module=mt5, dry_run=True, now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert "news_block_active" in result.reason
    assert mt5.order_send_called is False


def test_drawdown_lock_stops_dry_run_order(tmp_path):
    config_path = write_config(tmp_path, drawdown_lock_enabled=True, min_equity_floor=5000.0)
    mt5 = FakeMT5(equity=1000.0)

    result = executor.run_v51_demo_execution_once(
        config_path=config_path, output_dir=tmp_path / "demo", mtf_context_summary_path=None,
        mt5_module=mt5, dry_run=True, now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert "drawdown_lock_active" in result.reason
    assert mt5.order_send_called is False


# --- config validation and safety -----------------------------------------


def test_invalid_news_window_rejected(tmp_path):
    with pytest.raises(ValueError):
        _config(tmp_path, news_block_enabled=True, news_block_windows=["nope"])


def test_negative_guardrail_budgets_rejected(tmp_path):
    with pytest.raises(ValueError):
        _config(tmp_path, max_daily_loss_currency=-1.0)
    with pytest.raises(ValueError):
        _config(tmp_path, min_equity_floor=-1.0)


def test_committed_config_stays_disarmed():
    raw = yaml.safe_load(open("config/strategy_v51.yaml", encoding="utf-8"))
    # The hardening must not arm execution in the shared config.
    assert raw["allow_real_live"] is False
    assert raw["allow_demo_execution"] is False
    assert raw["execution_enabled"] is False
    assert raw["demo_only"] is True
    # Guardrails ship disabled by default.
    assert raw["news_block_enabled"] is False
    assert raw["daily_loss_lock_enabled"] is False
    assert raw["drawdown_lock_enabled"] is False
