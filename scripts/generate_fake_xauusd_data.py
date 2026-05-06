"""
Generate fake OHLCV XAU/USD data for local backtest testing.

This data is artificial and must not be used to judge real profitability.
It only verifies that the full pipeline works:
CSV -> loader -> indicators -> signals -> risk manager -> backtester -> reports
"""

from __future__ import annotations

from pathlib import Path
import random

import pandas as pd


OUTPUT_PATH = Path("data/raw/xauusd.csv")


def generate_fake_xauusd_data(rows: int = 2000) -> pd.DataFrame:
    """Generate artificial 15-minute OHLCV data."""
    dates = pd.date_range("2025-01-01 00:00:00", periods=rows, freq="15min")

    price = 2350.0
    rows_data = []

    for i, date in enumerate(dates):
        # Create alternating market regimes
        if i < rows * 0.25:
            drift = 0.35
        elif i < rows * 0.50:
            drift = -0.25
        elif i < rows * 0.75:
            drift = 0.15
        else:
            drift = -0.10

        noise = random.uniform(-2.5, 2.5)
        open_price = price
        close_price = price + drift + noise

        high_price = max(open_price, close_price) + random.uniform(0.3, 2.0)
        low_price = min(open_price, close_price) - random.uniform(0.3, 2.0)

        volume = random.randint(500, 5000)

        rows_data.append(
            {
                "Date": date,
                "Open": round(open_price, 2),
                "High": round(high_price, 2),
                "Low": round(low_price, 2),
                "Close": round(close_price, 2),
                "Volume": volume,
            }
        )

        price = close_price

    return pd.DataFrame(rows_data)


def main() -> None:
    """Generate and save the fake CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    df = generate_fake_xauusd_data()
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Fake XAU/USD data generated: {OUTPUT_PATH}")
    print(f"Rows: {len(df)}")
    print("")
    print("Important: this is artificial data, not real market data.")


if __name__ == "__main__":
    main()
