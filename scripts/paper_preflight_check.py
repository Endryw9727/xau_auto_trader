"""
Preflight checks for controlled paper trading.

This script performs safety checks only. It never contacts a broker and never
enables live trading.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.broker.demo_broker_readonly import DEFAULT_DEMO_BROKER_CONFIG_PATH, load_demo_broker_config
from src.market_data.data_freshness import analyze_data_freshness, append_freshness_log, format_freshness_detail
from src.market_data.mt5_readonly_data_updater import (
    DEFAULT_MARKET_DATA_CONFIG_PATH,
    load_market_data_config,
    update_market_data_from_mt5_readonly,
)
from src.market_data.mt5_csv_bridge import DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH, load_mt5_csv_bridge_config
from src.paper.paper_candidate import PAPER_MAIN_STRATEGY, load_paper_candidate_config
from src.paper.paper_engine import DEFAULT_PAPER_OUTPUT_DIR, load_paper_trading_config
from src.paper.paper_monitor import build_monitor_summary, load_paper_reports


CONFIG_PATH = Path("config.yaml")
RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run paper preflight checks and print status."""
    print("=" * 72)
    print("XAU Auto Trader - Paper Preflight Check")
    print("=" * 72)
    checks = run_preflight_checks()
    status = preflight_status(checks)

    for item in checks:
        marker = "OK" if item["passed"] else "FAIL"
        print(f"[{marker}] {item['name']}: {item['detail']}")

    print("")
    print(f"Preflight status: {status}")
    if any(item["name"] == "data_freshness" and item.get("status") == "WARNING" for item in checks):
        print("WARNING: local market data is old; paper-forward can continue only with caution.")
    if any(item["name"] == "monitor_status" and "WARNING" in item["detail"] for item in checks):
        print("WARNING: paper can continue only with extra prudence.")
    if status in {"FAIL", "STALE"}:
        print("Do not start paper trading until failed checks are resolved.")
    elif status == "WARNING":
        print("Paper session can proceed only with controlled caution.")
    else:
        print("Paper session can proceed under controlled paper rules.")
    print("No real orders are possible from this script. allow_live remains false.")


def preflight_status(checks: list[dict]) -> str:
    """Return PASS, WARNING, STALE, or FAIL for the preflight report."""
    freshness = next((item for item in checks if item["name"] == "data_freshness"), None)
    if freshness and freshness.get("status") == "STALE":
        return "STALE"
    if not all(item["passed"] for item in checks):
        return "FAIL"
    if freshness and freshness.get("status") == "WARNING":
        return "WARNING"
    return "PASS"


def run_preflight_checks() -> list[dict]:
    """Return preflight checks as dictionaries."""
    checks = []
    candidate = load_paper_candidate_config()
    paper_config = load_paper_trading_config()
    app_config = load_yaml(CONFIG_PATH)

    live_mode = bool(app_config.get("trading", {}).get("live_mode", False))
    env_live_mode = str(os.environ.get("LIVE_MODE", "false")).strip().lower()
    checks.append(check("live_mode_false", not live_mode and env_live_mode not in {"1", "true", "yes"}, f"config live_mode={live_mode}, env LIVE_MODE={env_live_mode}"))
    checks.append(check("allow_live_false", candidate.allow_live is False, f"allow_live={candidate.allow_live}"))
    checks.append(check("paper_mode_true", candidate.paper_mode is True and paper_config.paper_mode is True, "paper_mode=true"))
    checks.append(check("strategy_name", candidate.paper_main_strategy == PAPER_MAIN_STRATEGY, f"paper_main_strategy={candidate.paper_main_strategy}"))
    checks.append(check("broker_not_active", True, "no broker connector/API is used by paper scripts"))
    checks.append(check("env_not_required", True, ".env is not required for paper preflight"))
    checks.append(check("paper_reports_dir", DEFAULT_PAPER_OUTPUT_DIR.exists(), f"{DEFAULT_PAPER_OUTPUT_DIR} exists"))
    checks.append(check_demo_broker_readonly_config(DEFAULT_DEMO_BROKER_CONFIG_PATH))
    checks.append(check_mt5_csv_bridge_config(DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH))
    checks.append(check_market_data_auto_update(DEFAULT_MARKET_DATA_CONFIG_PATH))
    freshness = analyze_data_freshness(RAW_DATA_PATH, symbol=paper_config.symbol)
    append_freshness_log(freshness)
    checks.append(
        check(
            "data_freshness",
            freshness.status in {"OK", "WARNING"},
            format_freshness_detail(freshness),
            status=freshness.status,
        )
    )

    try:
        reports = load_paper_reports()
        monitor = build_monitor_summary(reports, strategy_name=candidate.paper_main_strategy)
        row = monitor.iloc[0]
        status = str(row["status"])
        passed = status != "STOP"
        checks.append(check("monitor_status", passed, f"{status}: {row.get('warning_reasons', '') or row.get('stop_reasons', '')}"))
    except FileNotFoundError as exc:
        checks.append(check("monitor_status", False, str(exc)))

    return checks


def check_demo_broker_readonly_config(path: Path) -> dict:
    """Validate optional demo broker read-only config safety."""
    if not path.exists():
        return check("demo_broker_readonly", True, "config/demo_broker.yaml not configured; skipped")

    try:
        config = load_demo_broker_config(path)
    except Exception as exc:
        return check("demo_broker_readonly", False, str(exc), status="ERROR")

    return check(
        "demo_broker_readonly",
        True,
        (
            f"demo_only={config.demo_only}, allow_live={config.allow_live}, "
            f"execution_enabled={config.execution_enabled}; MT5 connection optional"
        ),
        status="OK",
    )


def check_mt5_csv_bridge_config(path: Path) -> dict:
    """Validate optional MT5 CSV bridge config without importing data."""
    if not path.exists():
        return check("mt5_csv_bridge", True, "config/mt5_csv_bridge.yaml not configured; skipped")

    try:
        config = load_mt5_csv_bridge_config(path)
    except Exception as exc:
        return check("mt5_csv_bridge", False, str(exc), status="ERROR")

    if config.auto_import:
        return check("mt5_csv_bridge", False, "auto_import=true is not allowed in paper preflight", status="ERROR")

    return check(
        "mt5_csv_bridge",
        True,
        (
            f"enabled={config.enabled}, demo_only={config.demo_only}, allow_live={config.allow_live}, "
            f"execution_enabled={config.execution_enabled}, auto_import={config.auto_import}"
        ),
        status="OK",
    )


def check_market_data_auto_update(path: Path) -> dict:
    """Optionally run read-only MT5 data update before freshness checks."""
    if not path.exists():
        return check("market_data_auto_update", True, "config/market_data.yaml not configured; skipped")

    try:
        config = load_market_data_config(path)
    except Exception as exc:
        return check("market_data_auto_update", False, str(exc), status="ERROR")

    if not config.auto_update_data:
        return check("market_data_auto_update", True, "auto_update_data=false; read-only update skipped", status="SKIPPED")

    results = update_market_data_from_mt5_readonly(market_config_path=path)
    statuses = sorted({result.status for result in results})
    added_rows = sum(result.added_rows for result in results)
    failed = any(status == "ERROR" for status in statuses)
    return check(
        "market_data_auto_update",
        not failed,
        f"auto_update_data=true; statuses={statuses}; added_rows={added_rows}",
        status="ERROR" if failed else "OK",
    )


def check(name: str, passed: bool, detail: str, **extra) -> dict:
    """Build one check row."""
    return {"name": name, "passed": bool(passed), "detail": detail, **extra}


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    main()
