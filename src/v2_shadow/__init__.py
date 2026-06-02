"""Read-only V2 shadow reporting components.

This package intentionally does not import broker, execution, scheduler, MT5,
paper engine, ML, or live-trading modules. It is a diagnostic adapter for V1.
"""

from src.v2_shadow.report import V2ShadowReport, run_v2_shadow_report

__all__ = ["V2ShadowReport", "run_v2_shadow_report"]
