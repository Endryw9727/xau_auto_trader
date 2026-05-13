"""
Frozen paper-candidate configuration.

This module validates paper-only candidate settings. It does not import live
execution code or place orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_PAPER_CANDIDATE_CONFIG_PATH = Path("config/paper_candidate.yaml")
PAPER_MAIN_STRATEGY = "proxy_hardened_no_worst_hours_high_margin"
PAPER_RESEARCH_STRATEGY = "proxy_hardened_no_worst_hours"
PAPER_EMERGENCY_MODE = "dynamic_normal_defensive_pause"


@dataclass(frozen=True)
class PaperCandidateConfig:
    """Frozen paper-candidate settings."""

    paper_main_strategy: str
    research_strategy: str
    emergency_mode: str
    allow_live: bool
    paper_mode: bool
    max_trades_per_day: int
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    warning_drawdown_pct: float
    stop_drawdown_pct: float
    min_recent_50_pf_warning: float
    min_recent_50_pf_stop: float
    min_trade_day_required: float


def load_paper_candidate_config(path: str | Path = DEFAULT_PAPER_CANDIDATE_CONFIG_PATH) -> PaperCandidateConfig:
    """Load and validate the frozen paper candidate config."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Paper candidate config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    if not isinstance(raw, dict):
        raise ValueError("paper_candidate.yaml must contain a YAML dictionary")

    config = PaperCandidateConfig(
        paper_main_strategy=str(raw.get("paper_main_strategy", "")),
        research_strategy=str(raw.get("research_strategy", "")),
        emergency_mode=str(raw.get("emergency_mode", "")),
        allow_live=bool(raw.get("allow_live", False)),
        paper_mode=bool(raw.get("paper_mode", True)),
        max_trades_per_day=int(raw.get("max_trades_per_day", 2)),
        max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 3.0)),
        max_weekly_loss_pct=float(raw.get("max_weekly_loss_pct", 8.0)),
        warning_drawdown_pct=float(raw.get("warning_drawdown_pct", 8.0)),
        stop_drawdown_pct=float(raw.get("stop_drawdown_pct", 12.0)),
        min_recent_50_pf_warning=float(raw.get("min_recent_50_pf_warning", 1.05)),
        min_recent_50_pf_stop=float(raw.get("min_recent_50_pf_stop", 1.00)),
        min_trade_day_required=float(raw.get("min_trade_day_required", 0.50)),
    )
    validate_paper_candidate_config(config)
    return config


def validate_paper_candidate_config(config: PaperCandidateConfig) -> None:
    """Validate paper-only candidate settings."""
    if config.paper_main_strategy != PAPER_MAIN_STRATEGY:
        raise ValueError(f"paper_main_strategy must be {PAPER_MAIN_STRATEGY}")
    if config.research_strategy != PAPER_RESEARCH_STRATEGY:
        raise ValueError(f"research_strategy must be {PAPER_RESEARCH_STRATEGY}")
    if config.emergency_mode != PAPER_EMERGENCY_MODE:
        raise ValueError(f"emergency_mode must be {PAPER_EMERGENCY_MODE}")
    if config.allow_live:
        raise ValueError("allow_live must remain false")
    if not config.paper_mode:
        raise ValueError("paper_mode must remain true")
    if config.max_trades_per_day <= 0:
        raise ValueError("max_trades_per_day must be positive")
    if config.min_trade_day_required <= 0:
        raise ValueError("min_trade_day_required must be positive")
