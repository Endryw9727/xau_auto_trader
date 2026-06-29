"""
Theoretical outcome simulation for V51 candidates (read-only research).

For each directional V51 candidate (entry / stop loss / take profit already
computed by the strategy), this module walks forward over later closed candles
and labels the theoretical outcome (WIN / LOSS / TIMEOUT) together with an R
multiple, so candidate quality can be measured per session, per direction and
per score band.

Conventions, chosen to avoid optimistic bias:
- No lookahead: only candles strictly after the candidate candle are used.
- If a single later candle could hit both stop loss and take profit, the stop is
  assumed to trigger first (worst case).
- TIMEOUT outcomes are marked to market at the horizon close, expressed in R.

This is research/backtest only. It reads a decision log and OHLCV candles. It
never fetches data, never contacts a broker, never imports execution code and
never sends orders.
"""

from __future__ import annotations

import pandas as pd


OUTCOME_COLUMNS: tuple[str, ...] = (
    "signal_id",
    "candle_time",
    "session",
    "side",
    "decision",
    "score",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "outcome",
    "r_multiple",
    "bars_held",
    "exit_time",
    "exit_price",
)

PERFORMANCE_COLUMNS: tuple[str, ...] = (
    "group",
    "trades",
    "wins",
    "losses",
    "timeouts",
    "win_rate",
    "avg_r",
    "total_r",
    "expectancy",
)


def simulate_candidate_outcomes(
    decision_log: pd.DataFrame,
    market_data: pd.DataFrame,
    *,
    max_horizon_candles: int = 32,
    accepted_only: bool = False,
) -> pd.DataFrame:
    """Return per-candidate theoretical outcomes from later closed candles."""
    if decision_log is None or decision_log.empty or "side" not in decision_log.columns:
        return pd.DataFrame(columns=OUTCOME_COLUMNS)
    if max_horizon_candles <= 0:
        raise ValueError("max_horizon_candles must be positive")

    candidates = decision_log[decision_log["side"].astype(str).isin(["BUY", "SELL"])].copy()
    if accepted_only:
        candidates = candidates[candidates.get("decision", "").astype(str).str.upper() == "ACCEPTED"]
    if candidates.empty:
        return pd.DataFrame(columns=OUTCOME_COLUMNS)

    data = _ensure_datetime_index(market_data)
    index = data.index
    candle_times = pd.to_datetime(candidates["candle_time"], errors="coerce")

    rows = []
    for (_, candidate), candle_time in zip(candidates.iterrows(), candle_times):
        rows.append(_simulate_one(candidate, candle_time, data, index, max_horizon_candles))
    return pd.DataFrame(rows, columns=OUTCOME_COLUMNS)


def build_performance_summary(outcomes: pd.DataFrame, *, by: str = "session") -> pd.DataFrame:
    """Aggregate simulated outcomes into a performance table by a grouping key."""
    if outcomes is None or outcomes.empty or by not in outcomes.columns:
        return pd.DataFrame(columns=PERFORMANCE_COLUMNS)

    valid = outcomes[outcomes["outcome"].isin(["WIN", "LOSS", "TIMEOUT"])].copy()
    if valid.empty:
        return pd.DataFrame(columns=PERFORMANCE_COLUMNS)
    valid["r_multiple"] = pd.to_numeric(valid["r_multiple"], errors="coerce")

    rows = [_performance_row(str(key), group) for key, group in valid.groupby(valid[by].astype(str))]
    summary = pd.DataFrame(rows, columns=PERFORMANCE_COLUMNS)
    return summary.sort_values("total_r", ascending=False).reset_index(drop=True)


def build_score_threshold_curve(outcomes: pd.DataFrame, *, thresholds: tuple[float, ...] | None = None) -> pd.DataFrame:
    """Show how expectancy/win-rate change if only candidates with score >= T are kept."""
    if outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=PERFORMANCE_COLUMNS)
    valid = outcomes[outcomes["outcome"].isin(["WIN", "LOSS", "TIMEOUT"])].copy()
    if valid.empty:
        return pd.DataFrame(columns=PERFORMANCE_COLUMNS)
    valid["score"] = pd.to_numeric(valid["score"], errors="coerce")
    valid["r_multiple"] = pd.to_numeric(valid["r_multiple"], errors="coerce")

    if thresholds is None:
        thresholds = (0.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0)

    rows = []
    for threshold in thresholds:
        subset = valid[valid["score"] >= threshold]
        if subset.empty:
            continue
        rows.append(_performance_row(f"score>={threshold:g}", subset))
    return pd.DataFrame(rows, columns=PERFORMANCE_COLUMNS)


def _simulate_one(
    candidate: pd.Series,
    candle_time: pd.Timestamp,
    data: pd.DataFrame,
    index: pd.DatetimeIndex,
    max_horizon_candles: int,
) -> dict:
    side = str(candidate.get("side", ""))
    entry = _float_or_none(candidate.get("entry_price"))
    stop = _float_or_none(candidate.get("stop_loss"))
    target = _float_or_none(candidate.get("take_profit"))
    base = {
        "signal_id": candidate.get("signal_id"),
        "candle_time": candidate.get("candle_time"),
        "session": candidate.get("session"),
        "side": side,
        "decision": candidate.get("decision"),
        "score": candidate.get("score"),
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit": target,
        "risk_reward": _float_or_none(candidate.get("risk_reward")),
        "outcome": "INVALID",
        "r_multiple": None,
        "bars_held": 0,
        "exit_time": None,
        "exit_price": None,
    }
    if entry is None or stop is None or target is None or pd.isna(candle_time):
        return base
    risk = abs(entry - stop)
    if risk <= 0:
        return base

    future = data[index > candle_time]
    if future.empty:
        return base
    future = future.head(max_horizon_candles)

    for bars, (exit_time, candle) in enumerate(future.iterrows(), start=1):
        high = float(candle["High"])
        low = float(candle["Low"])
        hit_stop, hit_target = _hits(side, low, high, stop, target)
        if hit_stop:  # worst case first
            return {**base, "outcome": "LOSS", "r_multiple": -1.0, "bars_held": bars, "exit_time": exit_time, "exit_price": stop}
        if hit_target:
            reward_r = abs(target - entry) / risk
            return {**base, "outcome": "WIN", "r_multiple": reward_r, "bars_held": bars, "exit_time": exit_time, "exit_price": target}

    last_time = future.index[-1]
    last_close = float(future.iloc[-1]["Close"])
    mark = (last_close - entry) / risk if side == "BUY" else (entry - last_close) / risk
    return {
        **base,
        "outcome": "TIMEOUT",
        "r_multiple": round(mark, 4),
        "bars_held": int(len(future)),
        "exit_time": last_time,
        "exit_price": last_close,
    }


def _hits(side: str, low: float, high: float, stop: float, target: float) -> tuple[bool, bool]:
    if side == "BUY":
        return low <= stop, high >= target
    return high >= stop, low <= target


def _performance_row(group_name: str, group: pd.DataFrame) -> dict:
    r_values = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
    trades = int(len(group))
    wins = int((group["outcome"] == "WIN").sum())
    losses = int((group["outcome"] == "LOSS").sum())
    timeouts = int((group["outcome"] == "TIMEOUT").sum())
    total_r = float(r_values.sum())
    return {
        "group": group_name,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate": round(100.0 * wins / trades, 2) if trades else 0.0,
        "avg_r": round(float(r_values.mean()), 4) if not r_values.empty else 0.0,
        "total_r": round(total_r, 4),
        "expectancy": round(total_r / trades, 4) if trades else 0.0,
    }


def _ensure_datetime_index(market_data: pd.DataFrame) -> pd.DataFrame:
    if market_data is None or market_data.empty:
        return pd.DataFrame()
    data = market_data.copy()
    if isinstance(data.index, pd.DatetimeIndex):
        return data.sort_index()
    for column in ("Date", "time", "timestamp"):
        if column in data.columns:
            data[column] = pd.to_datetime(data[column], errors="coerce")
            data = data.dropna(subset=[column]).set_index(column)
            return data.sort_index()
    raise ValueError("market_data must have a DatetimeIndex or a Date/time column")


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
