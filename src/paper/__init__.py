"""Research-only paper trading simulation helpers."""

from src.paper.paper_engine import (
    DEFAULT_PAPER_CONFIG_PATH,
    DEFAULT_PAPER_DAILY_SUMMARY_PATH,
    DEFAULT_PAPER_EQUITY_CURVE_PATH,
    DEFAULT_PAPER_TRADES_PATH,
    PaperTradingConfig,
    load_paper_trading_config,
    run_controlled_paper_simulation,
    simulate_paper_strategy,
)

__all__ = [
    "DEFAULT_PAPER_CONFIG_PATH",
    "DEFAULT_PAPER_DAILY_SUMMARY_PATH",
    "DEFAULT_PAPER_EQUITY_CURVE_PATH",
    "DEFAULT_PAPER_TRADES_PATH",
    "PaperTradingConfig",
    "load_paper_trading_config",
    "run_controlled_paper_simulation",
    "simulate_paper_strategy",
]
