"""
Session analysis utilities.

This module classifies trades by trading session:
- Asia
- London
- New York
- Off Session

Times are interpreted from the trade timestamp hour.
For now we use simple hour windows.
Later this can be improved with timezone handling and daylight saving logic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SessionWindow:
    """Trading session time window."""

    name: str
    start_hour: int
    end_hour: int


DEFAULT_SESSIONS = [
    SessionWindow("Asia", 0, 7),
    SessionWindow("London", 8, 12),
    SessionWindow("New York", 14, 18),
]


def classify_hour_to_session(hour: int, sessions: list[SessionWindow] | None = None) -> str:
    """Classify an hour into a trading session."""
    if hour < 0 or hour > 23:
        raise ValueError("hour must be between 0 and 23")

    if sessions is None:
        sessions = DEFAULT_SESSIONS

    for session in sessions:
        if session.start_hour <= hour < session.end_hour:
            return session.name

    return "Off Session"


def add_session_column(
    trades: pd.DataFrame,
    timestamp_column: str = "timestamp_open",
) -> pd.DataFrame:
    """Add a session column to a trades DataFrame."""
    if trades.empty:
        result = trades.copy()
        result["session"] = []
        return result

    if timestamp_column not in trades.columns:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")

    result = trades.copy()
    result[timestamp_column] = pd.to_datetime(result[timestamp_column], errors="coerce")

    result["session"] = result[timestamp_column].dt.hour.apply(
        lambda hour: classify_hour_to_session(int(hour)) if pd.notna(hour) else "Unknown"
    )

    return result


def calculate_session_summary(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate P&L and win rate by session.

    Required columns:
    - session
    - profit_loss
    """
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "session",
                "total_trades",
                "wins",
                "losses",
                "breakeven",
                "net_profit",
                "win_rate",
                "average_trade",
            ]
        )

    required = ["session", "profit_loss"]
    missing = [column for column in required if column not in trades.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    result = trades.copy()
    result["profit_loss"] = pd.to_numeric(result["profit_loss"], errors="coerce").fillna(0.0)

    rows = []

    for session, group in result.groupby("session"):
        total_trades = len(group)
        wins = int((group["profit_loss"] > 0).sum())
        losses = int((group["profit_loss"] < 0).sum())
        breakeven = int((group["profit_loss"] == 0).sum())
        net_profit = float(group["profit_loss"].sum())
        win_rate = wins / total_trades * 100 if total_trades else 0.0
        average_trade = float(group["profit_loss"].mean()) if total_trades else 0.0

        rows.append(
            {
                "session": session,
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "net_profit": net_profit,
                "win_rate": win_rate,
                "average_trade": average_trade,
            }
        )

    return pd.DataFrame(rows).sort_values("net_profit", ascending=False)
