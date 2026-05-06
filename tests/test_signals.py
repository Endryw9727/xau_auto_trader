import pandas as pd
import pytest

from src.strategy.rules import StrategyConfig, calculate_trade_levels, get_trend_bias
from src.strategy.signals import generate_signal, signal_to_dict


def make_signal_data(side: str = "BUY") -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=5, freq="min")

    if side == "BUY":
        close = [100, 101, 102, 103, 104]
        ema_20 = [99, 100, 101, 102, 103]
        ema_50 = [98, 99, 100, 101, 102]
        rsi = [50, 52, 54, 56, 58]
        plus_di = [25, 26, 27, 28, 29]
        minus_di = [15, 14, 13, 12, 11]
    elif side == "SELL":
        close = [104, 103, 102, 101, 100]
        ema_20 = [105, 104, 103, 102, 101]
        ema_50 = [106, 105, 104, 103, 102]
        rsi = [50, 48, 46, 44, 42]
        plus_di = [15, 14, 13, 12, 11]
        minus_di = [25, 26, 27, 28, 29]
    else:
        close = [100, 100, 100, 100, 100]
        ema_20 = [100, 100, 100, 100, 100]
        ema_50 = [100, 100, 100, 100, 100]
        rsi = [50, 50, 50, 50, 50]
        plus_di = [20, 20, 20, 20, 20]
        minus_di = [20, 20, 20, 20, 20]

    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [1000] * 5,
            "EMA_20": ema_20,
            "EMA_50": ema_50,
            "RSI_14": rsi,
            "ATR_14": [1.0] * 5,
            "ADX_14": [25.0] * 5,
            "PLUS_DI_14": plus_di,
            "MINUS_DI_14": minus_di,
        },
        index=dates,
    )


def test_get_trend_bias_buy():
    df = make_signal_data("BUY")

    bias = get_trend_bias(df.iloc[-1])

    assert bias == "BUY"


def test_get_trend_bias_sell():
    df = make_signal_data("SELL")

    bias = get_trend_bias(df.iloc[-1])

    assert bias == "SELL"


def test_get_trend_bias_no_trade():
    df = make_signal_data("NO_TRADE")

    bias = get_trend_bias(df.iloc[-1])

    assert bias == "NO_TRADE"


def test_generate_buy_signal():
    df = make_signal_data("BUY")
    config = StrategyConfig(min_risk_reward=2.0)

    signal = generate_signal(df, config)

    assert signal.side == "BUY"
    assert signal.entry_price is not None
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.risk_reward >= 2.0
    assert signal.confidence > 0


def test_generate_sell_signal():
    df = make_signal_data("SELL")
    config = StrategyConfig(min_risk_reward=2.0)

    signal = generate_signal(df, config)

    assert signal.side == "SELL"
    assert signal.entry_price is not None
    assert signal.stop_loss is not None
    assert signal.take_profit is not None
    assert signal.risk_reward >= 2.0
    assert signal.confidence > 0


def test_generate_no_trade_when_adx_low():
    df = make_signal_data("BUY")
    df["ADX_14"] = 10.0
    config = StrategyConfig(min_adx=18.0)

    signal = generate_signal(df, config)

    assert signal.side == "NO_TRADE"
    assert "ADX ok=False" in signal.reason


def test_generate_no_trade_when_rsi_filter_fails():
    df = make_signal_data("BUY")
    df["RSI_14"] = 80.0
    config = StrategyConfig(rsi_buy_max=70.0)

    signal = generate_signal(df, config)

    assert signal.side == "NO_TRADE"
    assert "RSI ok=False" in signal.reason


def test_calculate_trade_levels_buy():
    df = make_signal_data("BUY")
    config = StrategyConfig(atr_multiplier_sl=1.5, atr_multiplier_tp=3.0)

    entry, stop_loss, take_profit, rr = calculate_trade_levels(df.iloc[-1], "BUY", config)

    assert entry == 104
    assert stop_loss == 102.5
    assert take_profit == 107.0
    assert rr == 2.0


def test_calculate_trade_levels_sell():
    df = make_signal_data("SELL")
    config = StrategyConfig(atr_multiplier_sl=1.5, atr_multiplier_tp=3.0)

    entry, stop_loss, take_profit, rr = calculate_trade_levels(df.iloc[-1], "SELL", config)

    assert entry == 100
    assert stop_loss == 101.5
    assert take_profit == 97.0
    assert rr == 2.0


def test_signal_to_dict():
    df = make_signal_data("BUY")
    signal = generate_signal(df)

    data = signal_to_dict(signal)

    assert data["symbol"] == "XAUUSD"
    assert data["side"] == "BUY"
    assert "reason" in data


def test_generate_signal_empty_dataframe_raises_error():
    with pytest.raises(ValueError):
        generate_signal(pd.DataFrame())
