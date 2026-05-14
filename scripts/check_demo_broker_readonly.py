"""Check safe demo broker read-only configuration and snapshots."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.broker.demo_broker_guardrails import assert_no_real_order_method_available
from src.broker.demo_broker_readonly import DemoBrokerReadOnlyClient, MT5_MOCK_STATUS


def main() -> None:
    """Print a read-only demo broker status report."""
    print("=" * 72)
    print("XAU Auto Trader - Demo Broker Read-Only Check")
    print("=" * 72)

    try:
        client = DemoBrokerReadOnlyClient.from_config_file()
        assert_no_real_order_method_available(client)
        config = client.config
        account = client.account_snapshot()
        symbol = client.symbol_snapshot()
        positions = client.open_positions()
        status = "WARNING" if account.status == MT5_MOCK_STATUS else "OK"

        print(f"Broker: {config.broker_name}")
        print(f"Platform: {config.platform}")
        print(f"Symbol: {config.symbol}")
        print(f"demo_only: {config.demo_only}")
        print(f"allow_live: {config.allow_live}")
        print(f"execution_enabled: {config.execution_enabled}")
        print(f"Mode: {client.mode}")
        print(f"Account status: {account.status}")
        print(f"Account connected: {account.connected}")
        print(f"Balance: {account.balance}")
        print(f"Equity: {account.equity}")
        print(f"Margin: {account.margin}")
        print(f"Free margin: {account.free_margin}")
        print(f"Symbol status: {symbol.status}")
        print(f"Bid: {symbol.bid}")
        print(f"Ask: {symbol.ask}")
        print(f"Spread: {symbol.spread}")
        print(f"Open demo positions: {len(positions)}")
        if account.status == MT5_MOCK_STATUS:
            print(MT5_MOCK_STATUS)
        print(f"Status: {status}")
        print("Read-only phase only: no demo or real orders can be sent.")
    except Exception as exc:
        print(f"Status: ERROR")
        print(f"Reason: {exc}")


if __name__ == "__main__":
    main()
