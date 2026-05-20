"""Run one read-only Control Room monitoring pass."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.control_room.orchestrator import DEFAULT_CONTROL_ROOM_CONFIG_PATH, DEFAULT_CONTROL_ROOM_OUTPUT_DIR, run_control_room_once


def main() -> None:
    """Run one Control Room pass and print a console report."""
    args = parse_args()
    output_dir = Path(args.output_dir or os.environ.get("CONTROL_ROOM_OUTPUT_DIR", DEFAULT_CONTROL_ROOM_OUTPUT_DIR))
    result = run_control_room_once(config_path=args.config, output_dir=output_dir)

    print("=" * 72)
    print("XAU Auto Trader - Control Room")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print("")
    for name, snapshot in result.snapshots.items():
        print(f"[{name.upper()}] {snapshot.get('status', 'OK')}: {snapshot.get('reason', '')}")
    print("")
    print("Outputs:")
    for name, path in result.output_paths.items():
        print(f"- {name}: {path}")
    print("")
    print("Read-only monitor only. No real or demo orders are submitted by Control Room.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONTROL_ROOM_CONFIG_PATH))
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
