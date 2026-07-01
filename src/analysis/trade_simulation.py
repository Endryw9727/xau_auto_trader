"""
Expectancy and Monte Carlo trade-outcome simulation (read-only research).

The point of this module is the honest core of professional trading: you do NOT
need to win every trade. With an adequate reward/risk you can be very profitable
while losing most of your trades — what matters is *positive expectancy* and
understanding *variance*.

Two questions it answers:

1. Expectancy / break-even win rate. Given a reward:risk ratio R, the break-even
   win rate is ``1 / (1 + R)`` (e.g. R = 2 -> you only need to win 33.3%). The
   expectancy per trade (in R units, a loss = -1R) is
   ``win_rate * R - (1 - win_rate)``.

2. Monte Carlo. Run thousands of possible trade *sequences* to see the whole
   distribution of outcomes — final equity, worst drawdown, probability of
   ending in profit, probability of ruin. Even a positive-expectancy system has
   losing streaks; this makes that variance explicit instead of hiding it.

Pure statistics: no IO, no execution, no orders, no position sizing changes. It
only *describes* outcome distributions so a human can judge them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------- #
# Expectancy (closed form)
# --------------------------------------------------------------------------- #
def breakeven_win_rate(reward_risk: float) -> float:
    """Win rate at which a fixed reward:risk system exactly breaks even."""
    if reward_risk <= 0:
        return 1.0
    return 1.0 / (1.0 + reward_risk)


def expectancy_r(win_rate: float, reward_risk: float) -> float:
    """Expected profit per trade in R units (a full loss is -1R)."""
    win_rate = min(max(win_rate, 0.0), 1.0)
    return win_rate * reward_risk - (1.0 - win_rate)


def required_win_rate(reward_risk: float, *, target_expectancy_r: float = 0.0) -> float:
    """Win rate needed to reach a target expectancy (default 0 = break-even)."""
    if reward_risk <= -1.0:
        return 1.0
    wr = (target_expectancy_r + 1.0) / (reward_risk + 1.0)
    return min(max(wr, 0.0), 1.0)


def kelly_fraction(win_rate: float, reward_risk: float) -> float:
    """Kelly-optimal fraction of capital to risk (reference only, never auto-used).

    Returns 0 for non-positive-edge inputs. Real sizing stays governed by the risk
    manager and the YAML caps — this is just the theoretical ceiling.
    """
    if reward_risk <= 0:
        return 0.0
    win_rate = min(max(win_rate, 0.0), 1.0)
    kelly = win_rate - (1.0 - win_rate) / reward_risk
    return max(0.0, kelly)


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MonteCarloResult:
    """Distribution of outcomes across many simulated trade sequences."""

    n_sims: int
    n_trades: int
    expectancy_r: float
    prob_profit: float           # P(final equity > start)
    prob_ruin: float             # P(equity ever falls below the ruin threshold)
    median_return: float         # median final return (fraction, e.g. 0.12 = +12%)
    p05_return: float
    p95_return: float
    median_max_drawdown: float   # negative fraction, e.g. -0.18
    worst_max_drawdown: float

    def as_dict(self) -> dict:
        return {
            "n_sims": self.n_sims,
            "n_trades": self.n_trades,
            "expectancy_r": round(self.expectancy_r, 4),
            "prob_profit": round(self.prob_profit, 4),
            "prob_ruin": round(self.prob_ruin, 4),
            "median_return": round(self.median_return, 4),
            "p05_return": round(self.p05_return, 4),
            "p95_return": round(self.p95_return, 4),
            "median_max_drawdown": round(self.median_max_drawdown, 4),
            "worst_max_drawdown": round(self.worst_max_drawdown, 4),
        }


def _summarise(factors: np.ndarray, *, n_trades: int, expectancy: float,
               ruin_drawdown: float) -> MonteCarloResult:
    """Turn a (n_sims x n_trades) matrix of per-trade growth factors into stats."""
    equity = np.cumprod(factors, axis=1)
    running_max = np.maximum.accumulate(equity, axis=1)
    drawdown = equity / running_max - 1.0
    max_dd = drawdown.min(axis=1)
    final_return = equity[:, -1] - 1.0
    n_sims = factors.shape[0]
    return MonteCarloResult(
        n_sims=n_sims,
        n_trades=n_trades,
        expectancy_r=expectancy,
        prob_profit=float((final_return > 0).mean()),
        prob_ruin=float((max_dd <= -abs(ruin_drawdown)).mean()),
        median_return=float(np.median(final_return)),
        p05_return=float(np.percentile(final_return, 5)),
        p95_return=float(np.percentile(final_return, 95)),
        median_max_drawdown=float(np.median(max_dd)),
        worst_max_drawdown=float(max_dd.min()),
    )


def monte_carlo_fixed(
    win_rate: float,
    reward_risk: float,
    *,
    n_trades: int = 100,
    n_sims: int = 1000,
    risk_per_trade: float = 0.01,
    ruin_drawdown: float = 0.5,
    seed: int = 0,
) -> MonteCarloResult:
    """Monte Carlo a fixed win-rate / reward:risk system with fixed-fractional risk.

    Each trade risks ``risk_per_trade`` of current equity: a win multiplies equity
    by ``1 + reward_risk * risk_per_trade``, a loss by ``1 - risk_per_trade``.
    ``ruin_drawdown`` is the peak-to-trough loss counted as ruin (default 50%).
    """
    if not 0.0 <= win_rate <= 1.0:
        raise ValueError("win_rate must be in [0, 1]")
    if n_trades < 1 or n_sims < 1:
        raise ValueError("n_trades and n_sims must be >= 1")
    rng = np.random.default_rng(seed)
    wins = rng.random((n_sims, n_trades)) < win_rate
    win_factor = 1.0 + reward_risk * risk_per_trade
    loss_factor = 1.0 - risk_per_trade
    factors = np.where(wins, win_factor, loss_factor)
    return _summarise(
        factors, n_trades=n_trades,
        expectancy=expectancy_r(win_rate, reward_risk), ruin_drawdown=ruin_drawdown,
    )


def bootstrap_monte_carlo(
    trade_returns,
    *,
    n_trades: int | None = None,
    n_sims: int = 1000,
    ruin_drawdown: float = 0.5,
    seed: int = 0,
) -> MonteCarloResult:
    """Monte Carlo by resampling *historical* per-trade returns (fractions).

    ``trade_returns`` is a sequence of realised per-trade returns (e.g. 0.012 for
    +1.2%). Each simulation draws ``n_trades`` of them with replacement and
    compounds. This keeps the real fat tails / skew of the strategy instead of
    assuming a clean win/loss model.
    """
    returns = np.asarray(trade_returns, dtype=float)
    returns = returns[np.isfinite(returns)]
    if returns.size == 0:
        raise ValueError("trade_returns is empty")
    if n_trades is None:
        n_trades = int(returns.size)
    if n_trades < 1 or n_sims < 1:
        raise ValueError("n_trades and n_sims must be >= 1")
    rng = np.random.default_rng(seed)
    sampled = rng.choice(returns, size=(n_sims, n_trades), replace=True)
    factors = 1.0 + sampled
    win_rate = float((returns > 0).mean())
    avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0.0
    avg_loss = -returns[returns < 0].mean() if (returns < 0).any() else 0.0
    rr = float(avg_win / avg_loss) if avg_loss > 0 else 0.0
    return _summarise(
        factors, n_trades=n_trades,
        expectancy=expectancy_r(win_rate, rr), ruin_drawdown=ruin_drawdown,
    )


def expectancy_report(reward_risk: float, win_rate: float) -> dict:
    """Closed-form expectancy summary for a reward:risk / win-rate pair."""
    be = breakeven_win_rate(reward_risk)
    exp = expectancy_r(win_rate, reward_risk)
    return {
        "reward_risk": round(reward_risk, 4),
        "win_rate": round(win_rate, 4),
        "breakeven_win_rate": round(be, 4),
        "expectancy_r": round(exp, 4),
        "edge": round(win_rate - be, 4),           # margin above break-even
        "profitable": bool(exp > 0),
        "kelly_fraction": round(kelly_fraction(win_rate, reward_risk), 4),
    }
