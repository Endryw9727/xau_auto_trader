import pandas as pd

from scripts.run_strategy_lab import QUICK_CANDLES, parse_args, select_strategy_lab_data
from src.backtesting.backtester import BacktestConfig
from src.lab.strategy_lab import StrategyVariant, run_strategy_lab as run_legacy_strategy_lab
from src.strategy.rules import StrategyConfig
from src.strategy_lab import (
    strategy_v1,
    strategy_v2,
    strategy_v3,
    strategy_v4,
    strategy_v5,
    strategy_v6,
    strategy_v50_pine,
)
from src.strategy_lab.lab import COMPARISON_FILENAME, get_default_strategy_specs, run_strategy_lab


def make_signal_ready_data(latest_hour: int = 14) -> pd.DataFrame:
    dates = pd.date_range(f"2026-01-01 {latest_hour - 5:02d}:00:00", periods=6, freq="h")

    return pd.DataFrame(
        {
            "Open": [99.8, 100.7, 101.7, 101.6, 101.2, 102.4],
            "High": [100.4, 101.4, 102.4, 102.1, 101.7, 103.0],
            "Low": [99.6, 100.5, 101.5, 100.9, 100.8, 101.9],
            "Close": [100.0, 101.0, 102.0, 101.6, 101.0, 103.0],
            "EMA_20": [99.0, 99.5, 100.0, 101.0, 102.0, 102.5],
            "EMA_50": [98.0, 98.5, 99.0, 99.5, 100.0, 100.5],
            "EMA_200": [95.0, 95.2, 95.4, 95.6, 95.8, 96.0],
            "RSI_14": [55.0] * 6,
            "ATR_14": [1.0] * 6,
            "ADX_14": [25.0] * 6,
            "PLUS_DI_14": [30.0] * 6,
            "MINUS_DI_14": [15.0] * 6,
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


def test_strategy_v4_generates_strict_offsession_signal():
    signal = strategy_v4.generate_signal(make_signal_ready_data(latest_hour=13), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.risk_reward == 2.0
    assert "Strict Off Session MTF momentum pullback" in signal.reason


def test_strategy_v4_blocks_london_and_reduces_signals_vs_base_mtf():
    windows = [
        make_signal_ready_data(latest_hour=10),
        make_signal_ready_data(latest_hour=13),
        make_signal_ready_data(latest_hour=14),
    ]

    base_signals = [strategy_v3.generate_signal(window, StrategyConfig()) for window in windows]
    strict_signals = [strategy_v4.generate_signal(window, StrategyConfig()) for window in windows]

    assert strict_signals[0].side == "NO_TRADE"
    assert "Session=London" in strict_signals[0].reason
    assert strict_signals[1].side == "BUY"
    assert strict_signals[2].side == "NO_TRADE"
    assert sum(signal.side in {"BUY", "SELL"} for signal in strict_signals) < sum(
        signal.side in {"BUY", "SELL"} for signal in base_signals
    )


def test_strategy_v4_blocks_unclear_momentum():
    unclear_data = make_signal_ready_data(latest_hour=13)
    unclear_data.loc[unclear_data.index[-1], "ADX_14"] = 18.0

    signal = strategy_v4.generate_signal(unclear_data, StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "momentum filter blocked" in signal.reason


def make_feature_filtered_signal_data() -> pd.DataFrame:
    data = make_signal_ready_data()
    data["trend_regime"] = "bullish"
    data["candle_regime"] = "normal"
    data["adx"] = 22.0
    return data


def test_strategy_v5_generates_valid_feature_filtered_signal():
    signal = strategy_v5.generate_signal(make_feature_filtered_signal_data(), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert "Feature filtered" in signal.reason


def test_strategy_v5_blocks_neutral_trend_regime():
    data = make_feature_filtered_signal_data()
    data.loc[data.index[-1], "trend_regime"] = "neutral"

    signal = strategy_v5.generate_signal(data, StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "neutral trend regime" in signal.reason


def test_strategy_v5_blocks_impulse_candle_regime():
    data = make_feature_filtered_signal_data()
    data.loc[data.index[-1], "candle_regime"] = "impulse"

    signal = strategy_v5.generate_signal(data, StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "candle regime=impulse" in signal.reason


def test_strategy_v6_generates_relaxed_candidate_signal():
    data = make_feature_filtered_signal_data()
    data.loc[data.index[-1], "trend_regime"] = "neutral"
    data.loc[data.index[-1], "candle_regime"] = "impulse"
    data.loc[data.index[-1], "adx"] = 1.0
    data.loc[data.index[-1], "ADX_14"] = 1.0

    signal = strategy_v6.generate_signal(data, StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert "Feature filtered" in signal.reason


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
        "mtf_strict_offsession_strategy",
        "mtf_feature_filtered_strategy",
        "mtf_relaxed_offasia_strategy",
        "v50_pine_technical_strategy",
        "v50_pine_mtf_strategy",
    }
    saved = pd.read_csv(tmp_path / COMPARISON_FILENAME)
    strict_row = saved[saved["strategy_name"] == "mtf_strict_offsession_strategy"].iloc[0]
    relaxed_row = saved[saved["strategy_name"] == "mtf_relaxed_offasia_strategy"].iloc[0]

    assert result.report_path == tmp_path / COMPARISON_FILENAME
    assert result.report_path.exists()
    assert set(result.comparison["strategy_name"]) == expected_names
    assert set(saved["strategy_name"]) == expected_names
    assert len(get_default_strategy_specs()) == 8
    assert "net_profit" in saved.columns
    assert "max_drawdown" in saved.columns
    assert strict_row["risk_per_trade"] == 0.0025
    assert strict_row["min_risk_reward"] == 2.0
    assert strict_row["allowed_sessions"] == "Off Session"
    assert relaxed_row["risk_per_trade"] == 0.005
    assert relaxed_row["min_risk_reward"] == 2.0
    assert relaxed_row["allowed_sessions"] == "Off Session, Asia"


def test_strategy_lab_progress_mode_runs(tmp_path, capsys):
    df = make_strategy_lab_data()
    config = BacktestConfig(warmup_candles=60, allowed_sessions=None)

    result = run_strategy_lab(
        df=df,
        strategy_config=StrategyConfig(),
        backtest_config=config,
        output_dir=tmp_path,
        show_progress=True,
    )
    captured = capsys.readouterr().out

    assert "Running strategy:" in captured
    assert "Strategy Lab total time:" in captured
    assert "mtf_feature_filtered_strategy" in set(result.comparison["strategy_name"])
    assert "mtf_relaxed_offasia_strategy" in set(result.comparison["strategy_name"])


def test_run_strategy_lab_quick_selection_uses_latest_default_window():
    df = make_strategy_lab_data(rows=QUICK_CANDLES + 25)

    selected = select_strategy_lab_data(df)

    assert len(selected) == QUICK_CANDLES
    assert selected.index[0] == df.index[-QUICK_CANDLES]


def test_run_strategy_lab_cli_options():
    full_args = parse_args(["--full"])
    candle_args = parse_args(["--candles", "20000"])

    assert full_args.full is True
    assert candle_args.candles == 20000


def test_strategy_v5_declares_required_history():
    assert strategy_v5.generate_signal.required_history_candles == strategy_v5.REQUIRED_HISTORY_CANDLES


def test_strategy_lab_research_only_without_live_or_api_references():
    checked_files = [
        "src/strategy_lab/strategy_v4.py",
        "src/strategy_lab/strategy_v5.py",
        "src/strategy_lab/strategy_v6.py",
        "src/strategy_lab/strategy_v50_pine.py",
        "src/strategy_lab/v50_mtf_features.py",
        "src/strategy_lab/lab.py",
        "scripts/run_strategy_lab.py",
        "scripts/run_v50_mtf_lab.py",
    ]

    for path in checked_files:
        source = open(path, encoding="utf-8").read()
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source


def test_strategy_lab_includes_v50_pine_candidate():
    names = {spec.name for spec in get_default_strategy_specs()}

    assert strategy_v50_pine.STRATEGY_NAME in names
    assert strategy_v50_pine.MTF_STRATEGY_NAME in names


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
