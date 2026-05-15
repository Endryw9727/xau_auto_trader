from pathlib import Path
from datetime import datetime
import shutil

import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "XAUUSD-P"
TARGET = Path("data/raw/xauusd.csv")
REQUEST_SIZES = [100000, 50000, 20000, 10000, 5000, 1000, 500, 100, 50, 5]

def fetch_rates():
    if not mt5.initialize():
        print("MT5 initialize failed:", mt5.last_error())
        raise SystemExit(1)

    selected = mt5.symbol_select(SYMBOL, True)
    print(f"symbol_select({SYMBOL}) = {selected}")

    df = None

    for n in REQUEST_SIZES:
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, n)
        err = mt5.last_error()
        count = None if rates is None else len(rates)
        print(f"REQUEST {n} -> RATES {count}, ERR {err}")

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            break

    mt5.shutdown()

    if df is None or df.empty:
        print("FAIL: no M15 rates returned")
        raise SystemExit(1)

    df["time_iso"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S")

    print("USING rows:", len(df))
    print("FIRST:", df["time_iso"].iloc[0])
    print("LAST :", df["time_iso"].iloc[-1])
    print("LAST CLOSE:", df["close"].iloc[-1])

    return df

def existing_columns():
    if TARGET.exists():
        old = pd.read_csv(TARGET, nrows=5)
        return list(old.columns)
    return ["time", "open", "high", "low", "close", "volume"]

def build_output(df, columns):
    out = pd.DataFrame()

    for col in columns:
        key = col.lower().strip()

        if key in {"time", "datetime", "timestamp", "date"}:
            out[col] = df["time_iso"]
        elif key == "open":
            out[col] = df["open"]
        elif key == "high":
            out[col] = df["high"]
        elif key == "low":
            out[col] = df["low"]
        elif key == "close":
            out[col] = df["close"]
        elif key in {"volume", "tick_volume", "tickvol", "vol"}:
            out[col] = df["tick_volume"]
        elif key == "spread":
            out[col] = df["spread"]
        elif key == "real_volume":
            out[col] = df["real_volume"]
        elif key == "timeframe":
            out[col] = "M15"
        elif key == "timeframe_code":
            out[col] = 15
        elif key == "symbol":
            out[col] = SYMBOL
        else:
            out[col] = 0

    return out

df = fetch_rates()

TARGET.parent.mkdir(parents=True, exist_ok=True)

if TARGET.exists():
    backup = TARGET.with_suffix(TARGET.suffix + f".bak_force_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(TARGET, backup)
    print("Backup created:", backup)

cols = existing_columns()
out = build_output(df, cols)

out.to_csv(TARGET, index=False)

print("OVERWRITTEN:", TARGET)
print("ROWS:", len(out))
print("LAST ROW:")
print(out.tail(1).to_string(index=False))
print("DONE: xauusd.csv now contains fresh M15 data from MT5 XAUUSD-P read-only")
