"""Run a full read-only Control Room cycle."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.control_room.orchestrator import DEFAULT_CONTROL_ROOM_CONFIG_PATH, DEFAULT_CONTROL_ROOM_OUTPUT_DIR, run_control_room_cycle


def main() -> None:
    """Run all Control Room monitors once."""
    args = parse_args()
    output_dir = Path(args.output_dir or os.environ.get("CONTROL_ROOM_OUTPUT_DIR", DEFAULT_CONTROL_ROOM_OUTPUT_DIR))
    result = run_control_room_cycle(config_path=args.config, output_dir=output_dir)
    print("=" * 72)
    print("XAU Auto Trader - Control Room Cycle")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print("Components: market, account, risk, signal, shadow, telegram, audit")
    print("No execution is available from this script.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONTROL_ROOM_CONFIG_PATH))
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
