"""
Report-only demo readiness for V51 (Phase 3, no execution).

This is the *report-only phase before execution* described in the project
roadmap. It simulates, from theoretical outcomes, how the proposed protective
guardrails would have behaved on the accepted V51 candidates:

- a per-day trade cap (max_trades_per_day),
- a daily-loss lock (stop trading for the day after a loss budget in R),
- a drawdown lock (overall equity drawdown budget in R).

It also produces a read-only safety checklist over the V51 config flags so it is
obvious that execution stays disabled.

It NEVER enables execution, NEVER changes config or flags, NEVER imports
execution code and NEVER sends orders. It only reads outcomes and config to
report what *would* happen. Arming demo execution remains a separate, explicit,
manual decision.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


DAILY_EQUITY_COLUMNS: tuple[str, ...] = (
    "day",
    "trades_taken",
    "daily_r",
    "cumulative_r",
    "drawdown_r",
    "hit_daily_loss_lock",
)

READINESS_CHECKLIST_COLUMNS: tuple[str, ...] = (
    "check",
    "value",
    "expected",
    "status",
)


@dataclass(frozen=True)
class GuardrailEvaluation:
    """Aggregate guardrail behaviour over the simulated accepted candidates."""

    trading_days: int
    total_trades: int
    capped_trades: int
    total_r: float
    max_drawdown_r: float
    daily_loss_lock_days: int
    drawdown_lock_hit: bool
    worst_day_r: float


def simulate_daily_equity(
    outcomes: pd.DataFrame,
    *,
    max_trades_per_day: int = 2,
    daily_loss_limit_r: float = 2.0,
) -> pd.DataFrame:
    """Simulate a day-by-day R equity curve for accepted candidates only.

    Within each day, trades are taken in time order up to ``max_trades_per_day``;
    once the cumulative daily loss reaches ``daily_loss_limit_r`` the day is
    locked and no further trades are counted (daily-loss lock).
    """
    accepted = _accepted_outcomes(outcomes)
    if accepted.empty:
        return pd.DataFrame(columns=DAILY_EQUITY_COLUMNS)
    if max_trades_per_day <= 0:
        raise ValueError("max_trades_per_day must be positive")
    if daily_loss_limit_r <= 0:
        raise ValueError("daily_loss_limit_r must be positive")

    accepted = accepted.sort_values("_time")
    rows = []
    cumulative = 0.0
    peak = 0.0
    for day, group in accepted.groupby(accepted["_time"].dt.normalize(), sort=True):
        daily_r = 0.0
        trades_taken = 0
        locked = False
        for r_value in group["_r"].tolist():
            if trades_taken >= max_trades_per_day or locked:
                break
            daily_r += float(r_value)
            trades_taken += 1
            if daily_r <= -abs(daily_loss_limit_r):
                locked = True
        cumulative += daily_r
        peak = max(peak, cumulative)
        rows.append(
            {
                "day": pd.Timestamp(day),
                "trades_taken": int(trades_taken),
                "daily_r": round(daily_r, 4),
                "cumulative_r": round(cumulative, 4),
                "drawdown_r": round(cumulative - peak, 4),
                "hit_daily_loss_lock": bool(locked),
            }
        )
    return pd.DataFrame(rows, columns=DAILY_EQUITY_COLUMNS)


def evaluate_guardrails(
    outcomes: pd.DataFrame,
    *,
    max_trades_per_day: int = 2,
    daily_loss_limit_r: float = 2.0,
    max_drawdown_r: float = 4.0,
) -> GuardrailEvaluation:
    """Summarize how the protective guardrails would behave on accepted candidates."""
    accepted = _accepted_outcomes(outcomes)
    total_candidates = int(len(accepted))
    daily = simulate_daily_equity(
        outcomes, max_trades_per_day=max_trades_per_day, daily_loss_limit_r=daily_loss_limit_r
    )
    if daily.empty:
        return GuardrailEvaluation(0, 0, 0, 0.0, 0.0, 0, False, 0.0)

    total_trades = int(daily["trades_taken"].sum())
    max_drawdown = float(daily["drawdown_r"].min())
    return GuardrailEvaluation(
        trading_days=int(len(daily)),
        total_trades=total_trades,
        capped_trades=max(0, total_candidates - total_trades),
        total_r=round(float(daily["daily_r"].sum()), 4),
        max_drawdown_r=round(max_drawdown, 4),
        daily_loss_lock_days=int(daily["hit_daily_loss_lock"].sum()),
        drawdown_lock_hit=bool(max_drawdown <= -abs(max_drawdown_r)),
        worst_day_r=round(float(daily["daily_r"].min()), 4),
    )


def build_readiness_checklist(config) -> pd.DataFrame:
    """Build a read-only safety checklist from the V51 config flags.

    This never changes the config; it only reports whether the execution gates
    are in their safe (disabled) state.
    """
    checks = [
        ("allow_real_live", _get(config, "allow_real_live"), False),
        ("demo_only", _get(config, "demo_only"), True),
        ("allow_demo_execution", _get(config, "allow_demo_execution"), False),
        ("execution_enabled", _get(config, "execution_enabled"), False),
        ("max_open_positions", _get(config, "max_open_positions"), 1),
    ]
    rows = []
    for name, value, expected in checks:
        rows.append(
            {
                "check": name,
                "value": value,
                "expected": expected,
                "status": "OK" if value == expected else "REVIEW",
            }
        )
    return pd.DataFrame(rows, columns=READINESS_CHECKLIST_COLUMNS)


def _accepted_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=["_time", "_r"])
    needed = {"decision", "candle_time", "r_multiple", "outcome"}
    if not needed.issubset(outcomes.columns):
        return pd.DataFrame(columns=["_time", "_r"])
    accepted = outcomes[
        (outcomes["decision"].astype(str).str.upper() == "ACCEPTED")
        & (outcomes["outcome"].isin(["WIN", "LOSS", "TIMEOUT"]))
    ].copy()
    if accepted.empty:
        return pd.DataFrame(columns=["_time", "_r"])
    accepted["_time"] = pd.to_datetime(accepted["candle_time"], errors="coerce")
    accepted["_r"] = pd.to_numeric(accepted["r_multiple"], errors="coerce")
    accepted = accepted.dropna(subset=["_time", "_r"])
    return accepted


def _get(config, name):
    if isinstance(config, dict):
        return config.get(name)
    return getattr(config, name, None)
