"""Fetch intraday OHLCV CSVs from the public Yahoo Finance chart API.

Research helper to populate data/raw/*.csv for the multi-instrument session edge
lab when MT5 export is not available (e.g. on a laptop). It reads only public
market data over HTTPS, writes local CSVs (gitignored), and never trades.

Caveat: Yahoo timestamps are UTC. The session edge lab's session windows are
broker-server-time, so session boundaries here are approximate (UTC-based). For
production use prefer broker-aligned data exported from MT5 on the VPS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# Project symbol -> Yahoo Finance symbol.
YAHOO_SYMBOLS: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "AUDUSD": "AUDUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "NAS100": "^NDX",
    "XAUUSD": "GC=F",
}

DEFAULT_DATA_DIR = Path("data/raw")
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def fetch_yahoo_chart_json(yahoo_symbol: str, *, interval: str = "1h", range_: str = "730d", timeout: int = 40) -> dict:
    """Download the raw Yahoo chart JSON for one symbol."""
    url = YAHOO_CHART_URL.format(symbol=urllib.parse.quote(yahoo_symbol))
    url = f"{url}?interval={interval}&range={range_}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    """Convert a Yahoo chart JSON payload into a Date,O,H,L,C,Volume frame."""
    chart = (payload or {}).get("chart", {})
    error = chart.get("error")
    if error:
        raise ValueError(f"Yahoo chart error: {error}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart returned no result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    if not timestamps:
        raise ValueError("Yahoo chart returned no timestamps")

    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(pd.Series(timestamps, dtype="int64"), unit="s", utc=True).dt.tz_localize(None),
            "Open": quote.get("open"),
            "High": quote.get("high"),
            "Low": quote.get("low"),
            "Close": quote.get("close"),
            "Volume": quote.get("volume"),
        }
    )
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
    if frame.empty:
        raise ValueError("Yahoo chart produced no valid OHLC rows")
    frame["Volume"] = frame["Volume"].fillna(0)
    return frame


def fetch_ohlcv(symbol: str, *, interval: str = "1h", range_: str = "730d") -> pd.DataFrame:
    """Fetch and parse OHLCV for a project symbol."""
    yahoo_symbol = YAHOO_SYMBOLS.get(symbol.upper())
    if yahoo_symbol is None:
        raise KeyError(f"unknown symbol: {symbol} (known: {sorted(YAHOO_SYMBOLS)})")
    return parse_yahoo_chart(fetch_yahoo_chart_json(yahoo_symbol, interval=interval, range_=range_))


def save_ohlcv_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write an OHLCV frame to CSV in the project format."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=sorted(YAHOO_SYMBOLS), help="Project symbols to fetch.")
    parser.add_argument("--interval", default="1h", help="Yahoo interval (e.g. 1h, 30m, 1d).")
    parser.add_argument("--range", dest="range_", default="730d", help="Yahoo range (e.g. 730d, 60d).")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Output directory for CSVs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 72)
    print("XAU Auto Trader - Yahoo OHLCV fetch (research data only)")
    print("=" * 72)
    for symbol in args.symbols:
        target = Path(args.data_dir) / f"{symbol.lower()}.csv"
        try:
            frame = fetch_ohlcv(symbol, interval=args.interval, range_=args.range_)
            save_ohlcv_csv(frame, target)
            print(f"{symbol:<8} OK   rows={len(frame):<6} {frame['Date'].iloc[0]} .. {frame['Date'].iloc[-1]} -> {target}")
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol:<8} FAIL {exc}")
    print("No orders were sent. Research data only.")


if __name__ == "__main__":
    main()
