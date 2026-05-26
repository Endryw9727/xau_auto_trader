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


def write_v51_config(tmp_path, **overrides):
    raw = yaml.safe_load(open("config/strategy_v51.yaml", encoding="utf-8"))
    raw.update({"allow_real_live": False, "demo_only": True})
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
