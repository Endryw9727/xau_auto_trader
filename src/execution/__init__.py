"""Disabled future execution layer placeholder.

No live trading connector is implemented here. The module exists only to keep a
future execution boundary separate from research, AI, risk, and monitoring.
"""

EXECUTION_LAYER_ENABLED = False
ALLOW_LIVE = False

__all__ = ["EXECUTION_LAYER_ENABLED", "ALLOW_LIVE"]
