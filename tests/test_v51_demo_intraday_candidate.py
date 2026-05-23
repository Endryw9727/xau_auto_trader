from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_proxy_candidate, strategy_v51_demo_intraday as v51


def make_v51_feature_data(rows: int = 8, start: str = "2026-01-05 10:00:00") -> pd.DataFrame:
    index = pd.date_range(start, periods=rows, freq="15min")
    return pd.DataFrame(
        {
            "Open": [2399.8] * rows,
            "High": [2401.0] * rows,
            "Low": [2399.0] * rows,
            "Close": [2400.0] * rows,
            "Volume": [1000.0] * rows,
            "ATR_14": [1.0] * rows,
            "ADX_14": [20.0] * rows,
            "v50_adx": [20.0] * rows,
            "v50_ema21": [2399.0] * rows,
            "v50_score_long": [65.0] * rows,
            "v50_score_short": [20.0] * rows,
            "v50_quality_long_ok": [True] * rows,
            "v50_quality_short_ok": [False] * rows,
            "v50_setup_long": [True] * rows,
            "v50_setup_short": [False] * rows,
            "v50_chop_block": [False] * rows,
            "v50_long_chase_block": [False] * rows,
            "v50_late_long_impulse": [False] * rows,
            "v50_session": ["LONDON"] * rows,
        },
        index=index,
    )


def test_v51_non_usa_dati_futuri():
    data = make_v51_feature_data(rows=6)
    mutated = data.copy()
    mutated.loc[mutated.index[-1], ["Close", "v50_score_long", "v50_score_short"]] = [1000.0, 0.0, 95.0]

    base_log = v51.build_demo_intraday_decision_log(data)
    mutated_log = v51.build_demo_intraday_decision_log(mutated)
    candle_time = data.index[2].isoformat()
    base_row = base_log[base_log["candle_time"] == candle_time].iloc[0]
    mutated_row = mutated_log[mutated_log["candle_time"] == candle_time].iloc[0]

    assert base_row["decision"] == mutated_row["decision"]
    assert base_row["side"] == mutated_row["side"]
    assert base_row["score"] == mutated_row["score"]


def test_v51_non_apre_piu_di_max_trades_per_day():
    data = make_v51_feature_data(rows=6)

    log = v51.build_demo_intraday_decision_log(data)

    assert int((log["decision"] == "ACCEPTED").sum()) == 2
    assert int(log["reason"].str.contains("max trades per day").sum()) == 4


def test_v51_non_apre_senza_sl_tp():
    data = make_v51_feature_data(rows=3)

    log = v51.build_demo_intraday_decision_log(data)
    accepted = log[log["decision"] == "ACCEPTED"]

    assert not accepted.empty
    assert accepted["stop_loss"].notna().all()
    assert accepted["take_profit"].notna().all()
    assert (accepted["risk_reward"] >= 1.2).all()


def test_v51_non_usa_martingala():
    data = make_v51_feature_data(rows=4)

    log = v51.build_demo_intraday_decision_log(data)
    accepted = log[log["decision"] == "ACCEPTED"]

    assert accepted["lot_size"].nunique() == 1
    assert float(accepted["lot_size"].iloc[0]) == v51.load_v51_config().fixed_lot_size


def test_v51_non_usa_grid():
    data = make_v51_feature_data(rows=4)

    log = v51.build_demo_intraday_decision_log(data)
    accepted = log[log["decision"] == "ACCEPTED"]

    assert accepted["signal_id"].is_unique
    assert accepted.groupby("candle_time").size().max() == 1


def test_v51_produce_piu_candidate_della_v50_sullo_stesso_dataset():
    data = make_v51_feature_data(rows=6)
    v50_signals = [
        strategy_v50_proxy_candidate.generate_signal(data.iloc[: index + 1], StrategyConfig())
        for index in range(len(data))
    ]
    v50_candidates = sum(signal.side in {"BUY", "SELL"} for signal in v50_signals)

    v51_log = v51.build_demo_intraday_decision_log(data)
    v51_candidates = int(v51_log["side"].isin(["BUY", "SELL"]).sum())

    assert v50_candidates == 0
    assert v51_candidates > v50_candidates


def test_v51_rispetta_spread_slippage_guard():
    data = make_v51_feature_data(rows=3)
    spread_config = replace(
        v51.load_v51_config(),
        spread_cost=1.0,
        max_spread_cost=0.5,
        slippage_estimate=0.1,
        max_slippage_estimate=0.5,
    )

    spread_log = v51.build_demo_intraday_decision_log(data, spread_config)

    assert not (spread_log["decision"] == "ACCEPTED").any()
    assert "spread cost" in str(spread_log.iloc[0]["reason"])

    slippage_config = replace(
        v51.load_v51_config(),
        spread_cost=0.0,
        max_spread_cost=0.5,
        slippage_estimate=1.0,
        max_slippage_estimate=0.5,
    )
    slippage_log = v51.build_demo_intraday_decision_log(data, slippage_config)

    assert not (slippage_log["decision"] == "ACCEPTED").any()
    assert "slippage estimate" in str(slippage_log.iloc[0]["reason"])


def test_v51_blocca_se_esiste_posizione_aperta():
    decision = v51.evaluate_latest_demo_intraday_candidate(
        make_v51_feature_data(rows=1),
        open_positions=1,
    )

    assert decision["decision"] == "REJECTED"
    assert "max open positions" in decision["reason"]


def test_v51_blocca_trade_se_allow_real_live_true(tmp_path):
    raw = yaml.safe_load(Path("config/strategy_v51.yaml").read_text(encoding="utf-8"))
    raw["allow_real_live"] = True
    path = tmp_path / "strategy_v51.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PermissionError, match="allow_real_live"):
        v51.load_v51_config(path)


def test_v51_log_contiene_campi_operativi_richiesti():
    log = v51.build_demo_intraday_decision_log(make_v51_feature_data(rows=3))

    assert list(log.columns) == v51.V51_LOG_COLUMNS


def test_v50_vs_v51_report_contiene_metriche_richieste():
    v50_log = pd.DataFrame(columns=v51.V51_LOG_COLUMNS)
    v51_log = v51.build_demo_intraday_decision_log(make_v51_feature_data(rows=4))

    report = v51.build_v50_vs_v51_report(v50_log, v51_log)

    assert list(report.columns) == v51.V51_COMPARISON_COLUMNS
    assert "demo_intraday_candidate" in set(report["strategy_name"])
    assert report.loc[report["strategy_name"] == "demo_intraday_candidate", "accepted_signals"].iloc[0] == 2
