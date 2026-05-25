from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from src.execution import v51_demo_executor as executor
from src.execution.v51_demo_executor import V51DemoCandidate
from src.strategy_lab.strategy_v51_demo_intraday import load_v51_config


NOW = pd.Timestamp("2026-05-23 12:00:00", tz="UTC")


class FakeV51MT5:
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

    def __init__(self, *, spread=10, demo=True, positions=None, latest_age_minutes=15, bid=2400.0, ask=2400.10):
        self.spread = spread
        self.demo = demo
        self.positions = positions or []
        self.latest_age_minutes = latest_age_minutes
        self.bid = bid
        self.ask = ask
        self.order_send_called = False
        self.last_request = None

    def initialize(self):
        return True

    def shutdown(self):
        return None

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else self.ACCOUNT_TRADE_MODE_REAL,
            trade_allowed=True,
            server="Fortune Prime Demo" if self.demo else "Fortune Prime Real",
            balance=1000.0,
            equity=1000.0,
        )

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=True)

    def symbol_info(self, symbol):
        return SimpleNamespace(
            name=symbol,
            visible=True,
            trade_mode=1,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=1.0,
            filling_mode=1,
            spread=self.spread,
            point=0.01,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self.bid, ask=self.ask)

    def positions_get(self, symbol=None):
        return self.positions

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        latest = NOW - pd.Timedelta(minutes=self.latest_age_minutes)
        index = pd.date_range(end=latest, periods=count, freq="15min")
        rates = []
        price = 2390.0
        for timestamp in index:
            price += 0.05
            rates.append(
                {
                    "time": int(timestamp.timestamp()),
                    "open": price - 0.1,
                    "high": price + 0.6,
                    "low": price - 0.6,
                    "close": price,
                    "tick_volume": 1000,
                }
            )
        return rates

    def order_send(self, request):
        self.order_send_called = True
        self.last_request = request
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=111, deal=222, comment="done")

    def last_error(self):
        return "fake"


def write_v51_config(tmp_path, **overrides):
    raw = yaml.safe_load(open("config/strategy_v51.yaml", encoding="utf-8"))
    raw.update(
        {
            "allow_demo_execution": True,
            "execution_enabled": True,
            "allow_real_live": False,
            "demo_only": True,
        }
    )
    raw.update(overrides)
    path = tmp_path / "strategy_v51.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def make_candidate(**overrides):
    values = {
        "signal_id": "V51-202605231145-BUY",
        "candle_time": NOW - pd.Timedelta(minutes=15),
        "symbol": "XAUUSD-P",
        "side": "BUY",
        "lot_size": 0.01,
        "entry_price": 2400.0,
        "stop_loss": 2398.8,
        "take_profit": 2401.5,
        "risk_reward": 1.25,
        "score": 80.0,
        "score_gap": 20.0,
        "spread_cost": 0.0,
        "slippage_estimate": 0.1,
        "reason": "test candidate",
        "session": "LONDON",
    }
    values.update(overrides)
    return V51DemoCandidate(**values)


def force_selected_candidate(monkeypatch, candidate):
    monkeypatch.setattr(executor, "select_best_v51_candidate", lambda *args, **kwargs: (candidate, "forced candidate"))


def make_feature_candidates() -> pd.DataFrame:
    index = pd.date_range("2026-05-23 10:00:00", periods=3, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [2399.8, 2400.8, 2401.8],
            "High": [2401.0, 2402.0, 2403.0],
            "Low": [2399.0, 2400.0, 2401.0],
            "Close": [2400.0, 2401.0, 2402.0],
            "Volume": [1000.0] * 3,
            "ATR_14": [1.0] * 3,
            "ADX_14": [20.0] * 3,
            "v50_adx": [20.0] * 3,
            "v50_ema21": [2399.0, 2400.0, 2401.0],
            "v50_score_long": [66.0, 82.0, 76.0],
            "v50_score_short": [20.0, 20.0, 20.0],
            "v50_quality_long_ok": [True] * 3,
            "v50_quality_short_ok": [False] * 3,
            "v50_setup_long": [True] * 3,
            "v50_setup_short": [False] * 3,
            "v50_chop_block": [False] * 3,
            "v50_long_chase_block": [False] * 3,
            "v50_late_long_impulse": [False] * 3,
            "v50_session": ["LONDON"] * 3,
        },
        index=index,
    )


def test_v51_demo_executor_non_puo_abilitare_allow_real_live(tmp_path):
    config_path = write_v51_config(tmp_path, allow_real_live=True)

    with pytest.raises(PermissionError, match="allow_real_live"):
        executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=FakeV51MT5())


def test_v51_demo_executor_blocca_se_allow_demo_execution_false(tmp_path):
    config_path = write_v51_config(tmp_path, allow_demo_execution=False)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.accepted is False
    assert "allow_demo_execution=false" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_blocca_se_execution_enabled_false(tmp_path):
    config_path = write_v51_config(tmp_path, execution_enabled=False)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.accepted is False
    assert "execution_enabled=false" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_blocca_senza_sl_tp():
    config = load_v51_config()
    candidate = make_candidate(stop_loss=None, take_profit=None)

    reason = executor.validate_v51_demo_candidate(candidate, config)

    assert "SL and TP" in reason


def test_v51_demo_executor_blocca_rr_sotto_minimo():
    config = load_v51_config()
    candidate = make_candidate(risk_reward=1.0)

    reason = executor.validate_v51_demo_candidate(candidate, config)

    assert "RR" in reason


def test_v51_demo_executor_blocca_spread_troppo_alto(tmp_path):
    config_path = write_v51_config(tmp_path, max_spread_points=20)
    fake = FakeV51MT5(spread=100)

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert "spread" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_blocca_dati_stale(tmp_path):
    config_path = write_v51_config(tmp_path, max_data_age_minutes=45)
    fake = FakeV51MT5(latest_age_minutes=120)

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert "stale" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_rifiuta_candidate_stale_prima_dello_slippage(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path)
    stale_candidate = make_candidate(candle_time=NOW - pd.Timedelta(minutes=60), entry_price=2400.0)
    force_selected_candidate(monkeypatch, stale_candidate)
    fake = FakeV51MT5(bid=2402.90, ask=2403.00)

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert result.reason.startswith("candidate stale:")
    assert "max_candidate_age_minutes=20" in result.reason
    assert result.slippage_points is None
    assert fake.order_send_called is False


def test_v51_demo_executor_candidate_fresco_arriva_al_controllo_successivo(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path)
    fresh_candidate = make_candidate(candle_time=NOW - pd.Timedelta(minutes=15), entry_price=2400.0)
    force_selected_candidate(monkeypatch, fresh_candidate)
    fake = FakeV51MT5(bid=2402.90, ask=2403.00)

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert "slippage" in result.reason
    assert result.slippage_points == pytest.approx(300.0)
    assert fake.order_send_called is False


def test_v51_demo_executor_non_ritenta_signal_id_rifiutato_entra_cooldown(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, rejected_signal_cooldown_minutes=30)
    candidate = make_candidate()
    force_selected_candidate(monkeypatch, candidate)
    pd.DataFrame(
        [
            {
                "timestamp": (NOW - pd.Timedelta(minutes=10)).isoformat(),
                "event": "no_trade",
                "status": "NO_TRADE",
                "decision": "NO_TRADE",
                "reason": "slippage 188.0 points exceeds max 20.0",
                "signal_id": candidate.signal_id,
                "candle_time": candidate.candle_time.isoformat(),
                "symbol": candidate.symbol,
                "side": candidate.side,
                "dry_run": True,
            }
        ],
        columns=executor.V51_DEMO_LOG_COLUMNS,
    ).to_csv(tmp_path / "v51_demo_execution_log.csv", index=False)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert result.reason.startswith("duplicate rejected signal cooldown")
    assert fake.order_send_called is False


def test_v51_demo_executor_allow_real_live_resta_false():
    config = load_v51_config()

    assert config.allow_real_live is False


def test_v51_demo_executor_non_apre_ordini_se_freshness_required_e_candidate_vecchio(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, candidate_freshness_required=True)
    stale_candidate = make_candidate(candle_time=NOW - pd.Timedelta(minutes=60))
    force_selected_candidate(monkeypatch, stale_candidate)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        dry_run=False,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason.startswith("candidate stale:")
    assert fake.order_send_called is False


def test_v51_demo_executor_blocca_duplicato_stessa_candela_signal_id(tmp_path):
    config = load_v51_config()
    candidate = make_candidate()
    pd.DataFrame(
        [
            {
                "signal_id": candidate.signal_id,
                "candle_time": candidate.candle_time.isoformat(),
                "status": "SENT",
            }
        ],
        columns=executor.V51_DEMO_ORDER_COLUMNS,
    ).to_csv(tmp_path / "v51_demo_orders.csv", index=False)
    orders = executor.load_v51_demo_orders(tmp_path)

    reason = executor.validate_v51_demo_candidate(candidate, config, orders)

    assert "duplicate" in reason


def test_v51_demo_executor_non_supera_max_trades_per_day(tmp_path):
    config_path = write_v51_config(tmp_path, max_trades_per_day=2)
    rows = [
        {"signal_id": f"sig-{index}", "candle_time": (NOW - pd.Timedelta(minutes=15 + index)).isoformat(), "status": "SENT"}
        for index in range(2)
    ]
    pd.DataFrame(rows, columns=executor.V51_DEMO_ORDER_COLUMNS).to_csv(tmp_path / "v51_demo_orders.csv", index=False)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert "max trades per day" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_non_apre_se_esiste_posizione_v51_demo(tmp_path):
    config_path = write_v51_config(tmp_path)
    position = SimpleNamespace(symbol="XAUUSD-P", magic=510051, comment="V51_DEMO")
    fake = FakeV51MT5(positions=[position])

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert "open V51_DEMO position" in result.reason
    assert fake.order_send_called is False


def test_v51_demo_executor_seleziona_miglior_candidato_non_il_primo():
    config = load_v51_config()

    candidate, reason = executor.select_best_v51_candidate(make_feature_candidates(), config)

    assert reason == "V51 candidate selected"
    assert candidate.signal_id == "V51-202605231015-BUY"
    assert candidate.score == 82.0
