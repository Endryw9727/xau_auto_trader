# MT5 CSV Bridge

This bridge exists for Mac/Wine setups where MetaTrader 5 is running but the
Python `MetaTrader5` package is not available. It imports candle CSV files
exported manually from MT5 and updates the local research CSVs used by
paper-forward.

It is data-only:

- no broker connection
- no demo orders
- no real orders
- no live execution
- no API keys
- `allow_live: false`
- `execution_enabled: false`
- `demo_only: true`

## Input Folder

Put MT5 exports here:

```text
data/mt5_bridge/input/
```

Expected filenames are configured in:

```text
config/mt5_csv_bridge.yaml
```

Defaults:

```text
xauusd_m1.csv
xauusd_m5.csv
xauusd_m15.csv
xauusd_m30.csv
xauusd_h1.csv
xauusd_h4.csv
```

CSV files are ignored by Git. The repository keeps only `.gitkeep` placeholders
for the input and archive folders.

## Supported MT5 Format

The importer accepts common MT5 export columns:

```text
Date, Time, Open, High, Low, Close, TickVol, Vol, Spread
```

It also accepts angle-bracket MT5 headers such as:

```text
<DATE>, <TIME>, <OPEN>, <HIGH>, <LOW>, <CLOSE>, <TICKVOL>, <VOL>, <SPREAD>
```

The bridge combines `Date + Time` into a single timestamp, sorts candles,
removes duplicate timestamps, validates OHLC relationships, validates the
timeframe, and writes the local project files.

## Outputs

Multi-timeframe files:

```text
data/raw/timeframes/XAUUSD_M1.csv
data/raw/timeframes/XAUUSD_M5.csv
data/raw/timeframes/XAUUSD_M15.csv
data/raw/timeframes/XAUUSD_M30.csv
data/raw/timeframes/XAUUSD_H1.csv
data/raw/timeframes/XAUUSD_H4.csv
```

The M15 import also updates:

```text
data/raw/xauusd.csv
```

That file is the one used by the paper-forward freshness check.

## Commands

Import exported MT5 CSVs:

```bash
.venv/bin/python scripts/import_mt5_csv_bridge.py
```

Check freshness:

```bash
.venv/bin/python scripts/check_data_freshness.py
```

Run preflight:

```bash
.venv/bin/python scripts/paper_preflight_check.py
```

Evaluate one paper-forward step only after freshness is OK:

```bash
.venv/bin/python scripts/run_paper_forward_once.py
```

## Safety Notes

The bridge does not import the Python `MetaTrader5` package and does not contain
execution code. Preflight only checks the bridge configuration; it does not
auto-import CSV files. The current config keeps `auto_import: false`.
