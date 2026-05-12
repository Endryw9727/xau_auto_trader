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
from src.paper.paper_monitor import (
    DEFAULT_PAPER_MONITOR_SUMMARY_PATH,
    DEFAULT_PAPER_VALIDATION_STATUS_PATH,
    PaperValidationRules,
    build_monitor_summary,
    build_validation_status,
    load_validation_rules,
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
    "DEFAULT_PAPER_MONITOR_SUMMARY_PATH",
    "DEFAULT_PAPER_VALIDATION_STATUS_PATH",
    "PaperValidationRules",
    "build_monitor_summary",
    "build_validation_status",
    "load_validation_rules",
]
