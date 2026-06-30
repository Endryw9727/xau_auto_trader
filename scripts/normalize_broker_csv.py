"""Normalize broker M15 CSV exports into the project format.

Many broker/history exports are headerless and named like ``EURUSD_M15.csv`` or
``USATECHIDXUSD_M15.csv``. This converts them into ``data/raw/<symbol>.csv`` with
the required ``Date,Open,High,Low,Close,Volume`` header so the edge lab / API can
read them. It is read/transform only: no network, no execution, no orders.

    python scripts/normalize_broker_csv.py --input C:\\Users\\Administrator\\Downloads --output data/raw

Handles: headerless or headered files; a combined ``YYYY-MM-DD HH:MM`` datetime
column, OR separate Date and Time columns; extra trailing columns (tick volume,
spread) are ignored.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]

# Broker symbol stems that should map to the project's instrument names.
SYMBOL_MAP = {
    "USATECHIDXUSD": "nas100",
    "USTEC": "nas100",
    "NAS100": "nas100",
    "USA500IDXUSD": "sp500",
    "US500": "sp500",
    "SPX500": "sp500",
}

_TF_SUFFIX = re.compile(r"[_-](m1|m5|m15|m30|h1|h4|d1)$", re.IGNORECASE)


@dataclass(frozen=True)
class NormalizeResult:
    symbol: str
    source: str
    output: str
    rows: int
    status: str
    reason: str = ""


def derive_symbol(filename: str) -> str:
    """Map a broker filename to a project symbol (lowercase)."""
    stem = Path(filename).stem
    stem = _TF_SUFFIX.sub("", stem)
    return SYMBOL_MAP.get(stem.upper(), stem.lower())


def normalize_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn a raw broker frame into a Date,Open,High,Low,Close,Volume frame."""
    if raw is None or raw.empty:
        raise ValueError("empty input")
    ncols = raw.shape[1]
    if ncols < 6:
        raise ValueError(f"expected at least 6 columns, got {ncols}")

    columns = list(raw.columns)
    # Detect a separate Time column: second column is HH:MM-like and not numeric.
    second = str(raw.iloc[0, 1])
    has_separate_time = bool(re.match(r"^\d{1,2}:\d{2}", second.strip())) and ":" in second

    if has_separate_time:
        date = raw[columns[0]].astype(str).str.strip() + " " + raw[columns[1]].astype(str).str.strip()
        ohlcv = raw.iloc[:, 2:7]
    else:
        date = raw[columns[0]].astype(str).str.strip()
        ohlcv = raw.iloc[:, 1:5]
        volume = raw.iloc[:, 5]
        ohlcv = pd.concat([ohlcv, volume], axis=1)

    frame = pd.DataFrame()
    frame["Date"] = pd.to_datetime(date, errors="coerce")
    values = ohlcv.to_numpy()
    for idx, name in enumerate(["Open", "High", "Low", "Close", "Volume"]):
        frame[name] = pd.to_numeric(pd.Series(values[:, idx]), errors="coerce")
    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"]).reset_index(drop=True)
    if frame.empty:
        raise ValueError("no valid rows after parsing")
    return frame[OUTPUT_COLUMNS]


def _read_raw(path: Path) -> pd.DataFrame:
    """Read a CSV whether or not it has a header row."""
    headed = pd.read_csv(path)
    # If the first cell of the first data row is not a parseable date, the file
    # likely has no header and pandas consumed the first data row as the header.
    first_label = str(headed.columns[0])
    if pd.isna(pd.to_datetime(first_label, errors="coerce")):
        return headed  # genuine header (e.g. "Date" / "Gmt time")
    return pd.read_csv(path, header=None)


def normalize_file(src_path: Path, dest_dir: Path, *, symbol: str | None = None) -> NormalizeResult:
    """Normalize one broker CSV into dest_dir/<symbol>.csv."""
    symbol = symbol or derive_symbol(src_path.name)
    dest = Path(dest_dir) / f"{symbol}.csv"
    try:
        frame = normalize_frame(_read_raw(src_path))
    except Exception as exc:  # noqa: BLE001
        return NormalizeResult(symbol, str(src_path), str(dest), 0, "ERROR", str(exc))
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(dest, index=False)
    return NormalizeResult(symbol, str(src_path), str(dest), int(len(frame)), "OK")


def normalize_directory(input_dir: str | Path, output_dir: str | Path) -> list[NormalizeResult]:
    """Normalize every *.csv in input_dir into output_dir."""
    in_dir = Path(input_dir)
    results = []
    for csv_path in sorted(in_dir.glob("*.csv")):
        results.append(normalize_file(csv_path, output_dir))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Folder with the raw broker CSV files.")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Destination folder (default data/raw).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = normalize_directory(args.input, args.output)
    print("=" * 72)
    print("XAU Auto Trader - Broker CSV normalizer")
    print("=" * 72)
    for r in results:
        print(f"{r.status:<6} {r.symbol:<10} rows={r.rows:<7} -> {r.output}  {r.reason}")
    ok = sum(1 for r in results if r.status == "OK")
    print(f"\n{ok}/{len(results)} files normalized. No orders were sent.")


if __name__ == "__main__":
    main()
