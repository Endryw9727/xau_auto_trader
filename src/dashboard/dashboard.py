"""
Streamlit dashboard for local backtest reports.

Run with:
    streamlit run src/dashboard/dashboard.py

This dashboard reads:
- reports/backtests/trades.csv
- reports/backtests/metrics.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


TRADES_PATH = Path("reports/backtests/trades.csv")
METRICS_PATH = Path("reports/backtests/metrics.csv")


def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV if it exists."""
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def main() -> None:
    """Render dashboard."""
    st.set_page_config(
        page_title="XAU Auto Trader Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("📊 XAU Auto Trader - Backtest Dashboard")
    st.caption("Dashboard locale per analizzare i report del backtest. Non è live trading.")

    trades = load_csv(TRADES_PATH)
    metrics = load_csv(METRICS_PATH)

    if trades.empty or metrics.empty:
        st.warning("Nessun report trovato. Prima lancia il backtest con:")
        st.code("python -m src.main")
        return

    latest_metrics = metrics.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Trade totali", int(latest_metrics.get("total_trades", 0)))
    col2.metric("Win rate", f"{latest_metrics.get('win_rate', 0):.2f}%")
    col3.metric("Profit factor", f"{latest_metrics.get('profit_factor', 0):.2f}")
    col4.metric("Net profit", f"{latest_metrics.get('net_profit', 0):.2f}")

    col5, col6, col7, col8 = st.columns(4)

    col5.metric("Wins", int(latest_metrics.get("wins", 0)))
    col6.metric("Losses", int(latest_metrics.get("losses", 0)))
    col7.metric("Expectancy", f"{latest_metrics.get('expectancy', 0):.2f}")
    col8.metric("Max drawdown", f"{latest_metrics.get('max_drawdown', 0):.2f}")

    st.divider()

    st.subheader("Equity Curve")

    if "profit_loss" in trades.columns:
        trades = trades.copy()
        trades["equity"] = 1000 + trades["profit_loss"].fillna(0).cumsum()
        st.line_chart(trades["equity"])
    else:
        st.info("Colonna profit_loss non trovata nei trade.")

    st.divider()

    st.subheader("Distribuzione risultati")

    if "result" in trades.columns:
        result_counts = trades["result"].value_counts()
        st.bar_chart(result_counts)

    st.divider()

    st.subheader("Tabella Trade")

    st.dataframe(trades, use_container_width=True)

    st.divider()

    st.subheader("Metriche complete")

    st.dataframe(metrics, use_container_width=True)

    st.warning(
        "Nota: se stai usando dati finti, questi risultati servono solo a testare il software. "
        "Non dimostrano che la strategia sia profittevole."
    )


if __name__ == "__main__":
    main()
