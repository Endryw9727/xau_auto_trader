"""Serve the read-only research API for the console UI.

    python scripts/serve_research_api.py --host 0.0.0.0 --port 8000

Then point the console app's API_BASE_URL at this server. Set RESEARCH_API_TOKEN
to require a bearer token. This serves diagnostics only and cannot send orders.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import uvicorn

    print("=" * 72)
    print("XAU Auto Trader - Research API (read-only, no orders)")
    print(f"Listening on http://{args.host}:{args.port}  (live_armed=false)")
    print("=" * 72)
    uvicorn.run("src.api.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
