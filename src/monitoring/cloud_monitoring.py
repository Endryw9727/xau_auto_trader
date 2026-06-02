"""
Cloud monitoring and observability.

Supports:
- Prometheus metrics export
- CloudWatch integration (AWS)
- Health checks
- Performance metrics
- Alert thresholds

Usage:
    from src.monitoring.cloud_monitoring import MetricsExporter
    exporter = MetricsExporter()
    exporter.record_trade("XAUUSD", "BUY", 2350.0, 0.5)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS_FILE = Path("reports/metrics/system_metrics.jsonl")

@dataclass(frozen=True)
class TradeMetric:
    """Metric for a single trade."""

    timestamp: float
    symbol: str
    side: str
    entry_price: float
    risk_reward: float
    ai_score: float
    macro_score: float
    smc_score: float
    regime: str
    session: str

@dataclass(frozen=True)
class SystemHealth:
    """System health status."""

    timestamp: float
    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    latency_ms: float
    error_count: int
    last_error: str | None


class MetricsExporter:
    """Export metrics for monitoring systems."""

    def __init__(self, output_file: Path = METRICS_FILE):
        self.output_file = output_file
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self._health_status: dict[str, SystemHealth] = {}

    def record_trade(self, symbol: str, side: str, entry: float, risk_reward: float,
                     ai_score: float = 0.0, macro_score: float = 0.0,
                     smc_score: float = 0.0, regime: str = "UNKNOWN",
                     session: str = "UNKNOWN") -> None:
        """Record a trade execution metric."""
        metric = TradeMetric(
            timestamp=time.time(),
            symbol=symbol,
            side=side,
            entry_price=entry,
            risk_reward=risk_reward,
            ai_score=ai_score,
            macro_score=macro_score,
            smc_score=smc_score,
            regime=regime,
            session=session,
        )
        self._write_metric("trade", metric.__dict__)

    def record_health(self, component: str, status: str, latency_ms: float,
                      error_count: int = 0, last_error: str | None = None) -> None:
        """Record a health check metric."""
        health = SystemHealth(
            timestamp=time.time(),
            component=component,
            status=status,
            latency_ms=latency_ms,
            error_count=error_count,
            last_error=last_error,
        )
        self._health_status[component] = health
        self._write_metric("health", health.__dict__)

    def record_custom(self, metric_name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a custom metric."""
        entry = {
            "timestamp": time.time(),
            "metric": metric_name,
            "value": value,
            "labels": labels or {},
        }
        self._write_metric("custom", entry)

    def get_health_summary(self) -> dict[str, Any]:
        """Get current health summary."""
        healthy = sum(1 for h in self._health_status.values() if h.status == "healthy")
        degraded = sum(1 for h in self._health_status.values() if h.status == "degraded")
        unhealthy = sum(1 for h in self._health_status.values() if h.status == "unhealthy")

        return {
            "total_components": len(self._health_status),
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "overall_status": "healthy" if unhealthy == 0 else ("degraded" if unhealthy < 2 else "critical"),
            "components": {name: {"status": h.status, "latency_ms": h.latency_ms}
                           for name, h in self._health_status.items()},
        }

    def _write_metric(self, metric_type: str, data: dict[str, Any]) -> None:
        """Write metric to file."""
        entry = {"type": metric_type, **data}
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_prometheus_format(self) -> str:
        """Export metrics in Prometheus exposition format."""
        lines = []

        # Trade counter
        lines.append("# HELP xau_trades_total Total trades executed")
        lines.append("# TYPE xau_trades_total counter")
        # Would need to count from file

        # Health gauge
        lines.append("# HELP xau_component_health Component health status (1=healthy, 0.5=degraded, 0=unhealthy)")
        lines.append("# TYPE xau_component_health gauge")
        for component, health in self._health_status.items():
            value = 1.0 if health.status == "healthy" else (0.5 if health.status == "degraded" else 0.0)
            lines.append(f'xau_component_health{{component="{component}"}} {value}')

        # Latency gauge
        lines.append("# HELP xau_component_latency_ms Component latency in milliseconds")
        lines.append("# TYPE xau_component_latency_ms gauge")
        for component, health in self._health_status.items():
            lines.append(f'xau_component_latency_ms{{component="{component}"}} {health.latency_ms}')

        return "\n".join(lines)


class CloudWatchExporter:
    """Export metrics to AWS CloudWatch."""

    def __init__(self, namespace: str = "XAUAutoTrader"):
        self.namespace = namespace
        self._client = None

    def _get_client(self):
        """Lazy initialization of CloudWatch client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("cloudwatch")
        return self._client

    def put_metric(self, metric_name: str, value: float, unit: str = "Count",
                   dimensions: list[dict[str, str]] | None = None) -> None:
        """Put a metric to CloudWatch."""
        try:
            client = self._get_client()
            metric_data = {
                "MetricName": metric_name,
                "Value": value,
                "Unit": unit,
            }
            if dimensions:
                metric_data["Dimensions"] = dimensions

            client.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data],
            )
        except Exception as e:
            print(f"CloudWatch export failed: {e}")

    def put_trade_metric(self, symbol: str, side: str, pnl: float) -> None:
        """Record trade P&L to CloudWatch."""
        self.put_metric(
            "TradePnL",
            pnl,
            unit="None",
            dimensions=[
                {"Name": "Symbol", "Value": symbol},
                {"Name": "Side", "Value": side},
            ],
        )
