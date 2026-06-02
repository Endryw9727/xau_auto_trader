from types import SimpleNamespace

import pandas as pd
import yaml

from scripts import run_v51_live_safe_cycle as script
from src.market_data.data_freshness import DataFreshnessReport


NOW = pd.Timestamp("2026-05-25 12:00:00")


def make_freshness(status: str) -> DataFreshnessReport:
    age = 10.0 if status == "OK" else 120.0
    return DataFreshnessReport(
        symbol="XAUUSD",
        path="data/raw/xauusd.csv",
        status=status,
        reason=f"freshness {status}",
        latest_timestamp=NOW - pd.Timedelta(minutes=age),
        timeframe_minutes=15.0,
        timeframe="15m",
        row_count=100,
        gap_count=0,
        missing_candles=0,
        max_gap_minutes=0.0,
        age_minutes=age,
        missing_expected_candle=status != "OK",
        market_open=True,
        checked_at=NOW,
        error="",
    )


def write_v51_config(
    tmp_path,
    *,
    use_ai_reasoning_filter: bool = False,
    ai_reasoning_report_only: bool = False,
    **overrides,
):
    raw = yaml.safe_load(open("config/strategy_v51.yaml", encoding="utf-8"))
    raw.update(
        {
            "allow_real_live": False,
            "demo_only": True,
            "use_ai_reasoning_filter": use_ai_reasoning_filter,
            "ai_reasoning_report_only": ai_reasoning_report_only,
        }
    )
    raw.update(overrides)
    path = tmp_path / "strategy_v51.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def timeframe_update_ok(calls):
    def update_timeframes():
        calls.append("timeframes")
        return SimpleNamespace(status="OK", summary_path="timeframes.csv", latest_path="timeframes.txt")

    return update_timeframes


def mtf_context_ok(calls, *, final_bias="SHORT_BIAS"):
    def mtf_context(**kwargs):
        calls.append("mtf")
        assert "config_path" in kwargs
        return SimpleNamespace(status="OK", final_bias=final_bias, summary_path="mtf_summary.csv", latest_path="mtf_latest.txt")

    return mtf_context


def mtf_context_with_summary(calls, tmp_path, *, final_bias="SHORT_BIAS"):
    summary_path = tmp_path / "v51_mtf_context_summary.csv"
    pd.DataFrame(
        [
            {
                "final_bias": final_bias,
                "timeframe": "H4",
                "status": "OK",
                "data_status": "OK",
                "used_in_bias": True,
                "trend_direction": "BEAR" if final_bias == "SHORT_BIAS" else "BULL",
            },
            {
                "final_bias": final_bias,
                "timeframe": "M15",
                "status": "OK",
                "data_status": "OK",
                "used_in_bias": True,
                "trend_direction": "BEAR" if final_bias == "SHORT_BIAS" else "BULL",
            },
        ]
    ).to_csv(summary_path, index=False)

    def mtf_context(**kwargs):
        calls.append("mtf")
        assert "config_path" in kwargs
        return SimpleNamespace(status="OK", final_bias=final_bias, summary_path=summary_path, latest_path=tmp_path / "mtf.txt")

    return mtf_context


def test_v51_live_safe_cycle_non_esegue_v51_se_dati_stale(tmp_path):
    calls = []

    def update_data():
        calls.append("update")
        return [SimpleNamespace(status="OK")]

    def import_bridge():
        calls.append("import")
        return [SimpleNamespace(status="FILE_MISSING")]

    def freshness(*_args, **_kwargs):
        calls.append("freshness")
        return make_freshness("STALE")

    def execute_v51(**_kwargs):
        calls.append("v51")
        raise AssertionError("V51 must not run when data is stale")

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        update_data_fn=update_data,
        import_bridge_fn=import_bridge,
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_ok(calls),
        freshness_fn=freshness,
        execution_fn=execute_v51,
        now=NOW,
    )

    assert result.status == "DATA_STALE"
    assert result.v51_called is False
    assert result.timeframe_update_status == "OK"
    assert result.mtf_context_status == "OK"
    assert result.mtf_final_bias == "SHORT_BIAS"
    assert calls == ["update", "import", "timeframes", "mtf", "freshness"]

    audit = pd.read_csv(tmp_path / "v51_decision_audit.csv")
    latest_text = (tmp_path / "v51_decision_audit_latest.txt").read_text(encoding="utf-8")
    latest = audit.iloc[-1]
    assert latest["v51_called"] == False  # noqa: E712
    assert pd.isna(latest["v51_status"])
    assert latest["mtf_context_status"] == "OK"
    assert latest["mtf_final_bias"] == "SHORT_BIAS"
    assert latest["final_reason"].startswith("STALE")
    assert "Market data freshness" in latest_text
    assert "Final decision" in latest_text


def test_v51_live_safe_cycle_chiama_v51_se_dati_freschi(tmp_path):
    calls = []

    def update_data():
        calls.append("update")
        return [SimpleNamespace(status="OK")]

    def import_bridge():
        calls.append("import")
        return [SimpleNamespace(status="OK")]

    def freshness(*_args, **_kwargs):
        calls.append("freshness")
        return make_freshness("OK")

    def execute_v51(**kwargs):
        calls.append("v51")
        assert kwargs["dry_run"] is False
        assert kwargs["mtf_context_summary_path"] == "mtf_summary.csv"
        return SimpleNamespace(status="SENT", accepted=True, reason="demo order accepted")

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        execute_demo=True,
        update_data_fn=update_data,
        import_bridge_fn=import_bridge,
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_ok(calls),
        freshness_fn=freshness,
        execution_fn=execute_v51,
        now=NOW,
    )

    assert result.status == "V51_EXECUTED"
    assert result.v51_called is True
    assert result.v51_status == "SENT"
    assert result.timeframe_update_status == "OK"
    assert result.mtf_context_status == "OK"
    assert result.mtf_final_bias == "SHORT_BIAS"
    assert calls == ["update", "import", "timeframes", "mtf", "freshness", "v51"]


def test_v51_live_safe_cycle_audit_scrive_no_trade_con_mtf_e_candidate(tmp_path):
    calls = []
    reason = "no fresh live candidate on latest closed candle"

    def execute_v51(**kwargs):
        calls.append("v51")
        assert kwargs["dry_run"] is True
        return SimpleNamespace(
            status="NO_TRADE",
            accepted=False,
            reason=reason,
            now_utc=pd.Timestamp("2026-05-25 10:00:00", tz="UTC"),
            now_local="2026-05-25T12:00:00+02:00",
            mt5_timestamp_timezone="Europe/Rome",
            signal_id="V51-202605251145-SELL",
            side="SELL",
            latest_closed_candle_time=NOW - pd.Timedelta(minutes=15),
            latest_closed_candle_time_raw="2026-05-25T11:45:00",
            latest_closed_candle_time_utc=pd.Timestamp("2026-05-25 09:45:00", tz="UTC"),
            selected_candidate_time=NOW - pd.Timedelta(minutes=15),
            selected_candidate_time_raw="2026-05-25T11:45:00",
            selected_candidate_time_utc=pd.Timestamp("2026-05-25 09:45:00", tz="UTC"),
            candidate_age_minutes=0.0,
            candidate_time_basis="mt5_csv_naive_Europe/Rome_to_utc",
            time_alignment_status="OK",
            current_bid=2400.0,
            current_ask=2400.1,
            spread_points=10.0,
            expected_entry_price=2400.0,
            slippage_points=None,
            max_slippage_points=20.0,
            score=81.5,
            score_gap=18.0,
            risk_reward=1.25,
            session="NEW YORK",
            mtf_final_bias="SHORT_BIAS",
            mtf_filter_enabled=True,
            mtf_filter_passed=None,
            mtf_filter_reason="no_v51_candidate_to_filter",
        )

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path, use_mtf_context_filter=True),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        update_data_fn=lambda: calls.append("update") or [SimpleNamespace(status="OK")],
        import_bridge_fn=lambda: calls.append("import") or [SimpleNamespace(status="OK")],
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_with_summary(calls, tmp_path, final_bias="SHORT_BIAS"),
        freshness_fn=lambda *_args, **_kwargs: calls.append("freshness") or make_freshness("OK"),
        execution_fn=execute_v51,
        now=NOW,
    )

    audit = pd.read_csv(tmp_path / "v51_decision_audit.csv")
    latest_text = (tmp_path / "v51_decision_audit_latest.txt").read_text(encoding="utf-8")
    latest = audit.iloc[-1]
    assert result.status == "V51_EXECUTED"
    assert latest["mode"] == "DRY_RUN"
    assert latest["now_utc"] == "2026-05-25T10:00:00+00:00"
    assert latest["now_local"] == "2026-05-25T12:00:00+02:00"
    assert latest["mt5_timestamp_timezone"] == "Europe/Rome"
    assert latest["latest_closed_candle_time_raw"] == "2026-05-25T11:45:00"
    assert latest["latest_closed_candle_time_utc"] == "2026-05-25T09:45:00+00:00"
    assert latest["selected_candidate_time_raw"] == "2026-05-25T11:45:00"
    assert latest["selected_candidate_time_utc"] == "2026-05-25T09:45:00+00:00"
    assert latest["candidate_time_basis"] == "mt5_csv_naive_Europe/Rome_to_utc"
    assert latest["time_alignment_status"] == "OK"
    assert latest["v51_status"] == "NO_TRADE"
    assert latest["v51_accepted"] == False  # noqa: E712
    assert latest["mtf_context_status"] == "OK"
    assert latest["mtf_final_bias"] == "SHORT_BIAS"
    assert latest["mtf_filter_enabled"] == True  # noqa: E712
    assert latest["mtf_filter_reason"] == "no_v51_candidate_to_filter"
    assert latest["ai_reasoning_enabled"] == False  # noqa: E712
    assert latest["ai_reasoning_report_only"] == False  # noqa: E712
    assert latest["ai_final_bias"] == "SHORT_BIAS"
    assert latest["ai_confidence_score"] >= 70
    assert "V51 reasoning" in latest["ai_explanation"]
    assert latest["signal_id"] == "V51-202605251145-SELL"
    assert latest["side"] == "SELL"
    assert latest["expected_entry_price"] == 2400.0
    assert latest["max_slippage_points"] == 20.0
    assert latest["score"] == 81.5
    assert latest["risk_reward"] == 1.25
    assert latest["final_reason"] == reason
    assert "H4: trend=BEAR" in latest_text
    assert "AI reasoning" in latest_text
    assert reason in latest_text
    assert not (tmp_path / "v51_demo_orders.csv").exists()


def test_v51_live_safe_cycle_ai_report_only_non_blocca(tmp_path):
    calls = []
    dry_run_values = []

    def execute_v51(**kwargs):
        calls.append("v51")
        dry_run_values.append(kwargs["dry_run"])
        return SimpleNamespace(
            status="SENT",
            accepted=True,
            reason="demo order accepted",
            signal_id="V51-202605251145-SELL",
            side="SELL",
            latest_closed_candle_time=NOW - pd.Timedelta(minutes=15),
            selected_candidate_time=NOW - pd.Timedelta(minutes=15),
            candidate_age_minutes=0.0,
            current_bid=2400.0,
            current_ask=2400.1,
            spread_points=10.0,
            expected_entry_price=2400.0,
            slippage_points=2.0,
            max_slippage_points=20.0,
            score=88.0,
            score_gap=18.0,
            risk_reward=1.5,
            session="NEW YORK",
            mtf_final_bias="SHORT_BIAS",
            mtf_filter_enabled=True,
            mtf_filter_passed=True,
            mtf_filter_reason="mtf_direction_filter_passed",
        )

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path, use_ai_reasoning_filter=True, ai_reasoning_report_only=True),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        execute_demo=True,
        update_data_fn=lambda: calls.append("update") or [SimpleNamespace(status="OK")],
        import_bridge_fn=lambda: calls.append("import") or [SimpleNamespace(status="OK")],
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_with_summary(calls, tmp_path, final_bias="SHORT_BIAS"),
        freshness_fn=lambda *_args, **_kwargs: calls.append("freshness") or make_freshness("OK"),
        execution_fn=execute_v51,
        now=NOW,
    )

    audit = pd.read_csv(tmp_path / "v51_decision_audit.csv").iloc[-1]
    assert result.status == "V51_EXECUTED"
    assert result.v51_accepted is True
    assert dry_run_values == [False]
    assert audit["ai_reasoning_enabled"] == True  # noqa: E712
    assert audit["ai_reasoning_report_only"] == True  # noqa: E712
    assert audit["ai_allow_trade"] == True  # noqa: E712
    assert calls == ["update", "import", "timeframes", "mtf", "freshness", "v51"]


def test_v51_live_safe_cycle_ai_report_only_no_candidate_resta_no_trade(tmp_path):
    calls = []

    def execute_v51(**kwargs):
        calls.append("v51")
        assert kwargs["dry_run"] is True
        return SimpleNamespace(
            status="NO_TRADE",
            accepted=False,
            reason="no fresh live candidate on latest closed candle",
            latest_closed_candle_time=NOW - pd.Timedelta(minutes=15),
            selected_candidate_time=None,
            candidate_age_minutes=None,
            current_bid=2400.0,
            current_ask=2400.1,
            spread_points=10.0,
            max_slippage_points=20.0,
            mtf_final_bias="SHORT_BIAS",
            mtf_filter_enabled=True,
            mtf_filter_passed=None,
            mtf_filter_reason="no_v51_candidate_to_filter",
        )

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path, use_ai_reasoning_filter=True, ai_reasoning_report_only=True),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        update_data_fn=lambda: calls.append("update") or [SimpleNamespace(status="OK")],
        import_bridge_fn=lambda: calls.append("import") or [SimpleNamespace(status="OK")],
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_with_summary(calls, tmp_path, final_bias="SHORT_BIAS"),
        freshness_fn=lambda *_args, **_kwargs: calls.append("freshness") or make_freshness("OK"),
        execution_fn=execute_v51,
        now=NOW,
    )

    audit = pd.read_csv(tmp_path / "v51_decision_audit.csv").iloc[-1]
    assert result.status == "V51_EXECUTED"
    assert result.v51_status == "NO_TRADE"
    assert result.v51_accepted is False
    assert audit["ai_reasoning_enabled"] == True  # noqa: E712
    assert audit["ai_reasoning_report_only"] == True  # noqa: E712
    assert audit["ai_allow_trade"] == False  # noqa: E712
    assert "no_v51_candidate" in audit["ai_veto_reasons"]
    assert not (tmp_path / "v51_demo_orders.csv").exists()
    assert calls == ["update", "import", "timeframes", "mtf", "freshness", "v51"]


def test_v51_live_safe_cycle_ai_enabled_blocca_sotto_score_minimo(tmp_path):
    calls = []
    dry_run_values = []

    def execute_v51(**kwargs):
        calls.append("v51")
        dry_run_values.append(kwargs["dry_run"])
        return SimpleNamespace(
            status="DRY_RUN",
            accepted=True,
            reason="V51 dry-run accepted; no MT5 order was submitted.",
            dry_run=True,
            signal_id="V51-202605251145-SELL",
            side="SELL",
            latest_closed_candle_time=NOW - pd.Timedelta(minutes=15),
            selected_candidate_time=NOW - pd.Timedelta(minutes=15),
            candidate_age_minutes=0.0,
            current_bid=2400.0,
            current_ask=2400.1,
            spread_points=10.0,
            expected_entry_price=2400.0,
            slippage_points=2.0,
            max_slippage_points=20.0,
            score=62.0,
            score_gap=4.0,
            risk_reward=1.2,
            session="NEW YORK",
            mtf_final_bias="SHORT_BIAS",
            mtf_filter_enabled=True,
            mtf_filter_passed=True,
            mtf_filter_reason="mtf_direction_filter_passed",
        )

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(
            tmp_path,
            use_ai_reasoning_filter=True,
            ai_reasoning_report_only=False,
            min_trade_quality_score=90,
        ),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        execute_demo=True,
        update_data_fn=lambda: calls.append("update") or [SimpleNamespace(status="OK")],
        import_bridge_fn=lambda: calls.append("import") or [SimpleNamespace(status="OK")],
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_with_summary(calls, tmp_path, final_bias="SHORT_BIAS"),
        freshness_fn=lambda *_args, **_kwargs: calls.append("freshness") or make_freshness("OK"),
        execution_fn=execute_v51,
        now=NOW,
    )

    audit = pd.read_csv(tmp_path / "v51_decision_audit.csv").iloc[-1]
    assert result.status == "V51_EXECUTED"
    assert result.v51_status == "NO_TRADE"
    assert result.v51_accepted is False
    assert result.reason.startswith("ai_reasoning_filter_blocked")
    assert dry_run_values == [True]
    assert audit["ai_reasoning_enabled"] == True  # noqa: E712
    assert audit["ai_reasoning_report_only"] == False  # noqa: E712
    assert audit["ai_allow_trade"] == False  # noqa: E712
    assert "ai_trade_quality_below_minimum" in audit["ai_veto_reasons"]


def test_v51_live_safe_cycle_blocca_live_reale(tmp_path):
    calls = []

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path, allow_real_live=True),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        update_data_fn=lambda: calls.append("update"),
        import_bridge_fn=lambda: calls.append("import"),
        update_timeframes_fn=lambda: calls.append("timeframes"),
        mtf_context_fn=lambda **_kwargs: calls.append("mtf"),
        freshness_fn=lambda *_args, **_kwargs: make_freshness("OK"),
        execution_fn=lambda **_kwargs: calls.append("v51"),
        now=NOW,
    )

    assert result.status == "SAFETY_ERROR"
    assert "allow_real_live" in result.reason
    assert result.v51_called is False
    assert calls == []


def test_v51_live_safe_cycle_data_update_avviene_prima_della_strategia(tmp_path):
    calls = []

    result = script.run_v51_live_safe_cycle(
        config_path=write_v51_config(tmp_path),
        log_path=tmp_path / "cycle.log",
        output_dir=tmp_path,
        update_data_fn=lambda: calls.append("update") or [SimpleNamespace(status="OK")],
        import_bridge_fn=lambda: calls.append("import") or [SimpleNamespace(status="OK")],
        update_timeframes_fn=timeframe_update_ok(calls),
        mtf_context_fn=mtf_context_ok(calls),
        freshness_fn=lambda *_args, **_kwargs: calls.append("freshness") or make_freshness("OK"),
        execution_fn=lambda **_kwargs: calls.append("v51") or SimpleNamespace(status="DRY_RUN", accepted=True, reason="ok"),
        now=NOW,
    )

    assert result.status == "V51_EXECUTED"
    assert calls == ["update", "import", "timeframes", "mtf", "freshness", "v51"]
