"""Read-only broker research interfaces.

This package is intentionally separated from live execution code. Modules here
may inspect demo-broker-like state, but they must not send orders.
"""

from .demo_broker_readonly import (
    DemoBrokerReadOnlyClient,
    DemoBrokerSnapshot,
    DemoPositionSnapshot,
    DemoSymbolSnapshot,
)

__all__ = [
    "DemoBrokerReadOnlyClient",
    "DemoBrokerSnapshot",
    "DemoPositionSnapshot",
    "DemoSymbolSnapshot",
]
