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
    side = overrides.get("side", "BUY")
    values = {
        "signal_id": "V51-202605231145-BUY",
        "candle_time": NOW - pd.Timedelta(minutes=15),
        "symbol": "XAUUSD-P",
        "side": side,
        "lot_size": 0.01,
        "entry_price": 2400.0,
        "stop_loss": 2398.8 if side == "BUY" else 2401.2,
        "take_profit": 2401.5 if side == "BUY" else 2398.5,
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


def write_mtf_summary(tmp_path, *, final_bias="SHORT_BIAS", m1_status="OK", m5_status="OK", m1_used=True, m5_used=True):
    rows = []
    for timeframe in ("D1", "H4", "H1", "M15", "M5", "M1"):
        status = m5_status if timeframe == "M5" else m1_status if timeframe == "M1" else "OK"
        used = m5_used if timeframe == "M5" else m1_used if timeframe == "M1" else True
        rows.append(
            {
                "final_bias": final_bias,
                "final_reason": "test mtf context",
                "timeframe": timeframe,
                "status": status,
                "data_status": status,
                "used_in_bias": used,
            }
        )
    path = tmp_path / "v51_mtf_context_summary.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


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


def make_live_feature_candidates(*, latest_accepted: bool) -> pd.DataFrame:
    index = pd.DatetimeIndex([NOW - pd.Timedelta(minutes=45), NOW - pd.Timedelta(minutes=30), NOW - pd.Timedelta(minutes=15)])
    latest_score = 82.0 if latest_accepted else 50.0
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
            "v50_score_long": [95.0, 72.0, latest_score],
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
    assert result.reason == "candidate_stale"
    assert result.time_alignment_status == "candidate_stale"
    assert result.slippage_points is None
    assert fake.order_send_called is False


def test_v51_demo_executor_rifiuta_candidate_futuro(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path)
    future_candidate = make_candidate(candle_time=NOW + pd.Timedelta(minutes=15), entry_price=2400.0)
    force_selected_candidate(monkeypatch, future_candidate)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    latest = log.iloc[-1]
    assert result.status == "NO_TRADE"
    assert result.reason == "candidate_time_in_future"
    assert result.time_alignment_status == "candidate_time_in_future"
    assert result.candidate_age_minutes < 0
    assert latest["time_alignment_status"] == "candidate_time_in_future"
    assert str(latest["now_utc"]).startswith("2026-05-23T12:00:00")
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
    assert result.adverse_slippage_points == pytest.approx(300.0)
    assert fake.order_send_called is False


def test_v51_demo_executor_sell_adverse_slippage_rejected(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="SHORT_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="SELL", entry_price=2400.0))
    fake = FakeV51MT5(bid=2399.50, ask=2399.60)

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "adverse_slippage_exceeded"
    assert result.mtf_filter_reason == "mtf_direction_filter_passed"
    assert result.adverse_slippage_points == pytest.approx(50.0)
    assert fake.order_send_called is False


def test_v51_demo_executor_buy_adverse_slippage_rejected(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="LONG_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="BUY", entry_price=2400.0))
    fake = FakeV51MT5(bid=2400.49, ask=2400.50)

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "adverse_slippage_exceeded"
    assert result.adverse_slippage_points == pytest.approx(50.0)
    assert fake.order_send_called is False


def test_v51_demo_executor_price_chase_distance_rejected(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="LONG_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="BUY", entry_price=2400.0))
    fake = FakeV51MT5(bid=2398.90, ask=2399.00)

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "price_chase_distance_exceeded"
    assert result.adverse_slippage_points == pytest.approx(0.0)
    assert result.chase_distance_points == pytest.approx(100.0)
    assert fake.order_send_called is False


def test_v51_demo_executor_fresh_valid_mtf_price_accettato_dry_run(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="LONG_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="BUY", entry_price=2400.0))
    fake = FakeV51MT5(bid=2400.00, ask=2400.10)

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    orders = pd.read_csv(tmp_path / "v51_demo_orders.csv")
    latest_order = orders.iloc[-1]
    assert result.status == "DRY_RUN"
    assert result.accepted is True
    assert result.live_entry_price == pytest.approx(2400.10)
    assert result.adverse_slippage_points == pytest.approx(10.0)
    assert result.chase_distance_points == pytest.approx(10.0)
    assert result.mtf_filter_reason == "mtf_direction_filter_passed"
    assert latest_order["entry_price"] == pytest.approx(2400.10)
    assert latest_order["stop_loss"] < latest_order["entry_price"] < latest_order["take_profit"]
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


def test_v51_mtf_filter_blocca_buy_quando_short_bias(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="SHORT_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="BUY"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    assert result.status == "NO_TRADE"
    assert result.reason == "mtf_direction_filter_blocked"
    assert result.mtf_final_bias == "SHORT_BIAS"
    assert result.mtf_filter_enabled is True
    assert result.mtf_filter_passed is False
    assert str(log.iloc[-1]["mtf_filter_passed"]).lower() == "false"
    assert log.iloc[-1]["mtf_filter_reason"] == "mtf_direction_filter_blocked"
    assert fake.order_send_called is False


def test_v51_mtf_filter_consente_sell_quando_short_bias(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="SHORT_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="SELL"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    assert result.status == "DRY_RUN"
    assert result.accepted is True
    assert result.mtf_final_bias == "SHORT_BIAS"
    assert result.mtf_filter_enabled is True
    assert result.mtf_filter_passed is True
    assert str(log.iloc[-1]["mtf_filter_passed"]).lower() == "true"
    assert log.iloc[-1]["mtf_filter_reason"] == "mtf_direction_filter_passed"
    assert fake.order_send_called is False


def test_v51_mtf_filter_blocca_sell_quando_long_bias(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="LONG_BIAS")
    force_selected_candidate(monkeypatch, make_candidate(side="SELL"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "mtf_direction_filter_blocked"
    assert result.mtf_final_bias == "LONG_BIAS"
    assert fake.order_send_called is False


def test_v51_mtf_filter_blocca_mixed_quando_abilitato(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="MIXED")
    force_selected_candidate(monkeypatch, make_candidate(side="BUY"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "mtf_final_bias_mixed"
    assert result.mtf_final_bias == "MIXED"
    assert fake.order_send_called is False


def test_v51_mtf_filter_disabilitato_comportamento_invariato(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=False)
    force_selected_candidate(monkeypatch, make_candidate(side="BUY"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=tmp_path / "missing_mtf_summary.csv",
        now=NOW,
    )

    assert result.status == "DRY_RUN"
    assert result.accepted is True
    assert result.mtf_filter_enabled is False
    assert result.mtf_filter_passed is True
    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    assert str(log.iloc[-1]["mtf_filter_enabled"]).lower() == "false"
    assert fake.order_send_called is False


def test_v51_mtf_filter_blocca_m1_m5_stale_se_require_data_ok(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True, require_mtf_data_ok=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="SHORT_BIAS", m1_status="STALE", m1_used=False)
    force_selected_candidate(monkeypatch, make_candidate(side="SELL"))
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "mtf_data_not_ok"
    assert result.mtf_final_bias == "SHORT_BIAS"
    assert fake.order_send_called is False


def test_v51_mtf_audit_no_candidate_logga_bias_e_enabled(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="MIXED")
    market_data = make_live_feature_candidates(latest_accepted=False)
    monkeypatch.setattr(executor, "read_mt5_closed_rates", lambda mt5, config: market_data)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    latest = log.iloc[-1]
    assert result.status == "NO_TRADE"
    assert result.mtf_final_bias == "MIXED"
    assert result.mtf_filter_enabled is True
    assert result.mtf_filter_passed is False
    assert result.mtf_filter_reason == "no_v51_candidate_to_filter"
    assert latest["mtf_final_bias"] == "MIXED"
    assert str(latest["mtf_filter_enabled"]).lower() == "true"
    assert str(latest["mtf_filter_passed"]).lower() == "false"
    assert latest["mtf_filter_reason"] == "no_v51_candidate_to_filter"
    assert fake.order_send_called is False


def test_v51_mtf_audit_config_gate_logga_bias(tmp_path):
    config_path = write_v51_config(tmp_path, allow_demo_execution=False, use_mtf_context_filter=True)
    mtf_path = write_mtf_summary(tmp_path, final_bias="LONG_BIAS")
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        mtf_context_summary_path=mtf_path,
        now=NOW,
    )

    log = pd.read_csv(tmp_path / "v51_demo_execution_log.csv")
    latest = log.iloc[-1]
    assert result.status == "REJECTED"
    assert result.mtf_final_bias == "LONG_BIAS"
    assert result.mtf_filter_enabled is True
    assert result.mtf_filter_reason == "no_v51_candidate_to_filter"
    assert latest["mtf_final_bias"] == "LONG_BIAS"
    assert str(latest["mtf_filter_enabled"]).lower() == "true"
    assert latest["mtf_filter_reason"] == "no_v51_candidate_to_filter"
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
    assert result.reason == "candidate_stale"
    assert fake.order_send_called is False


def test_v51_demo_executor_ignora_vecchio_score_alto_senza_candidate_recente(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, require_latest_closed_candle_candidate=True)
    market_data = make_live_feature_candidates(latest_accepted=False)
    monkeypatch.setattr(executor, "read_mt5_closed_rates", lambda mt5, config: market_data)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(config_path=config_path, output_dir=tmp_path, mt5_module=fake, now=NOW)

    assert result.status == "NO_TRADE"
    assert result.reason == "no fresh live candidate on latest closed candle"
    assert result.selection_reason == "no fresh live candidate on latest closed candle"
    assert result.latest_closed_candle_time == market_data.index[-1]
    assert result.selected_candidate_time is None
    assert fake.order_send_called is False


def test_v51_demo_executor_seleziona_candidate_sulla_latest_closed_candle(tmp_path):
    config_path = write_v51_config(tmp_path, require_latest_closed_candle_candidate=True)
    config = load_v51_config(config_path)
    market_data = make_live_feature_candidates(latest_accepted=True)

    candidate, reason = executor.select_best_v51_candidate(
        market_data,
        config,
        latest_closed_candle_time=market_data.index[-1],
    )

    assert candidate is not None
    assert candidate.candle_time == market_data.index[-1]
    assert candidate.signal_id == "V51-202605231145-BUY"
    assert reason == "V51 live candidate selected on latest closed candle"


def test_v51_demo_executor_require_latest_non_seleziona_candela_precedente(tmp_path):
    config_path = write_v51_config(tmp_path, require_latest_closed_candle_candidate=True)
    config = load_v51_config(config_path)
    market_data = make_live_feature_candidates(latest_accepted=False)

    candidate, reason = executor.select_best_v51_candidate(
        market_data,
        config,
        latest_closed_candle_time=market_data.index[-1],
    )

    assert candidate is None
    assert reason == "no fresh live candidate on latest closed candle"


def test_v51_demo_executor_non_apre_ordini_demo_su_candidate_vecchi_live(tmp_path, monkeypatch):
    config_path = write_v51_config(tmp_path, require_latest_closed_candle_candidate=True)
    market_data = make_live_feature_candidates(latest_accepted=False)
    monkeypatch.setattr(executor, "read_mt5_closed_rates", lambda mt5, config: market_data)
    fake = FakeV51MT5()

    result = executor.run_v51_demo_execution_once(
        config_path=config_path,
        output_dir=tmp_path,
        mt5_module=fake,
        dry_run=False,
        now=NOW,
    )

    assert result.status == "NO_TRADE"
    assert result.reason == "no fresh live candidate on latest closed candle"
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
