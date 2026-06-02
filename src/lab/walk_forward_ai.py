"""
Walk-Forward Analysis with AI-driven strategy selection.

Runs backtests across different market regimes and selects
the best strategy profile for each regime based on performance.

Usage:
    python scripts/run_walk_forward_ai.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.backtesting.backtester import BacktestConfig, BacktestResult, run_backtest
from src.data_feed.market_data import load_csv_data
from src.lab.strategy_selector import StrategyProfile, StrategySelector, apply_profile_to_config
from src.ml.regime_detector import detect_regime
from src.strategy.rules import StrategyConfig

@dataclass(frozen=True)
class WalkForwardResult:
    """Result of walk-forward analysis."""

    regime: str
    profile_name: str
    trades: int
    win_rate: float
    profit_factor: float
    net_profit: float
    max_drawdown: float
    recommendation: str


def run_walk_forward_analysis(
    df: pd.DataFrame,
    window_size: int = 1000,
    step_size: int = 500,
    profiles: list[StrategyProfile] | None = None,
) -> list[WalkForwardResult]:
    """
    Run walk-forward analysis with regime-based strategy selection.

    Parameters:
    - df: OHLCV DataFrame
    - window_size: candles per window
    - step_size: candles to step forward
    - profiles: optional custom strategy profiles

    Returns:
    - List of WalkForwardResult
    """
    if len(df) < window_size * 2:
        raise ValueError(f"Need at least {window_size * 2} candles for walk-forward analysis")

    selector = StrategySelector(profiles)
    results: list[WalkForwardResult] = []

    for start in range(0, len(df) - window_size * 2, step_size):
        # In-sample: detect regime
        in_sample = df.iloc[start:start + window_size]
        regime = detect_regime(in_sample)

        # Select profile for regime
        profile, _ = selector.select(in_sample)

        # Out-of-sample: test profile
        out_sample = df.iloc[start + window_size:start + window_size * 2]

        strategy_config = StrategyConfig(
            atr_multiplier_sl=profile.atr_multiplier_sl,
            atr_multiplier_tp=profile.atr_multiplier_tp,
            rsi_buy_max=profile.rsi_buy_max,
            rsi_sell_min=profile.rsi_sell_min,
            min_adx=profile.min_adx,
            min_risk_reward=profile.min_risk_reward,
        )

        backtest_config = BacktestConfig(
            initial_balance=1000,
            warmup_candles=220,
            rolling_window_candles=window_size,
        )

        try:
            result = run_backtest(out_sample, strategy_config, backtest_config)

            if not result.trades.empty:
                metrics = result.metrics.set_index("metric")["value"].to_dict()
                results.append(WalkForwardResult(
                    regime=regime.regime,
                    profile_name=profile.name,
                    trades=int(metrics.get("total_trades", 0)),
                    win_rate=float(metrics.get("win_rate", 0)),
                    profit_factor=float(metrics.get("profit_factor", 0)),
                    net_profit=float(metrics.get("net_profit", 0)),
                    max_drawdown=float(metrics.get("max_drawdown", 0)),
                    recommendation=regime.recommendation,
                ))
        except Exception as e:
            print(f"Window {start}-{start + window_size * 2} failed: {e}")
            continue

    return results


def summarize_walk_forward(results: list[WalkForwardResult]) -> pd.DataFrame:
    """Summarize walk-forward results by regime."""
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "regime": r.regime,
        "profile": r.profile_name,
        "trades": r.trades,
        "win_rate": r.win_rate,
        "profit_factor": r.profit_factor,
        "net_profit": r.net_profit,
        "max_drawdown": r.max_drawdown,
    } for r in results])

    summary = df.groupby(["regime", "profile"]).agg({
        "trades": "sum",
        "win_rate": "mean",
        "profit_factor": "mean",
        "net_profit": "sum",
        "max_drawdown": "max",
    }).reset_index()

    return summary


def export_walk_forward_report(
    results: list[WalkForwardResult],
    output_dir: Path = Path("reports/strategy_lab"),
) -> tuple[Path, Path]:
    """Export walk-forward results to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / "walk_forward_raw.csv"
    summary_path = output_dir / "walk_forward_summary.csv"

    raw_df = pd.DataFrame([{
        "regime": r.regime,
        "profile": r.profile_name,
        "trades": r.trades,
        "win_rate": r.win_rate,
        "profit_factor": r.profit_factor,
        "net_profit": r.net_profit,
        "max_drawdown": r.max_drawdown,
        "recommendation": r.recommendation,
    } for r in results])

    raw_df.to_csv(raw_path, index=False)

    summary = summarize_walk_forward(results)
    summary.to_csv(summary_path, index=False)

    return raw_path, summary_path
