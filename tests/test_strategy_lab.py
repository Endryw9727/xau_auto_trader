import pandas as pd

from src.backtesting.backtester import BacktestConfig
from src.lab.strategy_lab import StrategyVariant, run_strategy_lab as run_legacy_strategy_lab
from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v1, strategy_v2, strategy_v3
from src.strategy_lab.lab import COMPARISON_FILENAME, get_default_strategy_specs, run_strategy_lab


def make_signal_ready_data(latest_hour: int = 14) -> pd.DataFrame:
    dates = pd.date_range(f"2026-01-01 {latest_hour - 4:02d}:00:00", periods=5, freq="h")

    return pd.DataFrame(
        {
            "Close": [100.0, 101.0, 102.0, 101.0, 103.0],
            "EMA_20": [99.0, 100.0, 101.0, 102.0, 102.0],
            "EMA_50": [98.0, 99.0, 100.0, 100.0, 100.0],
            "RSI_14": [55.0] * 5,
            "ATR_14": [1.0] * 5,
            "ADX_14": [25.0] * 5,
        },
        index=dates,
    )


def make_strategy_lab_data(rows: int = 280) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    price = 2350.0
    close = []

    for i in range(rows):
        if i < 120:
            price += 0.25
        elif i < 210:
            price -= 0.18
        else:
            price += 0.12

        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 1.2 for value in close],
            "Low": [value - 1.2 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def test_strategy_v1_wraps_existing_strategy():
    signal = strategy_v1.generate_signal(make_signal_ready_data(), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None


def test_strategy_v2_blocks_off_session_and_allows_new_york():
    off_session_signal = strategy_v2.generate_signal(
        make_signal_ready_data(latest_hour=13),
        StrategyConfig(),
    )
    new_york_signal = strategy_v2.generate_signal(
        make_signal_ready_data(latest_hour=14),
        StrategyConfig(),
    )

    assert off_session_signal.side == "NO_TRADE"
    assert "Session filtered out" in off_session_signal.reason
    assert new_york_signal.side == "BUY"
    assert "Session=New York" in new_york_signal.reason


def test_strategy_v3_generates_simple_momentum_pullback_buy():
    signal = strategy_v3.generate_signal(make_signal_ready_data(), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.risk_reward == 2.0
    assert "MTF momentum pullback placeholder" in signal.reason


def test_strategy_lab_exports_comparison_csv(tmp_path):
    df = make_strategy_lab_data()
    config = BacktestConfig(warmup_candles=60, allowed_sessions=None)

    result = run_strategy_lab(
        df=df,
        strategy_config=StrategyConfig(),
        backtest_config=config,
        output_dir=tmp_path,
    )

    expected_names = {
        "existing_strategy",
        "session_filtered_strategy",
        "mtf_momentum_pullback_strategy",
    }
    saved = pd.read_csv(tmp_path / COMPARISON_FILENAME)

    assert result.report_path == tmp_path / COMPARISON_FILENAME
    assert result.report_path.exists()
    assert set(result.comparison["strategy_name"]) == expected_names
    assert set(saved["strategy_name"]) == expected_names
    assert len(get_default_strategy_specs()) == 3
    assert "net_profit" in saved.columns
    assert "max_drawdown" in saved.columns


def test_legacy_strategy_lab_entrypoint_still_runs():
    df = make_strategy_lab_data()
    variants = [
        StrategyVariant(
            name="legacy_smoke",
            allowed_sessions=["Asia", "London", "New York", "Off Session"],
            risk_per_trade=0.005,
            min_risk_reward=2.0,
            warmup_candles=60,
        )
    ]

    result = run_legacy_strategy_lab(df, variants=variants)

    assert len(result) == 1
    assert result.iloc[0]["name"] == "legacy_smoke"
    assert "profit_factor" in result.columns
