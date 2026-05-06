from pathlib import Path

from src.settings import load_settings, load_yaml_config


def test_load_yaml_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
trading:
  symbol: "XAUUSD"
  live_mode: false
  base_timeframe: "15m"
  confirmation_timeframes:
    - "1h"

risk:
  risk_per_trade: 0.005
  max_risk_per_trade: 0.01
  max_daily_loss: 0.02
  max_open_trades: 2
  max_consecutive_losses: 3
  min_risk_reward: 2.0

filters:
  avoid_high_impact_news: true
  max_spread_points: 30
  use_adx_filter: true
  min_adx: 18

backtest:
  initial_balance: 1000
  commission_per_trade: 0
  slippage_points: 0
""",
        encoding="utf-8",
    )

    data = load_yaml_config(config_path)

    assert data["trading"]["symbol"] == "XAUUSD"
    assert data["risk"]["risk_per_trade"] == 0.005


def test_load_settings_from_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"

    config_path.write_text(
        """
trading:
  symbol: "XAUUSD"
  live_mode: false
  base_timeframe: "15m"
  confirmation_timeframes:
    - "1h"
    - "4h"

risk:
  risk_per_trade: 0.005
  max_risk_per_trade: 0.01
  max_daily_loss: 0.02
  max_open_trades: 2
  max_consecutive_losses: 3
  min_risk_reward: 2.0

filters:
  avoid_high_impact_news: true
  max_spread_points: 30
  use_adx_filter: true
  min_adx: 18

backtest:
  initial_balance: 1000
  commission_per_trade: 0
  slippage_points: 0
""",
        encoding="utf-8",
    )

    env_path.write_text("", encoding="utf-8")

    settings = load_settings(config_path, env_path)

    assert settings.trading.symbol == "XAUUSD"
    assert settings.trading.live_mode is False
    assert settings.risk.risk_per_trade == 0.005
    assert settings.backtest.initial_balance == 1000


def test_env_overrides_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"

    config_path.write_text(
        """
trading:
  symbol: "XAUUSD"
  live_mode: false
  base_timeframe: "15m"
  confirmation_timeframes: []

risk:
  risk_per_trade: 0.005
  max_risk_per_trade: 0.01
  max_daily_loss: 0.02
  max_open_trades: 2
  max_consecutive_losses: 3
  min_risk_reward: 2.0

filters:
  avoid_high_impact_news: true
  max_spread_points: 30
  use_adx_filter: true
  min_adx: 18

backtest:
  initial_balance: 1000
  commission_per_trade: 0
  slippage_points: 0
""",
        encoding="utf-8",
    )

    env_path.write_text(
        "LIVE_MODE=true\nACCOUNT_BALANCE=2000\nRISK_PER_TRADE=0.01\nMAX_DAILY_LOSS=0.03\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path, env_path)

    assert settings.trading.live_mode is True
    assert settings.backtest.initial_balance == 2000
    assert settings.risk.risk_per_trade == 0.01
    assert settings.risk.max_daily_loss == 0.03
