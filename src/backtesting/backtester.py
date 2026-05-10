"""
Simple OHLCV backtester.

This backtester:
- adds indicators
- generates signals candle by candle
- validates signals with the risk manager
- simulates SL/TP execution on future candles
- records closed trades
- calculates metrics

This is not live trading.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from src.backtesting.metrics import BacktestMetrics, calculate_metrics, metrics_to_dict
from src.risk.risk_manager import AccountState, RiskConfig, evaluate_signal_risk, from_trading_signal
from src.strategy.indicators import add_all_core_indicators
from src.strategy.rules import StrategyConfig
from src.analysis.session_analysis import classify_hour_to_session
from src.strategy.signals import TradingSignal, generate_signal
from src.journal.trade_journal import save_signal_to_db


SignalGenerator = Callable[[pd.DataFrame, StrategyConfig], TradingSignal]
DEFAULT_STRATEGY_NAME = "existing_strategy"
TRADES_BY_STRATEGY_FILENAME = "trades_by_strategy.csv"
TRADE_REPORT_COLUMNS = [
    "strategy_name",
    "entry_time",
    "exit_time",
    "timestamp_open",
    "timestamp_close",
    "side",
    "side_label",
    "entry_price",
    "stop_loss",
    "take_profit",
    "exit_price",
    "position_size",
    "result",
    "pnl",
    "profit_loss",
    "pnl_pct",
    "bars_in_trade",
    "session",
    "setup_type",
    "score_long",
    "score_short",
    "reason",
    "signal_reason",
    "reason_entry",
    "reason_exit",
    "symbol",
    "timeframe",
    "risk_percent",
    "risk_amount",
    "risk_reward",
    "confidence",
    "balance_before",
    "balance_after",
]


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest configuration."""

    initial_balance: float = 1000.0
    risk_per_trade: float = 0.005
    max_risk_per_trade: float = 0.01
    max_daily_loss: float = 0.02
    max_open_trades: int = 1
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0
    warmup_candles: int = 220
    allowed_sessions: list[str] | None = None
    rolling_window_candles: int | None = 500


@dataclass(frozen=True)
class BacktestResult:
    """Backtest result."""

    trades: pd.DataFrame
    metrics: BacktestMetrics
    final_balance: float


def _resolve_rolling_window_candles(
    config: BacktestConfig,
    signal_generator: SignalGenerator,
) -> int | None:
    configured_window = config.rolling_window_candles
    if configured_window is not None and configured_window <= 0:
        raise ValueError("rolling_window_candles must be positive or None")

    required_window = getattr(signal_generator, "required_history_candles", None)
    if required_window is None:
        return configured_window

    required_window = int(required_window)
    if required_window <= 0:
        raise ValueError("strategy required_history_candles must be positive")
    if configured_window is None:
        return None
    return max(configured_window, required_window)


def run_backtest(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    db_path: str | Path = "data/database/trading.db",
    save_signals: bool = True,
    signal_generator: SignalGenerator | None = None,
    save_trades_to_db: bool = True,
    save_signals_to_db: bool = True,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
) -> BacktestResult:
    """
    Run a simple backtest on OHLCV data.

    Assumption:
    - one position at a time
    - entry happens at signal close price
    - SL/TP checked on following candles
    """
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    if signal_generator is None:
        signal_generator = generate_signal

    _validate_ohlcv(df)

    if len(df) <= backtest_config.warmup_candles:
        raise ValueError("Not enough candles for backtest warmup")

    data = add_all_core_indicators(df)
    prepare_backtest_data = getattr(signal_generator, "prepare_backtest_data", None)
    if prepare_backtest_data is not None:
        data = prepare_backtest_data(data)
    rolling_window_candles = _resolve_rolling_window_candles(
        backtest_config,
        signal_generator,
    )
    balance = backtest_config.initial_balance
    trades: list[dict] = []
    consecutive_losses = 0
    current_day = None
    current_daily_pnl = 0.0

    i = backtest_config.warmup_candles

    while i < len(data) - 1:
        timestamp = data.index[i]

        if current_day != timestamp.date():
            current_day = timestamp.date()
            current_daily_pnl = 0.0
            consecutive_losses = 0

        session_name = classify_hour_to_session(timestamp.hour)

        if (
            backtest_config.allowed_sessions is not None
            and session_name not in backtest_config.allowed_sessions
        ):
            i += 1
            continue

        window_start = 0
        if rolling_window_candles is not None:
            window_start = max(0, i - rolling_window_candles)
        window = data.iloc[window_start: i + 1]

        signal = signal_generator(window, strategy_config)
        risk_signal = from_trading_signal(signal)

        account_state = AccountState(
            current_daily_pnl=current_daily_pnl,
            open_trades_count=0,
            consecutive_losses=consecutive_losses,
        )

        risk_config = RiskConfig(
            account_balance=balance,
            risk_per_trade=backtest_config.risk_per_trade,
            max_risk_per_trade=backtest_config.max_risk_per_trade,
            max_daily_loss=backtest_config.max_daily_loss,
            max_open_trades=backtest_config.max_open_trades,
            max_consecutive_losses=backtest_config.max_consecutive_losses,
            min_risk_reward=backtest_config.min_risk_reward,
            value_per_point=backtest_config.value_per_point,
        )

        decision = evaluate_signal_risk(risk_signal, risk_config, account_state)

        if save_signals:
            if save_signals_to_db and signal.side in {"BUY", "SELL"}:
                save_signal_to_db(
                    signal,
                    db_path=db_path,
                    approved_by_risk_manager=decision.approved,
                    blocked_reason=None if decision.approved else decision.reason,
                )

        if not decision.approved:
            i += 1
            continue

        trade_result, exit_index = _simulate_trade_exit(
            data=data,
            entry_index=i,
            side=signal.side,
            entry_price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit),
            position_size=float(decision.position_size),
            value_per_point=backtest_config.value_per_point,
            commission_per_trade=backtest_config.commission_per_trade,
            slippage_points=backtest_config.slippage_points,
        )

        balance_before = balance
        balance += trade_result["profit_loss"]
        current_daily_pnl += trade_result["profit_loss"]

        if trade_result["profit_loss"] < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0

        signal_metadata = _extract_signal_metadata(signal)
        trade_result.update(
            {
                "strategy_name": strategy_name,
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "risk_percent": decision.risk_percent,
                "risk_amount": decision.risk_amount,
                "risk_reward": signal.risk_reward,
                "confidence": signal.confidence,
                "session": signal_metadata["session"] or session_name,
                "setup_type": signal_metadata["setup_type"],
                "score_long": signal_metadata["score_long"],
                "score_short": signal_metadata["score_short"],
                "signal_reason": signal.reason,
                "reason": signal.reason,
                "reason_entry": signal.reason,
                "balance_before": balance_before,
                "balance_after": balance,
            }
        )

        trades.append(trade_result)

        i = max(exit_index + 1, i + 1)

    trades_df = format_trades_for_reporting(pd.DataFrame(trades), strategy_name=strategy_name)
    metrics = calculate_metrics(trades_df, backtest_config.initial_balance)

    return BacktestResult(
        trades=trades_df,
        metrics=metrics,
        final_balance=balance,
    )


def export_backtest_report(result: BacktestResult, output_dir: str | Path = "reports/backtests") -> tuple[Path, Path]:
    """Export trades and metrics to CSV files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_path / "trades.csv"
    trades_by_strategy_path = output_path / TRADES_BY_STRATEGY_FILENAME
    metrics_path = output_path / "metrics.csv"
    trades = format_trades_for_reporting(result.trades)

    trades.to_csv(trades_path, index=False)
    trades.to_csv(trades_by_strategy_path, index=False)
    pd.DataFrame([metrics_to_dict(result.metrics)]).to_csv(metrics_path, index=False)

    return trades_path, metrics_path


def format_trades_for_reporting(
    trades: pd.DataFrame,
    strategy_name: str | None = None,
) -> pd.DataFrame:
    """Return trades with stable reporting columns and backward-compatible aliases."""
    result = trades.copy()

    if "strategy_name" not in result.columns:
        result["strategy_name"] = strategy_name or DEFAULT_STRATEGY_NAME
    elif strategy_name is not None:
        result["strategy_name"] = result["strategy_name"].where(
            result["strategy_name"].notna(),
            strategy_name,
        )

    _copy_alias(result, "timestamp_open", "entry_time")
    _copy_alias(result, "entry_time", "timestamp_open")
    _copy_alias(result, "timestamp_close", "exit_time")
    _copy_alias(result, "exit_time", "timestamp_close")
    _copy_alias(result, "profit_loss", "pnl")
    _copy_alias(result, "pnl", "profit_loss")
    _copy_alias(result, "signal_reason", "reason")
    _copy_alias(result, "reason_entry", "signal_reason")
    _copy_alias(result, "signal_reason", "reason_entry")

    if "side_label" not in result.columns:
        result["side_label"] = result["side"].apply(_side_label) if "side" in result.columns else pd.NA

    if "session" not in result.columns and "entry_time" in result.columns:
        result["session"] = pd.to_datetime(result["entry_time"], errors="coerce").dt.hour.apply(
            lambda hour: classify_hour_to_session(int(hour)) if pd.notna(hour) else "Unknown"
        )

    if "setup_type" not in result.columns and "signal_reason" in result.columns:
        result["setup_type"] = result["signal_reason"].apply(_setup_type_from_reason)

    if "pnl_pct" not in result.columns:
        result["pnl_pct"] = _calculate_pnl_pct(result)

    for column in TRADE_REPORT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    extra_columns = [column for column in result.columns if column not in TRADE_REPORT_COLUMNS]
    return result[TRADE_REPORT_COLUMNS + extra_columns]


def _simulate_trade_exit(
    data: pd.DataFrame,
    entry_index: int,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    position_size: float,
    value_per_point: float,
    commission_per_trade: float,
    slippage_points: float,
) -> tuple[dict, int]:
    """
    Simulate trade exit by scanning candles after entry.

    Conservative rule:
    if SL and TP are both touched in same candle, assume SL first.
    """
    entry_timestamp = data.index[entry_index]

    adjusted_entry = entry_price

    if side == "BUY":
        adjusted_entry += slippage_points
    elif side == "SELL":
        adjusted_entry -= slippage_points
    else:
        raise ValueError("side must be BUY or SELL")

    for j in range(entry_index + 1, len(data)):
        candle = data.iloc[j]
        timestamp_close = data.index[j]

        high = float(candle["High"])
        low = float(candle["Low"])

        if side == "BUY":
            hit_stop = low <= stop_loss
            hit_target = high >= take_profit

            if hit_stop:
                exit_price = stop_loss - slippage_points
                profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
                result = "LOSS"
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = take_profit - slippage_points
                profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
                result = "WIN"
                reason_exit = "Take profit hit"
            else:
                continue

        else:
            hit_stop = high >= stop_loss
            hit_target = low <= take_profit

            if hit_stop:
                exit_price = stop_loss + slippage_points
                profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point
                result = "LOSS"
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = take_profit + slippage_points
                profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point
                result = "WIN"
                reason_exit = "Take profit hit"
            else:
                continue

        profit_loss -= commission_per_trade

        return (
            {
                "timestamp_open": entry_timestamp,
                "timestamp_close": timestamp_close,
                "entry_time": entry_timestamp,
                "exit_time": timestamp_close,
                "side": side,
                "side_label": _side_label(side),
                "entry_price": adjusted_entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "exit_price": exit_price,
                "position_size": position_size,
                "result": result,
                "pnl": profit_loss,
                "profit_loss": profit_loss,
                "bars_in_trade": j - entry_index,
                "reason_exit": reason_exit,
            },
            j,
        )

    last_candle = data.iloc[-1]
    last_timestamp = data.index[-1]
    exit_price = float(last_candle["Close"])

    if side == "BUY":
        profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
    else:
        profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point

    profit_loss -= commission_per_trade

    result = "WIN" if profit_loss > 0 else "LOSS" if profit_loss < 0 else "BREAKEVEN"

    return (
        {
            "timestamp_open": entry_timestamp,
            "timestamp_close": last_timestamp,
            "entry_time": entry_timestamp,
            "exit_time": last_timestamp,
            "side": side,
            "side_label": _side_label(side),
            "entry_price": adjusted_entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "exit_price": exit_price,
            "position_size": position_size,
            "result": result,
            "pnl": profit_loss,
            "profit_loss": profit_loss,
            "bars_in_trade": len(data) - 1 - entry_index,
            "reason_exit": "End of data",
        },
        len(data) - 1,
    )


def _validate_ohlcv(df: pd.DataFrame) -> None:
    """Validate OHLCV columns."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")


def _extract_signal_metadata(signal: TradingSignal) -> dict:
    reason = signal.reason or ""
    score = _parse_optional_float(_extract_reason_field(reason, "score"))
    opposite_score = _parse_optional_float(_extract_reason_field(reason, "opposite_score"))
    score_long = _parse_optional_float(
        _extract_reason_field(reason, "scoreLong")
        or _extract_reason_field(reason, "score_long")
    )
    score_short = _parse_optional_float(
        _extract_reason_field(reason, "scoreShort")
        or _extract_reason_field(reason, "score_short")
    )

    if score is not None and opposite_score is not None:
        if signal.side == "BUY":
            score_long = score if score_long is None else score_long
            score_short = opposite_score if score_short is None else score_short
        elif signal.side == "SELL":
            score_short = score if score_short is None else score_short
            score_long = opposite_score if score_long is None else score_long

    return {
        "session": _extract_reason_field(reason, "session") or _extract_reason_field(reason, "Session"),
        "setup_type": _setup_type_from_reason(reason),
        "score_long": score_long,
        "score_short": score_short,
    }


def _extract_reason_field(reason: str, field_name: str) -> str | None:
    pattern = re.compile(rf"(?:^|\|\s*){re.escape(field_name)}\s*=\s*([^|]+)", re.IGNORECASE)
    match = pattern.search(reason)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _setup_type_from_reason(reason: object) -> str | None:
    if not isinstance(reason, str) or not reason.strip():
        return None
    return reason.split("|", maxsplit=1)[0].strip() or None


def _copy_alias(result: pd.DataFrame, source: str, target: str) -> None:
    if source in result.columns and target not in result.columns:
        result[target] = result[source]


def _calculate_pnl_pct(trades: pd.DataFrame) -> pd.Series:
    if "pnl" not in trades.columns or "balance_before" not in trades.columns:
        return pd.Series([pd.NA] * len(trades), index=trades.index, dtype="object")

    pnl = pd.to_numeric(trades["pnl"], errors="coerce")
    balance_before = pd.to_numeric(trades["balance_before"], errors="coerce")
    return (pnl / balance_before.where(balance_before != 0) * 100.0).astype("float")


def _side_label(side: object) -> str:
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return str(side) if side is not None else "Unknown"
