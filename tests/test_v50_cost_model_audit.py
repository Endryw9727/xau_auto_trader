from pathlib import Path

import pandas as pd

from scripts import audit_v50_cost_model as audit_script
from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy_lab import v50_cost_aware as cost_aware


def make_result(strategy_name: str = "v50_proxy_balanced_candidate") -> BacktestResult:
    trades = pd.DataFrame(
        {
            "strategy_name": [strategy_name, strategy_name],
            "entry_time": pd.to_datetime(["2025-01-01 09:00:00", "2025-01-01 14:00:00"]),
            "side": ["BUY", "SELL"],
            "session": ["LONDON", "NEW YORK"],
            "entry_price": [100.0, 110.0],
            "stop_loss": [98.0, 112.0],
            "take_profit": [104.0, 106.0],
            "position_size": [1.0, 2.0],
            "score_long": [80.0, 60.0],
            "score_short": [55.0, 82.0],
            "profit_loss": [12.0, -5.0],
            "pnl": [12.0, -5.0],
        }
    )
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    return BacktestResult(trades=trades, metrics=metrics, final_balance=1007.0)


def test_cost_profiles_are_static_and_complete():
    profiles = cost_aware.build_cost_profiles()
    names = [profile.name for profile in profiles]

    assert names == list(cost_aware.COST_PROFILE_NAMES)
    assert all(profile.spread_points >= 0 for profile in profiles)
    assert all(profile.slippage_points >= 0 for profile in profiles)
    assert all(profile.commission_per_trade >= 0 for profile in profiles)


def test_cost_model_audit_exports_expected_columns(tmp_path):
    profile = cost_aware.CostProfile("cost_test", spread_points=0.10, slippage_points=0.15, commission_per_trade=0.50)
    audit = cost_aware.build_cost_model_audit(
        {"v50_proxy_balanced_candidate": make_result()},
        profiles=[profile],
        value_per_point=1.0,
    )
    output_path = cost_aware.export_cost_model_audit(audit, tmp_path / "audit.csv")

    assert output_path.exists()
    assert set(cost_aware.AUDIT_COLUMNS).issubset(audit.columns)
    variant_row = audit[(audit["group_type"] == "variant")].iloc[0]
    assert variant_row["backtester_slippage_applications"] == 2
    assert variant_row["backtester_commission_applications"] == 1
    assert bool(variant_row["spread_native_supported"]) is False
    assert bool(variant_row["partial_exits_supported"]) is False
    assert variant_row["total_cost"] > 0


def test_cost_model_audit_script_runs(monkeypatch, tmp_path, capsys):
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    output_path = tmp_path / "audit.csv"

    monkeypatch.setattr(audit_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(audit_script, "DEFAULT_COST_MODEL_AUDIT_PATH", output_path)
    monkeypatch.setattr(audit_script, "load_csv_data", lambda _path: pd.DataFrame({"Close": [1.0]}))
    monkeypatch.setattr(
        audit_script,
        "run_source_variant_backtests",
        lambda **_kwargs: {"v50_proxy_balanced_candidate": make_result()},
    )

    audit_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Cost Model Audit" in output
    assert "No candidate was promoted automatically." in output


def test_cost_model_sources_are_research_only():
    for path in [
        Path("src/strategy_lab/v50_cost_aware.py"),
        Path("scripts/audit_v50_cost_model.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
