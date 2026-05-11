"""Strategy Lab package for comparing research strategies."""

from src.strategy_lab.lab import (
    StrategyLabResult,
    StrategySpec,
    get_default_strategy_specs,
    run_strategy_lab,
)
from src.strategy_lab import (
    strategy_v1,
    strategy_v2,
    strategy_v3,
    strategy_v4,
    strategy_v5,
    strategy_v6,
    strategy_v50_candidates,
    strategy_v50_pine,
    v50_daily_coverage,
    v50_daily_coverage_sweep,
    v50_growth_refinement_sweep,
    v50_loss_filter_sweep,
    v50_loss_intelligence,
    v50_monte_carlo,
    v50_stress_test,
)

__all__ = [
    "StrategyLabResult",
    "StrategySpec",
    "get_default_strategy_specs",
    "run_strategy_lab",
    "strategy_v1",
    "strategy_v2",
    "strategy_v3",
    "strategy_v4",
    "strategy_v5",
    "strategy_v6",
    "strategy_v50_candidates",
    "strategy_v50_pine",
    "v50_daily_coverage",
    "v50_daily_coverage_sweep",
    "v50_growth_refinement_sweep",
    "v50_loss_filter_sweep",
    "v50_loss_intelligence",
    "v50_monte_carlo",
    "v50_stress_test",
]
