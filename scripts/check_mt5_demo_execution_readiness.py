"""Check MT5 demo execution readiness without submitting any request."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.execution.mt5_demo_executor import check_demo_execution_readiness, load_demo_execution_config


def main() -> None:
    """Print MT5 demo execution readiness."""
    print("=" * 72)
    print("XAU Auto Trader - MT5 Demo Execution Readiness")
    print("=" * 72)

    try:
        config = load_demo_execution_config()
    except Exception as exc:
        print("Status: ERROR")
        print(f"Reason: {exc}")
        return

    readiness = check_demo_execution_readiness()
    print(f"Broker: {config.broker_name}")
    print(f"Platform: {config.platform}")
    print(f"Symbol: {config.symbol}")
    print(f"demo_only: {config.demo_only}")
    print(f"allow_demo_execution: {config.allow_demo_execution}")
    print(f"allow_real_live: {config.allow_real_live}")
    print(f"execution_enabled: {config.execution_enabled}")
    print(f"MT5 initialized: {readiness.mt5_initialized}")
    print(f"Account connected: {readiness.account_connected}")
    print(f"Account demo: {readiness.account_demo}")
    print(f"Trade allowed: {readiness.trade_allowed}")
    print(f"Symbol found: {readiness.symbol_found}")
    print(f"Symbol visible: {readiness.symbol_visible}")
    print(f"Volume min: {readiness.volume_min}")
    print(f"Volume step: {readiness.volume_step}")
    print(f"Stops level: {readiness.stops_level}")
    print(f"Filling mode: {readiness.filling_mode}")
    print(f"Current spread points: {readiness.spread_current}")
    print(f"Status: {readiness.status}")
    print(f"Reason: {readiness.reason}")
    print("No request was submitted. Real live execution remains disabled.")


if __name__ == "__main__":
    main()
