"""Export broker-time OHLCV CSVs from MT5 for multi-instrument edge research.

Read-only: for each configured instrument it reads closed candles from MT5 at one
timeframe and writes data/raw/<symbol>.csv in the project format (broker server
time). It never sends orders. If MT5 is unavailable or a symbol returns nothing,
it logs a WARNING and leaves the previous CSV untouched.

This unblocks the broker-time edge search: after exporting, re-run
run_session_edge_lab.py / run_ny_conditional_edge.py / run_edge_significance_audit.py
on session-aligned data. Run it on the VPS where MT5 is installed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.mt5_readonly_data_updater import import_mt5_module


DEFAULT_DATA_DIR = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
SUMMARY_FILENAME = "mt5_instrument_export_summary.csv"
LATEST_FILENAME = "mt5_instrument_export_latest.txt"

# Project symbol -> default MT5 broker symbol. Adjust to your broker's names
# (e.g. "EURUSD.r", "US100") via --map on the command line.
DEFAULT_BROKER_SYMBOLS: dict[str, str] = {
    "XAUUSD": "XAUUSD-P",
    "EURUSD": "EURUSD",
    "AUDUSD": "AUDUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "NAS100": "NAS100",
}

_TIMEFRAME_ATTR = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

SUMMARY_COLUMNS = ("symbol", "broker_symbol", "timeframe", "status", "rows", "output_file", "reason")


@dataclass(frozen=True)
class InstrumentExportResult:
    status: str
    reason: str
    summary_path: Path
    latest_path: Path


def rates_to_project_frame(rates: Any) -> pd.DataFrame:
    """Convert MT5 rates (array/list of dicts) into a Date,O,H,L,C,Volume frame."""
    raw = pd.DataFrame(rates)
    if raw.empty:
        raise ValueError("no rates returned")
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(raw.columns):
        raise ValueError("rates missing required OHLC columns")
    volume_col = "tick_volume" if "tick_volume" in raw.columns else "real_volume" if "real_volume" in raw.columns else None
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(raw["time"], unit="s", errors="coerce"),
            "Open": pd.to_numeric(raw["open"], errors="coerce"),
            "High": pd.to_numeric(raw["high"], errors="coerce"),
            "Low": pd.to_numeric(raw["low"], errors="coerce"),
            "Close": pd.to_numeric(raw["close"], errors="coerce"),
            "Volume": pd.to_numeric(raw[volume_col], errors="coerce") if volume_col else 1.0,
        }
    )
    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"]).sort_values("Date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("no valid OHLC rows after parsing")
    return frame


def read_symbol_rates(mt5: Any, broker_symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
    """Read recent closed candles for one broker symbol (read-only)."""
    copy_rates = getattr(mt5, "copy_rates_from_pos", None)
    if not callable(copy_rates):
        raise RuntimeError("MT5 copy_rates_from_pos is unavailable")
    tf = getattr(mt5, _TIMEFRAME_ATTR.get(timeframe.upper(), "TIMEFRAME_M15"), 15)
    if callable(getattr(mt5, "symbol_select", None)):
        mt5.symbol_select(broker_symbol, True)
    raw_rates = copy_rates(broker_symbol, tf, 1, bars)  # start at 1 = skip the open candle
    if raw_rates is None or len(raw_rates) == 0:
        raise RuntimeError(f"no candles returned for {broker_symbol}")
    return rates_to_project_frame(raw_rates)


def export_instruments(
    symbols: list[str],
    *,
    broker_map: dict[str, str] | None = None,
    timeframe: str = "M15",
    bars: int = 50000,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    mt5_module: Any | None = None,
) -> InstrumentExportResult:
    """Export each requested instrument to data/raw/<symbol>.csv from MT5."""
    broker_map = {**DEFAULT_BROKER_SYMBOLS, **(broker_map or {})}
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = export_paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    mt5 = mt5_module or import_mt5_module()
    rows = []
    if mt5 is None:
        for symbol in symbols:
            rows.append(_row(symbol, broker_map.get(symbol, symbol), timeframe, "MT5_NOT_AVAILABLE", 0, "", "MetaTrader5 not installed"))
        return _write_summary(paths, rows, "MT5_NOT_AVAILABLE", "MetaTrader5 package not available")

    initialized = False
    try:
        initialized = bool(mt5.initialize()) if callable(getattr(mt5, "initialize", None)) else False
        if not initialized:
            for symbol in symbols:
                rows.append(_row(symbol, broker_map.get(symbol, symbol), timeframe, "MT5_NOT_INITIALIZED", 0, "", _last_error(mt5)))
            return _write_summary(paths, rows, "ERROR", "MT5 not initialized")

        for symbol in symbols:
            broker_symbol = broker_map.get(symbol, symbol)
            target = data_dir / f"{symbol.lower()}.csv"
            try:
                frame = read_symbol_rates(mt5, broker_symbol, timeframe, bars)
            except Exception as exc:  # noqa: BLE001 - keep previous file, never crash
                rows.append(_row(symbol, broker_symbol, timeframe, "WARNING", 0, str(target) if target.exists() else "", str(exc)))
                continue
            frame.to_csv(target, index=False)
            rows.append(_row(symbol, broker_symbol, timeframe, "OK", len(frame), str(target), ""))
        return _write_summary(paths, rows, "OK", "instrument export completed")
    finally:
        shutdown = getattr(mt5, "shutdown", None)
        if initialized and callable(shutdown):
            shutdown()


def _row(symbol, broker_symbol, timeframe, status, count, output_file, reason) -> dict:
    return {
        "symbol": symbol, "broker_symbol": broker_symbol, "timeframe": timeframe,
        "status": status, "rows": int(count), "output_file": output_file, "reason": reason,
    }


def _write_summary(paths: dict[str, Path], rows: list[dict], status: str, reason: str) -> InstrumentExportResult:
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(paths["summary"], index=False)
    lines = ["MT5 Instrument Export", "=" * 72, f"Status: {status}", f"Reason: {reason}", ""]
    for row in rows:
        lines.append(f"{row['symbol']:<8} | {row['broker_symbol']:<10} | {row['timeframe']} | {row['status']:<18} | rows={row['rows']} | {row['reason']}")
    lines += ["", "No orders were sent. Read-only export.", ""]
    paths["latest"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return InstrumentExportResult(status, reason, paths["summary"], paths["latest"])


def export_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {"summary": directory / SUMMARY_FILENAME, "latest": directory / LATEST_FILENAME}


def _last_error(mt5: Any) -> str:
    last_error = getattr(mt5, "last_error", None)
    return str(last_error()) if callable(last_error) else "unknown"


def _parse_map(pairs: list[str] | None) -> dict[str, str]:
    mapping = {}
    for pair in pairs or []:
        if "=" in pair:
            key, value = pair.split("=", 1)
            mapping[key.strip().upper()] = value.strip()
    return mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=sorted(DEFAULT_BROKER_SYMBOLS), help="Project symbols to export.")
    parser.add_argument("--map", nargs="*", default=None, help="Override broker names, e.g. EURUSD=EURUSD.r NAS100=US100.")
    parser.add_argument("--timeframe", default="M15", help="MT5 timeframe (M1/M5/M15/M30/H1/H4/D1).")
    parser.add_argument("--bars", type=int, default=50000, help="Number of closed candles to read per symbol.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Output directory for CSVs.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = export_instruments(
        list(args.symbols),
        broker_map=_parse_map(args.map),
        timeframe=args.timeframe,
        bars=args.bars,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - MT5 Instrument Export (read-only)")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. Read-only export.")


if __name__ == "__main__":
    main()
