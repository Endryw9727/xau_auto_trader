from pathlib import Path

import pandas as pd

from src.settings import load_yaml_config
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_candidates, v50_edge_filters
from src.strategy_lab.lab import get_default_strategy_specs


def make_candidate_data() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01 10:00:00", periods=6, freq="15min")
    close = [2350.0 + index * 0.2 for index in range(6)]
    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 0.8 for value in close],
            "Low": [value - 0.8 for value in close],
            "Close": close,
            "Volume": [1000] * 6,
        },
        index=dates,
    )


def make_v50_signal(side: str = "BUY", session: str = "LONDON") -> TradingSignal:
    return TradingSignal(
        timestamp=pd.Timestamp("2025-01-01 10:15:00").to_pydatetime(),
        symbol="XAUUSD",
        timeframe="15m",
        side=side,
        entry_price=2350.0,
        stop_loss=2348.0 if side == "BUY" else 2352.0,
        take_profit=2354.0 if side == "BUY" else 2346.0,
        risk_reward=2.0,
        confidence=80.0,
        reason=f"V50 Pine technical approximation | Side={side} | score=80.0 | session={session}",
    )


def test_final_v50_candidates_are_available_in_strategy_lab():
    names = {spec.name for spec in get_default_strategy_specs()}

    assert set(strategy_v50_candidates.FINAL_CANDIDATE_STRATEGY_NAMES).issubset(names)


def test_final_low_risk_is_london_only(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="BUY", session="NEW YORK"),
    )

    signal = strategy_v50_candidates.generate_final_low_risk_signal(make_candidate_data(), StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "session=NEW YORK not allowed" in signal.reason


def test_final_balanced_long_new_york_and_short_london_rules(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="BUY", session="NEW YORK"),
    )
    long_signal = strategy_v50_candidates.generate_final_balanced_signal(make_candidate_data(), StrategyConfig())

    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="SELL", session="NEW YORK"),
    )
    short_new_york_signal = strategy_v50_candidates.generate_final_balanced_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="SELL", session="LONDON"),
    )
    short_london_signal = strategy_v50_candidates.generate_final_balanced_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    assert long_signal.side == "BUY"
    assert short_new_york_signal.side == "NO_TRADE"
    assert "short session=NEW YORK not allowed" in short_new_york_signal.reason
    assert short_london_signal.side == "SELL"


def test_final_growth_blocks_asia_london(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="BUY", session="ASIA/LONDON"),
    )

    signal = strategy_v50_candidates.generate_final_growth_signal(make_candidate_data(), StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "session=ASIA/LONDON blocked" in signal.reason


def test_final_candidates_research_only_and_live_mode_default_false():
    config = load_yaml_config()
    checked_files = [
        Path("src/strategy_lab/strategy_v50_candidates.py"),
        Path("src/strategy_lab/v50_stress_test.py"),
        Path("src/strategy_lab/v50_monte_carlo.py"),
        Path("scripts/run_v50_stress_test.py"),
        Path("scripts/run_v50_monte_carlo.py"),
        Path("scripts/analyze_v50_final_selection.py"),
    ]

    assert config["trading"]["live_mode"] is False
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
