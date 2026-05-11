from pathlib import Path
import inspect

import pandas as pd

from src.settings import load_yaml_config
from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_proxy_candidate
from src.strategy_lab.lab import get_default_strategy_specs
from src.strategy_lab.strategy_v50_candidates import FINAL_CANDIDATE_STRATEGY_NAMES
from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    _side_allowed,
    _side_setup_ok,
    validate_variant_no_leakage,
)
from src.strategy_lab.v50_stress_test import FINAL_CANDIDATE_GENERATORS


def make_v50_feature_window(score_long: float = 82.0, score_short: float = 20.0) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp("2025-01-01 11:00:00")])
    return pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.0],
            "Volume": [1.0],
            "ATR_14": [1.0],
            "v50_score_long": [score_long],
            "v50_score_short": [score_short],
            "v50_quality_long_ok": [True],
            "v50_quality_short_ok": [False],
            "v50_setup_long": [True],
            "v50_setup_short": [False],
            "v50_session": ["LONDON"],
        },
        index=index,
    )


def test_proxy_balanced_candidate_is_available_in_strategy_lab_and_final_tools():
    names = {spec.name for spec in get_default_strategy_specs()}

    assert strategy_v50_proxy_candidate.STRATEGY_NAME == "v50_proxy_balanced_candidate"
    assert strategy_v50_proxy_candidate.STRATEGY_NAME in names
    assert strategy_v50_proxy_candidate.STRATEGY_NAME in FINAL_CANDIDATE_STRATEGY_NAMES
    assert strategy_v50_proxy_candidate.STRATEGY_NAME in FINAL_CANDIDATE_GENERATORS


def test_proxy_balanced_candidate_freezes_expected_realtime_filters():
    variant = strategy_v50_proxy_candidate.PROXY_BALANCED_VARIANT

    validate_variant_no_leakage(variant)
    assert strategy_v50_proxy_candidate.SOURCE_VARIANT_NAME == "proxy_balanced_combo"
    assert variant.min_score_gap == 10.0
    assert variant.short_min_score == 75.0
    assert variant.blocked_score_bucket_hours == (("score_70_74", (11, 12, 20)),)


def test_proxy_balanced_candidate_blocks_weak_score_bucket_in_worst_hours():
    signal = strategy_v50_proxy_candidate.generate_signal(
        make_v50_feature_window(score_long=72.0, score_short=20.0),
        StrategyConfig(),
    )

    assert signal.side == "NO_TRADE"
    assert "v50_proxy_balanced_candidate" in signal.reason


def test_proxy_balanced_candidate_can_emit_valid_research_signal():
    signal = strategy_v50_proxy_candidate.generate_signal(
        make_v50_feature_window(score_long=84.0, score_short=20.0),
        StrategyConfig(),
    )

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.risk_reward == 2.0


def test_proxy_candidate_signal_filters_do_not_reference_future_outcome_columns():
    forbidden = ("bars_in_trade", "pnl", "exit_time", "trade_result", "profit", "drawdown")
    source = (
        Path("src/strategy_lab/strategy_v50_proxy_candidate.py").read_text(encoding="utf-8")
        + inspect.getsource(_side_allowed)
        + inspect.getsource(_side_setup_ok)
    ).lower()

    assert load_yaml_config()["trading"]["live_mode"] is False
    for term in forbidden:
        assert term not in source


def test_proxy_candidate_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/strategy_v50_proxy_candidate.py"),
        Path("scripts/analyze_v50_proxy_candidate_selection.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
