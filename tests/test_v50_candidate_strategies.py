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
        reason=(
            "V50 Pine technical approximation | "
            f"Side={side} | score=80.0 | opposite_score=20.0 | session={session}"
        ),
    )


def test_v50_candidate_strategies_are_available_in_strategy_lab():
    names = {spec.name for spec in get_default_strategy_specs()}

    assert set(strategy_v50_candidates.OFFICIAL_CANDIDATE_STRATEGY_NAMES).issubset(names)
    assert strategy_v50_candidates.strategy_v50_pine.STRATEGY_NAME in names


def test_v50_low_risk_london_candidate_allows_london_signal(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="BUY", session="LONDON"),
    )

    signal = strategy_v50_candidates.generate_low_risk_london_signal(make_candidate_data(), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None


def test_v50_balanced_no_asia_london_blocks_short_and_asia_london(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="SELL", session="LONDON"),
    )
    short_signal = strategy_v50_candidates.generate_balanced_no_asia_london_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="BUY", session="ASIA/LONDON"),
    )
    asia_london_signal = strategy_v50_candidates.generate_balanced_no_asia_london_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    assert short_signal.side == "NO_TRADE"
    assert "side=SELL not allowed" in short_signal.reason
    assert asia_london_signal.side == "NO_TRADE"
    assert "session=ASIA/LONDON blocked" in asia_london_signal.reason


def test_v50_growth_candidate_limits_shorts_to_london(monkeypatch):
    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="SELL", session="NEW YORK"),
    )
    blocked_signal = strategy_v50_candidates.generate_growth_long_all_short_london_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    monkeypatch.setattr(
        v50_edge_filters.strategy_v50_pine,
        "generate_signal",
        lambda _df, _config: make_v50_signal(side="SELL", session="LONDON"),
    )
    allowed_signal = strategy_v50_candidates.generate_growth_long_all_short_london_signal(
        make_candidate_data(),
        StrategyConfig(),
    )

    assert blocked_signal.side == "NO_TRADE"
    assert "short session=NEW YORK not allowed" in blocked_signal.reason
    assert allowed_signal.side == "SELL"


def test_v50_candidates_do_not_auto_promote_and_keep_live_mode_default_false():
    config = load_yaml_config()
    source = Path("scripts/analyze_v50_candidate_edges.py").read_text(encoding="utf-8")

    assert config["trading"]["live_mode"] is False
    assert "No strategy was promoted automatically." in source


def test_v50_candidate_files_are_research_only_without_broker_or_api_references():
    checked_files = [
        Path("src/strategy_lab/strategy_v50_candidates.py"),
        Path("src/strategy_lab/v50_edge_filters.py"),
        Path("scripts/analyze_v50_candidate_edges.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
