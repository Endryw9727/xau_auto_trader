"""
Project settings loader V2.

Loads configuration from:
- config.yaml
- .env

Now includes: trading, strategy, risk, sessions, filters, macro, news, ai_reasoning, smart_money, backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import os
import yaml
from dotenv import load_dotenv

CONFIG_PATH = Path("config.yaml")
ENV_PATH = Path(".env")

# ===================== TRADING =====================
@dataclass(frozen=True)
class TradingSettings:
    symbol: str
    live_mode: bool
    base_timeframe: str
    confirmation_timeframes: list[str]

# ===================== STRATEGY =====================
@dataclass(frozen=True)
class StrategySettings:
    atr_multiplier_sl: float
    atr_multiplier_tp: float
    rsi_buy_max: float
    rsi_sell_min: float

# ===================== RISK =====================
@dataclass(frozen=True)
class RiskSettings:
    risk_per_trade: float
    max_risk_per_trade: float
    max_daily_loss: float
    max_open_trades: int
    max_consecutive_losses: int
    min_risk_reward: float
    value_per_point: float

# ===================== SESSIONS =====================
@dataclass(frozen=True)
class SessionSettings:
    enabled_sessions: list[str]

# ===================== FILTERS =====================
@dataclass(frozen=True)
class FilterSettings:
    avoid_high_impact_news: bool
    max_spread_points: float
    use_adx_filter: bool
    min_adx: float

# ===================== NEW: MACRO =====================
@dataclass(frozen=True)
class MacroSettings:
    enabled: bool
    dxy_weight: float
    us10y_weight: float
    vix_weight: float
    spx_weight: float
    correlation_window: int
    dxy_symbol: str
    us10y_symbol: str
    vix_symbol: str
    spx_symbol: str
    min_correlation_confidence: float
    block_trade_against_macro: bool
    macro_score_threshold: float

# ===================== NEW: NEWS =====================
@dataclass(frozen=True)
class NewsSettings:
    enabled: bool
    block_before_minutes: int
    block_after_minutes: int
    block_high_impact_only: bool
    max_events_per_day: int

# ===================== NEW: AI REASONING =====================
@dataclass(frozen=True)
class AIReasoningWeights:
    technical: float
    macro: float
    news: float
    session: float
    risk: float

@dataclass(frozen=True)
class AIReasoningSettings:
    enabled: bool
    weights: AIReasoningWeights
    min_confidence_for_trade: float
    generate_explanations: bool
    generate_warnings: bool

# ===================== NEW: SMART MONEY =====================
@dataclass(frozen=True)
class SmartMoneySettings:
    enabled: bool
    fvg_lookback: int
    ob_lookback: int
    liquidity_lookback: int
    min_fvg_size_points: float

# ===================== BACKTEST =====================
@dataclass(frozen=True)
class BacktestSettings:
    initial_balance: float
    commission_per_trade: float
    slippage_points: float
    warmup_candles: int
    rolling_window_candles: int | None

# ===================== APP SETTINGS =====================
@dataclass(frozen=True)
class AppSettings:
    trading: TradingSettings
    strategy: StrategySettings
    risk: RiskSettings
    sessions: SessionSettings
    filters: FilterSettings
    macro: MacroSettings
    news: NewsSettings
    ai_reasoning: AIReasoningSettings
    smart_money: SmartMoneySettings
    backtest: BacktestSettings

def load_yaml_config(config_path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    """Load YAML configuration file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a YAML dictionary")
    return data

def load_settings(config_path: str | Path = CONFIG_PATH, env_path: str | Path = ENV_PATH) -> AppSettings:
    """Load app settings from config.yaml and .env."""
    load_dotenv(env_path)
    config = load_yaml_config(config_path)

    trading_config = config.get("trading", {})
    strategy_config = config.get("strategy", {})
    risk_config = config.get("risk", {})
    session_config = config.get("sessions", {})
    filter_config = config.get("filters", {})
    macro_config = config.get("macro", {})
    news_config = config.get("news", {})
    ai_config = config.get("ai_reasoning", {})
    sm_config = config.get("smart_money", {})
    backtest_config = config.get("backtest", {})

    live_mode = _get_bool_env("LIVE_MODE", trading_config.get("live_mode", False))
    account_balance = _get_float_env("ACCOUNT_BALANCE", backtest_config.get("initial_balance", 1000.0))
    risk_per_trade = _get_float_env("RISK_PER_TRADE", risk_config.get("risk_per_trade", 0.005))
    max_daily_loss = _get_float_env("MAX_DAILY_LOSS", risk_config.get("max_daily_loss", 0.02))
    rolling_window_candles = backtest_config.get("rolling_window_candles", 500)
    if rolling_window_candles is not None:
        rolling_window_candles = int(rolling_window_candles)

    # Parse AI weights
    ai_weights = ai_config.get("weights", {})
    ai_weights_obj = AIReasoningWeights(
        technical=float(ai_weights.get("technical", 0.40)),
        macro=float(ai_weights.get("macro", 0.30)),
        news=float(ai_weights.get("news", 0.15)),
        session=float(ai_weights.get("session", 0.10)),
        risk=float(ai_weights.get("risk", 0.05)),
    )

    return AppSettings(
        trading=TradingSettings(
            symbol=str(trading_config.get("symbol", "XAUUSD")),
            live_mode=live_mode,
            base_timeframe=str(trading_config.get("base_timeframe", "15m")),
            confirmation_timeframes=list(trading_config.get("confirmation_timeframes", [])),
        ),
        strategy=StrategySettings(
            atr_multiplier_sl=float(strategy_config.get("atr_multiplier_sl", 1.5)),
            atr_multiplier_tp=float(strategy_config.get("atr_multiplier_tp", 3.0)),
            rsi_buy_max=float(strategy_config.get("rsi_buy_max", 70.0)),
            rsi_sell_min=float(strategy_config.get("rsi_sell_min", 30.0)),
        ),
        risk=RiskSettings(
            risk_per_trade=risk_per_trade,
            max_risk_per_trade=float(risk_config.get("max_risk_per_trade", 0.01)),
            max_daily_loss=max_daily_loss,
            max_open_trades=int(risk_config.get("max_open_trades", 2)),
            max_consecutive_losses=int(risk_config.get("max_consecutive_losses", 3)),
            min_risk_reward=float(risk_config.get("min_risk_reward", 2.0)),
            value_per_point=float(risk_config.get("value_per_point", 1.0)),
        ),
        sessions=SessionSettings(
            enabled_sessions=list(session_config.get("enabled_sessions", ["Asia", "London", "New York", "Off Session"])),
        ),
        filters=FilterSettings(
            avoid_high_impact_news=bool(filter_config.get("avoid_high_impact_news", True)),
            max_spread_points=float(filter_config.get("max_spread_points", 30)),
            use_adx_filter=bool(filter_config.get("use_adx_filter", True)),
            min_adx=float(filter_config.get("min_adx", 18)),
        ),
        macro=MacroSettings(
            enabled=bool(macro_config.get("enabled", True)),
            dxy_weight=float(macro_config.get("dxy_weight", 0.35)),
            us10y_weight=float(macro_config.get("us10y_weight", 0.25)),
            vix_weight=float(macro_config.get("vix_weight", 0.20)),
            spx_weight=float(macro_config.get("spx_weight", 0.20)),
            correlation_window=int(macro_config.get("correlation_window", 50)),
            dxy_symbol=str(macro_config.get("dxy_symbol", "DX-Y.NYB")),
            us10y_symbol=str(macro_config.get("us10y_symbol", "^TNX")),
            vix_symbol=str(macro_config.get("vix_symbol", "^VIX")),
            spx_symbol=str(macro_config.get("spx_symbol", "^GSPC")),
            min_correlation_confidence=float(macro_config.get("min_correlation_confidence", 0.65)),
            block_trade_against_macro=bool(macro_config.get("block_trade_against_macro", True)),
            macro_score_threshold=float(macro_config.get("macro_score_threshold", 0.30)),
        ),
        news=NewsSettings(
            enabled=bool(news_config.get("enabled", True)),
            block_before_minutes=int(news_config.get("block_before_minutes", 30)),
            block_after_minutes=int(news_config.get("block_after_minutes", 15)),
            block_high_impact_only=bool(news_config.get("block_high_impact_only", True)),
            max_events_per_day=int(news_config.get("max_events_per_day", 5)),
        ),
        ai_reasoning=AIReasoningSettings(
            enabled=bool(ai_config.get("enabled", True)),
            weights=ai_weights_obj,
            min_confidence_for_trade=float(ai_config.get("min_confidence_for_trade", 0.55)),
            generate_explanations=bool(ai_config.get("generate_explanations", True)),
            generate_warnings=bool(ai_config.get("generate_warnings", True)),
        ),
        smart_money=SmartMoneySettings(
            enabled=bool(sm_config.get("enabled", True)),
            fvg_lookback=int(sm_config.get("fvg_lookback", 50)),
            ob_lookback=int(sm_config.get("ob_lookback", 50)),
            liquidity_lookback=int(sm_config.get("liquidity_lookback", 50)),
            min_fvg_size_points=float(sm_config.get("min_fvg_size_points", 2.0)),
        ),
        backtest=BacktestSettings(
            initial_balance=account_balance,
            commission_per_trade=float(backtest_config.get("commission_per_trade", 0.0)),
            slippage_points=float(backtest_config.get("slippage_points", 0.0)),
            warmup_candles=int(backtest_config.get("warmup_candles", 220)),
            rolling_window_candles=rolling_window_candles,
        ),
    )

def _get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return float(default)
    return float(value)

def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return bool(default)
    return value.lower() in {"true", "1", "yes", "y", "on"}
