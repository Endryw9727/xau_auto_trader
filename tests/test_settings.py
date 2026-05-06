from src.settings import load_settings, load_yaml_config


CONFIG_TEXT = """
trading:
  symbol: "XAUUSD"
  live_mode: false
  base_timeframe: "15m"
  confirmation_timeframes:
    - "1h"
    - "4h"

strategy:
  atr_multiplier_sl: 1.5
  atr_multiplier_tp: 3.0
  rsi_buy_max: 70.0
  rsi_sell_min: 30.0

risk:
  risk_per_trade: 0.005
  max_risk_per_trade: 0.01
  max_daily_loss: 0.02
  max_open_trades: 2
  max_consecutive_losses: 3
  min_risk_reward: 2.0
  value_per_point: 1.0

filters:
  avoid_high_impact_news: true
  max_spread_points: 30
  use_adx_filter: true
  min_adx: 18

backtest:
  initial_balance: 1000
  commission_per_trade: 0
  slippage_points: 0
  warmup_candles: 220
"""


def test_load_yaml_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")

    data = load_yaml_config(config_path)

    assert data["trading"]["symbol"] == "XAUUSD"
    assert data["risk"]["risk_per_trade"] == 0.005
    assert data["strategy"]["atr_multiplier_sl"] == 1.5


def test_load_settings_from_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"

    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    env_path.write_text("", encoding="utf-8")

    settings = load_settings(config_path, env_path)

    assert settings.trading.symbol == "XAUUSD"
    assert settings.trading.live_mode is False
    assert settings.trading.base_timeframe == "15m"
    assert settings.strategy.atr_multiplier_sl == 1.5
    assert settings.strategy.atr_multiplier_tp == 3.0
    assert settings.strategy.rsi_buy_max == 70.0
    assert settings.strategy.rsi_sell_min == 30.0
    assert settings.risk.risk_per_trade == 0.005
    assert settings.risk.value_per_point == 1.0
    assert settings.backtest.initial_balance == 1000
    assert settings.backtest.warmup_candles == 220


def test_env_overrides_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"

    config_path.write_text(CONFIG_TEXT, encoding="utf-8")

    env_path.write_text(
        "LIVE_MODE=true\nACCOUNT_BALANCE=2000\nRISK_PER_TRADE=0.01\nMAX_DAILY_LOSS=0.03\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path, env_path)

    assert settings.trading.live_mode is True
    assert settings.backtest.initial_balance == 2000
    assert settings.risk.risk_per_trade == 0.01
    assert settings.risk.max_daily_loss == 0.03
