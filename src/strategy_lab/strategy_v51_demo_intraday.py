"""
Demo intraday V51 candidate.

This variant is separate from V50 and is intended for paper-forward and demo
evaluation only. It emits analytical signals from closed candles and never
contacts brokers or live execution code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.strategy.rules import StrategyConfig, calculate_trade_levels
from src.strategy.signals import TradingSignal
from src.strategy_lab import strategy_v50_pine
from src.utils.time_alignment import normalize_timezone_name


STRATEGY_NAME = "demo_intraday_candidate"
DEFAULT_V51_CONFIG_PATH = Path("config/strategy_v51.yaml")
DEFAULT_V51_REPORT_DIR = Path("reports/strategy_lab")
DEFAULT_V51_SIGNAL_LOG_PATH = DEFAULT_V51_REPORT_DIR / "v51_demo_intraday_signal_log.csv"
DEFAULT_V50_SIGNAL_LOG_PATH = DEFAULT_V51_REPORT_DIR / "v50_high_margin_signal_log.csv"
DEFAULT_V50_V51_COMPARISON_PATH = DEFAULT_V51_REPORT_DIR / "v50_vs_v51_demo_intraday_comparison.csv"

V51_LOG_COLUMNS = [
    "signal_id",
    "candle_time",
    "session",
    "side",
    "decision",
    "score",
    "score_gap",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "lot_size",
    "spread_cost",
    "slippage_estimate",
    "reason",
]

V51_COMPARISON_COLUMNS = [
    "strategy_name",
    "trade_candidates",
    "accepted_signals",
    "rejected_signals",
    "top_rejection_reasons",
    "estimated_trades_per_day",
    "average_rr",
    "average_spread_cost",
    "max_daily_trades_reached",
]


@dataclass(frozen=True)
class V51DemoIntradayConfig:
    """Config for the V51 demo intraday candidate."""

    strategy_name: str
    symbol: str
    timeframe: str
    mt5_timestamp_timezone: str
    demo_only: bool
    allow_real_live: bool
    allow_demo_execution: bool
    execution_enabled: bool
    magic_number: int
    risk_per_trade: float
    max_trades_per_day: int
    max_open_positions: int
    min_risk_reward: float
    min_score: float
    min_score_gap: float
    min_adx: float
    atr_multiplier_sl: float
    atr_multiplier_tp: float
    warmup_candles: int
    allowed_sessions: tuple[str, ...]
    fixed_lot_size: float
    spread_cost: float
    slippage_estimate: float
    max_spread_cost: float
    max_slippage_estimate: float
    max_spread_points: float
    max_slippage_points: int
    max_chase_points: float
    reprice_live_entry: bool
    max_data_age_minutes: int
    max_candidate_age_minutes: int
    candidate_freshness_required: bool
    rejected_signal_cooldown_minutes: int
    live_candidate_window_minutes: int
    require_latest_closed_candle_candidate: bool
    selection_lookback_candles: int
    use_mtf_context_filter: bool
    require_mtf_data_ok: bool
    allowed_mtf_bias_for_buy: tuple[str, ...]
    allowed_mtf_bias_for_sell: tuple[str, ...]
    use_ai_reasoning_filter: bool
    ai_reasoning_report_only: bool
    min_ai_confidence_to_trade: float
    min_trade_quality_score: float

    @property
    def strategy_config(self) -> StrategyConfig:
        """Return the strategy-level config used to calculate SL, TP, and RR."""
        return StrategyConfig(
            symbol=self.symbol,
            timeframe=self.timeframe,
            min_adx=self.min_adx,
            min_risk_reward=self.min_risk_reward,
            atr_multiplier_sl=self.atr_multiplier_sl,
            atr_multiplier_tp=self.atr_multiplier_tp,
        )


def load_v51_config(path: str | Path = DEFAULT_V51_CONFIG_PATH) -> V51DemoIntradayConfig:
    """Load V51 config and validate demo-only safety gates."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid V51 config: {config_path}")

    allowed_sessions = raw.get("allowed_sessions", ("LONDON", "LONDON/US", "NEW YORK"))
    if isinstance(allowed_sessions, str):
        allowed_sessions = [allowed_sessions]

    config = V51DemoIntradayConfig(
        strategy_name=str(raw.get("strategy_name", STRATEGY_NAME)),
        symbol=str(raw.get("symbol", "XAUUSD")),
        timeframe=str(raw.get("timeframe", "15m")),
        mt5_timestamp_timezone=str(raw.get("mt5_timestamp_timezone", "Europe/Rome")),
        demo_only=_as_bool(raw.get("demo_only", True)),
        allow_real_live=_as_bool(raw.get("allow_real_live", False)),
        allow_demo_execution=_as_bool(raw.get("allow_demo_execution", False)),
        execution_enabled=_as_bool(raw.get("execution_enabled", False)),
        magic_number=int(raw.get("magic_number", 510051)),
        risk_per_trade=float(raw.get("risk_per_trade", 0.0025)),
        max_trades_per_day=int(raw.get("max_trades_per_day", 2)),
        max_open_positions=int(raw.get("max_open_positions", 1)),
        min_risk_reward=float(raw.get("min_risk_reward", 1.2)),
        min_score=float(raw.get("min_score", 60.0)),
        min_score_gap=float(raw.get("min_score_gap", 4.0)),
        min_adx=float(raw.get("min_adx", 14.0)),
        atr_multiplier_sl=float(raw.get("atr_multiplier_sl", 1.2)),
        atr_multiplier_tp=float(raw.get("atr_multiplier_tp", 1.5)),
        warmup_candles=int(raw.get("warmup_candles", 220)),
        allowed_sessions=tuple(str(session).upper() for session in allowed_sessions),
        fixed_lot_size=float(raw.get("fixed_lot_size", 0.01)),
        spread_cost=float(raw.get("spread_cost", 0.0)),
        slippage_estimate=float(raw.get("slippage_estimate", 0.1)),
        max_spread_cost=float(raw.get("max_spread_cost", 0.5)),
        max_slippage_estimate=float(raw.get("max_slippage_estimate", 0.5)),
        max_spread_points=float(raw.get("max_spread_points", 80)),
        max_slippage_points=int(raw.get("max_slippage_points", 20)),
        max_chase_points=float(raw.get("max_chase_points", 80)),
        reprice_live_entry=_as_bool(raw.get("reprice_live_entry", True)),
        max_data_age_minutes=int(raw.get("max_data_age_minutes", 45)),
        max_candidate_age_minutes=int(raw.get("max_candidate_age_minutes", 20)),
        candidate_freshness_required=_as_bool(raw.get("candidate_freshness_required", True)),
        rejected_signal_cooldown_minutes=int(raw.get("rejected_signal_cooldown_minutes", 30)),
        live_candidate_window_minutes=int(raw.get("live_candidate_window_minutes", 20)),
        require_latest_closed_candle_candidate=_as_bool(raw.get("require_latest_closed_candle_candidate", True)),
        selection_lookback_candles=int(raw.get("selection_lookback_candles", 16)),
        use_mtf_context_filter=_as_bool(raw.get("use_mtf_context_filter", False)),
        require_mtf_data_ok=_as_bool(raw.get("require_mtf_data_ok", True)),
        allowed_mtf_bias_for_buy=_as_tuple(raw.get("allowed_mtf_bias_for_buy", "LONG_BIAS")),
        allowed_mtf_bias_for_sell=_as_tuple(raw.get("allowed_mtf_bias_for_sell", "SHORT_BIAS")),
        use_ai_reasoning_filter=_as_bool(raw.get("use_ai_reasoning_filter", False)),
        ai_reasoning_report_only=_as_bool(raw.get("ai_reasoning_report_only", True)),
        min_ai_confidence_to_trade=float(raw.get("min_ai_confidence_to_trade", 70)),
        min_trade_quality_score=float(raw.get("min_trade_quality_score", 70)),
    )
    validate_v51_config(config)
    return config


def validate_v51_config(config: V51DemoIntradayConfig) -> None:
    """Validate V51 operational and demo safety invariants."""
    if config.strategy_name != STRATEGY_NAME:
        raise ValueError(f"strategy_name must be {STRATEGY_NAME}")
    try:
        normalize_timezone_name(config.mt5_timestamp_timezone)
    except Exception as exc:
        raise ValueError(f"invalid mt5_timestamp_timezone: {config.mt5_timestamp_timezone}") from exc
    if not config.demo_only:
        raise PermissionError("V51 requires demo_only=true")
    if config.allow_real_live:
        raise PermissionError("allow_real_live must remain false")
    if config.magic_number <= 0:
        raise ValueError("magic_number must be positive")
    if config.risk_per_trade <= 0 or config.risk_per_trade > 0.005:
        raise ValueError("risk_per_trade must be positive and low for V51 demo evaluation")
    if config.max_trades_per_day <= 0 or config.max_trades_per_day > 2:
        raise ValueError("max_trades_per_day must be between 1 and 2")
    if config.max_open_positions != 1:
        raise ValueError("max_open_positions must be 1")
    if config.min_risk_reward < 1.2:
        raise ValueError("min_risk_reward must be at least 1.2")
    if config.atr_multiplier_sl <= 0 or config.atr_multiplier_tp <= 0:
        raise ValueError("ATR multipliers must be positive")
    if config.atr_multiplier_tp / config.atr_multiplier_sl < config.min_risk_reward:
        raise ValueError("ATR TP/SL multipliers must satisfy min_risk_reward")
    if config.fixed_lot_size <= 0:
        raise ValueError("fixed_lot_size must be positive")
    if config.spread_cost < 0 or config.slippage_estimate < 0:
        raise ValueError("cost estimates cannot be negative")
    if config.max_spread_points <= 0 or config.max_slippage_points < 0:
        raise ValueError("MT5 spread/slippage limits must be valid")
    if config.max_chase_points < 0:
        raise ValueError("max_chase_points must be non-negative")
    if config.max_data_age_minutes <= 0 or config.selection_lookback_candles <= 0:
        raise ValueError("data freshness and selection lookback must be positive")
    if config.max_candidate_age_minutes <= 0:
        raise ValueError("max_candidate_age_minutes must be positive")
    if config.rejected_signal_cooldown_minutes <= 0:
        raise ValueError("rejected_signal_cooldown_minutes must be positive")
    if config.live_candidate_window_minutes <= 0:
        raise ValueError("live_candidate_window_minutes must be positive")
    if not config.allowed_mtf_bias_for_buy or not config.allowed_mtf_bias_for_sell:
        raise ValueError("allowed MTF bias lists cannot be empty")
    if not 0 <= config.min_ai_confidence_to_trade <= 100:
        raise ValueError("min_ai_confidence_to_trade must be between 0 and 100")
    if not 0 <= config.min_trade_quality_score <= 100:
        raise ValueError("min_trade_quality_score must be between 0 and 100")


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate a V51 analytical signal from the latest closed candle."""
    v51_config = load_v51_config()
    strategy_config = _v51_strategy_config(v51_config, config)
    decision = evaluate_latest_demo_intraday_candidate(df, v51_config, strategy_config=strategy_config)
    return decision["signal"]


def evaluate_latest_demo_intraday_candidate(
    df: pd.DataFrame,
    v51_config: V51DemoIntradayConfig | None = None,
    *,
    strategy_config: StrategyConfig | None = None,
    trades_today: int = 0,
    open_positions: int = 0,
) -> dict[str, Any]:
    """Evaluate only the latest row in the supplied closed-candle window."""
    if df.empty:
        raise ValueError("DataFrame cannot be empty")
    v51_config = v51_config or load_v51_config()
    validate_v51_config(v51_config)
    strategy_config = _v51_strategy_config(v51_config, strategy_config)
    features = df if strategy_v50_pine.V50_REQUIRED_COLUMNS.issubset(df.columns) else strategy_v50_pine.build_v50_features(df)
    latest = features.iloc[-1]
    return _decision_from_row(
        latest,
        v51_config,
        strategy_config,
        trades_today=trades_today,
        open_positions=open_positions,
    )


def build_demo_intraday_decision_log(
    market_data: pd.DataFrame,
    v51_config: V51DemoIntradayConfig | None = None,
    *,
    strategy_config: StrategyConfig | None = None,
    starting_trades_today: int = 0,
    open_positions: int = 0,
    enforce_daily_limit: bool = True,
) -> pd.DataFrame:
    """Build a closed-candle V51 decision log with one row per evaluated candle."""
    v51_config = v51_config or load_v51_config()
    validate_v51_config(v51_config)
    strategy_config = _v51_strategy_config(v51_config, strategy_config)
    data = _normalize_market_data(market_data)
    features = data if strategy_v50_pine.V50_REQUIRED_COLUMNS.issubset(data.columns) else strategy_v50_pine.build_v50_features(data)
    start = 0 if strategy_v50_pine.V50_REQUIRED_COLUMNS.issubset(data.columns) else min(v51_config.warmup_candles, len(features))
    rows = []
    accepted_by_day: dict[pd.Timestamp, int] = {}

    for _, row in features.iloc[start:].iterrows():
        candle_time = _timestamp_from_row(row)
        trade_day = candle_time.normalize()
        accepted_count = accepted_by_day.get(trade_day, 0)
        trades_today = starting_trades_today + accepted_count if enforce_daily_limit else starting_trades_today
        decision = _decision_from_row(
            row,
            v51_config,
            strategy_config,
            trades_today=trades_today,
            open_positions=open_positions,
        )
        log_row = _log_row(decision, v51_config)
        rows.append(log_row)
        if enforce_daily_limit and log_row["decision"] == "ACCEPTED":
            accepted_by_day[trade_day] = accepted_count + 1

    return pd.DataFrame(rows, columns=V51_LOG_COLUMNS)


def build_v50_reference_decision_log(
    market_data: pd.DataFrame,
    *,
    warmup_candles: int = 220,
) -> pd.DataFrame:
    """Build a V50 high-margin reference log for comparison only."""
    from src.paper.paper_engine import load_paper_trading_config
    from src.paper.paper_forward_engine import generate_high_margin_candidate

    data = _normalize_market_data(market_data)
    paper_config = load_paper_trading_config()
    strategy_config = StrategyConfig(symbol=paper_config.symbol, timeframe=paper_config.base_timeframe)
    rows = []
    start = min(warmup_candles, len(data))

    for index in range(start, len(data)):
        window = data.iloc[: index + 1]
        candidate = generate_high_margin_candidate(window, strategy_config, paper_config, paper_config.initial_equity)
        signal = candidate.signal
        metadata = candidate.metadata
        decision = "ACCEPTED" if candidate.allowed and signal.side in {"BUY", "SELL"} else "REJECTED" if signal.side in {"BUY", "SELL"} else "NO_TRADE"
        rows.append(
            {
                "signal_id": "V50-" + pd.Timestamp(window.index[-1]).strftime("%Y%m%d%H%M"),
                "candle_time": pd.Timestamp(window.index[-1]).isoformat(),
                "session": metadata.get("session", ""),
                "side": signal.side if signal.side in {"BUY", "SELL"} else "",
                "decision": decision,
                "score": metadata.get("score"),
                "score_gap": metadata.get("score_gap"),
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "risk_reward": signal.risk_reward,
                "lot_size": metadata.get("lot_size"),
                "spread_cost": metadata.get("spread_cost_eur"),
                "slippage_estimate": metadata.get("slippage_cost_eur"),
                "reason": candidate.reason,
            }
        )
    return pd.DataFrame(rows, columns=V51_LOG_COLUMNS)


def build_v50_vs_v51_report(v50_log: pd.DataFrame, v51_log: pd.DataFrame) -> pd.DataFrame:
    """Summarize V50 and V51 decision logs for operational comparison."""
    rows = [
        _comparison_row("v50_high_margin_reference", v50_log),
        _comparison_row(STRATEGY_NAME, v51_log),
    ]
    return pd.DataFrame(rows, columns=V51_COMPARISON_COLUMNS)


def run_v50_vs_v51_comparison(
    market_data: pd.DataFrame,
    *,
    v51_config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_V51_REPORT_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build and export V50 reference, V51 decision log, and comparison report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    v51_config = load_v51_config(v51_config_path)
    v50_log = build_v50_reference_decision_log(market_data, warmup_candles=v51_config.warmup_candles)
    v51_log = build_demo_intraday_decision_log(market_data, v51_config)
    comparison = build_v50_vs_v51_report(v50_log, v51_log)
    v50_log.to_csv(output_dir / DEFAULT_V50_SIGNAL_LOG_PATH.name, index=False)
    v51_log.to_csv(output_dir / DEFAULT_V51_SIGNAL_LOG_PATH.name, index=False)
    comparison.to_csv(output_dir / DEFAULT_V50_V51_COMPARISON_PATH.name, index=False)
    return comparison, v50_log, v51_log


def _decision_from_row(
    row: pd.Series,
    v51_config: V51DemoIntradayConfig,
    strategy_config: StrategyConfig,
    *,
    trades_today: int,
    open_positions: int,
) -> dict[str, Any]:
    candle_time = _timestamp_from_row(row)
    session = _session(row)
    side = _select_side(row)
    score = _score(row, side)
    opposite = _opposite_score(row, side)
    score_gap = score - opposite
    signal = _no_trade(candle_time, strategy_config, "V51 no setup")
    base = {
        "signal": signal,
        "candle_time": candle_time,
        "session": session,
        "side": side if side in {"BUY", "SELL"} else "",
        "decision": "NO_TRADE",
        "score": score,
        "score_gap": score_gap,
        "lot_size": v51_config.fixed_lot_size,
        "spread_cost": v51_config.spread_cost,
        "slippage_estimate": v51_config.slippage_estimate,
        "reason": "V51 no directional score candidate",
    }

    if side not in {"BUY", "SELL"}:
        return base

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(row, side, strategy_config)
    signal = TradingSignal(
        timestamp=candle_time.to_pydatetime(),
        symbol=strategy_config.symbol,
        timeframe=strategy_config.timeframe,
        side=side,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=min(score, 100.0),
        reason=(
            "V51 demo intraday"
            f" | Side={side}"
            f" | score={score:.1f}"
            f" | opposite_score={opposite:.1f}"
            f" | session={session}"
            f" | RR={risk_reward:.2f}"
        ),
    )
    base["signal"] = signal

    rejection = _rejection_reason(row, v51_config, side, score, score_gap, risk_reward, trades_today, open_positions)
    if rejection is not None:
        base["decision"] = "PAUSE" if rejection.startswith("max trades per day") else "REJECTED"
        base["reason"] = rejection
        return base

    base["decision"] = "ACCEPTED"
    base["reason"] = "V51 demo intraday signal accepted"
    return base


def _rejection_reason(
    row: pd.Series,
    config: V51DemoIntradayConfig,
    side: str,
    score: float,
    score_gap: float,
    risk_reward: float,
    trades_today: int,
    open_positions: int,
) -> str | None:
    session = _session(row)
    if open_positions >= config.max_open_positions:
        return f"max open positions reached ({config.max_open_positions})"
    if trades_today >= config.max_trades_per_day:
        return f"max trades per day reached ({config.max_trades_per_day})"
    if session not in set(config.allowed_sessions):
        return f"session blocked: {session}"
    if score < config.min_score:
        return f"score {score:.1f} below {config.min_score:.1f}"
    if score_gap < config.min_score_gap:
        return f"score gap {score_gap:.1f} below {config.min_score_gap:.1f}"
    if _adx(row) < config.min_adx:
        return f"ADX {_adx(row):.1f} below {config.min_adx:.1f}"
    if not _relaxed_setup_ok(row, side):
        return f"{side} setup not confirmed"
    if _quality_blocked(row, side):
        return f"{side} quality guard blocked"
    if risk_reward < config.min_risk_reward:
        return f"RR {risk_reward:.2f} below {config.min_risk_reward:.2f}"
    if config.spread_cost > config.max_spread_cost:
        return f"spread cost {config.spread_cost:.2f} above {config.max_spread_cost:.2f}"
    if config.slippage_estimate > config.max_slippage_estimate:
        return f"slippage estimate {config.slippage_estimate:.2f} above {config.max_slippage_estimate:.2f}"
    return None


def _v51_strategy_config(
    v51_config: V51DemoIntradayConfig,
    base_config: StrategyConfig | None,
) -> StrategyConfig:
    if base_config is None:
        return v51_config.strategy_config
    return replace(
        base_config,
        symbol=v51_config.symbol,
        timeframe=v51_config.timeframe,
        min_adx=v51_config.min_adx,
        min_risk_reward=v51_config.min_risk_reward,
        atr_multiplier_sl=v51_config.atr_multiplier_sl,
        atr_multiplier_tp=v51_config.atr_multiplier_tp,
    )


def _relaxed_setup_ok(row: pd.Series, side: str) -> bool:
    if side == "BUY":
        return bool(row.get("v50_setup_long", False)) or (
            _value(row, "Close") > _value(row, "v50_ema21")
            and _score(row, side) >= 60.0
        )
    return bool(row.get("v50_setup_short", False)) or (
        _value(row, "Close") < _value(row, "v50_ema21")
        and _score(row, side) >= 60.0
    )


def _quality_blocked(row: pd.Series, side: str) -> bool:
    if bool(row.get("v50_chop_block", False)):
        return True
    if side == "BUY":
        return bool(row.get("v50_long_chase_block", False)) or bool(row.get("v50_late_long_impulse", False))
    return bool(row.get("v50_short_chase_block", False)) or bool(row.get("v50_late_short_impulse", False))


def _select_side(row: pd.Series) -> str:
    long_score = _score(row, "BUY")
    short_score = _score(row, "SELL")
    if long_score <= 0 and short_score <= 0:
        return "NO_TRADE"
    return "BUY" if long_score >= short_score else "SELL"


def _score(row: pd.Series, side: str) -> float:
    key = "v50_score_long" if side == "BUY" else "v50_score_short"
    value = row.get(key, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _opposite_score(row: pd.Series, side: str) -> float:
    if side not in {"BUY", "SELL"}:
        return 0.0
    return _score(row, "SELL" if side == "BUY" else "BUY")


def _comparison_row(strategy_name: str, log: pd.DataFrame) -> dict[str, Any]:
    prepared = log.copy()
    if prepared.empty:
        return {
            "strategy_name": strategy_name,
            "trade_candidates": 0,
            "accepted_signals": 0,
            "rejected_signals": 0,
            "top_rejection_reasons": "",
            "estimated_trades_per_day": 0.0,
            "average_rr": 0.0,
            "average_spread_cost": 0.0,
            "max_daily_trades_reached": 0,
        }
    candidates = prepared[prepared["side"].astype(str).isin(["BUY", "SELL"])]
    accepted = prepared[prepared["decision"] == "ACCEPTED"]
    rejected = candidates[candidates["decision"] != "ACCEPTED"]
    return {
        "strategy_name": strategy_name,
        "trade_candidates": int(len(candidates)),
        "accepted_signals": int(len(accepted)),
        "rejected_signals": int(len(rejected)),
        "top_rejection_reasons": _top_rejection_reasons(rejected),
        "estimated_trades_per_day": _estimated_trades_per_day(accepted, prepared),
        "average_rr": _mean_numeric(accepted.get("risk_reward")),
        "average_spread_cost": _mean_numeric(accepted.get("spread_cost")),
        "max_daily_trades_reached": int(prepared["reason"].astype(str).str.contains("max trades per day", case=False).sum()),
    }


def _top_rejection_reasons(rejected: pd.DataFrame) -> str:
    if rejected.empty:
        return ""
    counts = rejected["reason"].astype(str).value_counts().head(3)
    return "; ".join(f"{reason} ({count})" for reason, count in counts.items())


def _estimated_trades_per_day(accepted: pd.DataFrame, full_log: pd.DataFrame) -> float:
    if full_log.empty:
        return 0.0
    times = pd.to_datetime(full_log["candle_time"], errors="coerce").dropna()
    days = max(int(times.dt.date.nunique()), 1)
    return float(len(accepted) / days)


def _log_row(decision: dict[str, Any], config: V51DemoIntradayConfig) -> dict[str, Any]:
    signal = decision["signal"]
    candle_time = pd.Timestamp(decision["candle_time"])
    side = decision["side"]
    return {
        "signal_id": f"V51-{candle_time.strftime('%Y%m%d%H%M')}-{side or 'NO_TRADE'}",
        "candle_time": candle_time.isoformat(),
        "session": decision["session"],
        "side": side,
        "decision": decision["decision"],
        "score": decision["score"],
        "score_gap": decision["score_gap"],
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "risk_reward": signal.risk_reward,
        "lot_size": config.fixed_lot_size,
        "spread_cost": config.spread_cost,
        "slippage_estimate": config.slippage_estimate,
        "reason": decision["reason"],
    }


def _normalize_market_data(market_data: pd.DataFrame) -> pd.DataFrame:
    data = market_data.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        for column in ("Date", "time", "timestamp"):
            if column in data.columns:
                data[column] = pd.to_datetime(data[column], errors="coerce")
                data = data.dropna(subset=[column]).set_index(column)
                break
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("market_data must have a DatetimeIndex or a Date/time column")
    return data.sort_index()


def _no_trade(timestamp: pd.Timestamp, config: StrategyConfig, reason: str) -> TradingSignal:
    return TradingSignal(
        timestamp=timestamp.to_pydatetime(),
        symbol=config.symbol,
        timeframe=config.timeframe,
        side="NO_TRADE",
        entry_price=None,
        stop_loss=None,
        take_profit=None,
        risk_reward=None,
        confidence=0.0,
        reason=reason,
    )


def _timestamp_from_row(row: pd.Series) -> pd.Timestamp:
    if isinstance(row.name, pd.Timestamp):
        return pd.Timestamp(row.name)
    return pd.Timestamp.now(tz=UTC)


def _session(row: pd.Series) -> str:
    return str(row.get("v50_session", row.get("session", "UNKNOWN"))).strip().upper()


def _adx(row: pd.Series) -> float:
    return _value(row, "v50_adx", fallback_column="ADX_14")


def _value(row: pd.Series, column: str, fallback_column: str | None = None) -> float:
    value = row.get(column)
    if pd.isna(value) and fallback_column is not None:
        value = row.get(fallback_column)
    if pd.isna(value):
        return 0.0
    return float(value)


def _mean_numeric(series: pd.Series | None) -> float:
    if series is None:
        return 0.0
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip().upper(),)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip().upper() for item in value if str(item).strip())
    return (str(value).strip().upper(),)


generate_signal.required_history_candles = strategy_v50_pine.REQUIRED_HISTORY_CANDLES
generate_signal.prepare_backtest_data = strategy_v50_pine.build_v50_features
