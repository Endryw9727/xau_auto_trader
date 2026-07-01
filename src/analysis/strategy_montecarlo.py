"""
Per-strategy Monte Carlo outcome distribution (read-only research).

For every strategy in the edge family we take its *realised* historical per-trade
returns and bootstrap thousands of possible 100-trade sequences, to answer the
practical question in plain terms: "over the next 100 trades, is this strategy
likely to be in profit, and what drawdown / risk of ruin does it carry?"

This is the honest, statistics-first view the project is built around: a strategy
does not need to win every trade — it needs positive expectancy and survivable
variance. The numbers here *describe* that variance; they never size positions,
never send orders, never relax a risk gate.

Note on interpretation: the session-drift strategies have no designed stop/target,
so ``reward_risk`` and ``win_rate`` here are the *realised* payoff profile of the
raw session move, not a designed R:R. It is descriptive, not a promise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.trade_simulation import bootstrap_monte_carlo, expectancy_r

STRATEGY_MC_COLUMNS: tuple[str, ...] = (
    "strategy",
    "trades",
    "win_rate",
    "reward_risk",
    "expectancy_r",
    "prob_profit",
    "median_return",
    "median_max_drawdown",
    "prob_ruin",
)

# A strategy needs a minimum trade history for a resample to mean anything.
_MIN_TRADES = 20


def _realised_profile(returns_pct: np.ndarray) -> tuple[float, float]:
    """Realised (win_rate, reward:risk) from a per-trade percent-return series."""
    wins = returns_pct[returns_pct > 0]
    losses = returns_pct[returns_pct < 0]
    win_rate = float(wins.size) / float(returns_pct.size) if returns_pct.size else 0.0
    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(-losses.mean()) if losses.size else 0.0
    reward_risk = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    return win_rate, reward_risk


def strategy_outcome_table(
    series_by_strategy: dict[str, pd.Series],
    *,
    n_sims: int = 1000,
    n_trades: int = 100,
    ruin_drawdown: float = 0.5,
    seed: int = 0,
) -> list[dict]:
    """Bootstrap Monte Carlo of each strategy's next ``n_trades`` trades.

    Returns one JSON-friendly row per strategy (>= ``_MIN_TRADES`` trades),
    sorted by expectancy (best first).
    """
    rows: list[dict] = []
    for name, series in series_by_strategy.items():
        returns_pct = np.asarray(pd.Series(series).dropna(), dtype=float)
        returns_pct = returns_pct[np.isfinite(returns_pct)]
        if returns_pct.size < _MIN_TRADES:
            continue
        win_rate, reward_risk = _realised_profile(returns_pct)
        # Compound in fraction space (percent -> fraction).
        try:
            mc = bootstrap_monte_carlo(
                returns_pct / 100.0,
                n_trades=n_trades,
                n_sims=n_sims,
                ruin_drawdown=ruin_drawdown,
                seed=seed,
            )
        except ValueError:
            continue
        rows.append(
            {
                "strategy": name,
                "trades": int(returns_pct.size),
                "win_rate": round(win_rate, 4),
                "reward_risk": round(reward_risk, 3),
                "expectancy_r": round(expectancy_r(win_rate, reward_risk), 4),
                "prob_profit": round(mc.prob_profit, 4),
                "median_return": round(mc.median_return, 4),
                "median_max_drawdown": round(mc.median_max_drawdown, 4),
                "prob_ruin": round(mc.prob_ruin, 4),
            }
        )
    rows.sort(key=lambda row: row["expectancy_r"], reverse=True)
    return rows


def montecarlo_summary(rows: list[dict]) -> dict:
    """Family-level headline from the per-strategy Monte Carlo table."""
    if not rows:
        return {"status": "INSUFFICIENT_DATA", "n_strategies": 0, "n_profitable": 0}
    profitable = [r for r in rows if r["expectancy_r"] > 0 and r["prob_profit"] >= 0.5]
    best = rows[0]
    return {
        "status": "OK",
        "n_strategies": len(rows),
        "n_profitable": len(profitable),
        "best_strategy": best["strategy"],
        "best_prob_profit": best["prob_profit"],
        "best_expectancy_r": best["expectancy_r"],
    }
