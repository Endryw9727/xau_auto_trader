"""
Streamlit dashboard for local backtest and SQLite trade journal.

Run with:
    streamlit run src/dashboard/dashboard.py

Reads:
- reports/backtests/trades.csv
- reports/backtests/metrics.csv
- data/database/trading.db
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st


TRADES_PATH = Path("reports/backtests/trades.csv")
METRICS_PATH = Path("reports/backtests/metrics.csv")
DATABASE_PATH = Path("data/database/trading.db")


def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV if it exists."""
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def load_sqlite_table(db_path: Path, table_name: str) -> pd.DataFrame:
    """Load a SQLite table into a DataFrame."""
    if not db_path.exists():
        return pd.DataFrame()

    with sqlite3.connect(db_path) as connection:
        query = f"SELECT * FROM {table_name}"
        return pd.read_sql_query(query, connection)


def render_backtest_report_tab() -> None:
    """Render CSV backtest report tab."""
    trades = load_csv(TRADES_PATH)
    metrics = load_csv(METRICS_PATH)

    if trades.empty or metrics.empty:
        st.warning("Nessun report CSV trovato. Prima lancia il backtest con:")
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

    st.subheader("Equity Curve CSV")

    if "profit_loss" in trades.columns:
        trades = trades.copy()
        trades["equity"] = 1000 + trades["profit_loss"].fillna(0).cumsum()
        st.line_chart(trades["equity"])
    else:
        st.info("Colonna profit_loss non trovata nei trade.")

    st.divider()

    st.subheader("Distribuzione risultati CSV")

    if "result" in trades.columns:
        result_counts = trades["result"].value_counts()
        st.bar_chart(result_counts)

    st.divider()

    st.subheader("Tabella Trade CSV")
    st.dataframe(trades, width="stretch")

    st.divider()

    st.subheader("Metriche complete CSV")
    st.dataframe(metrics, width="stretch")


def render_database_tab() -> None:
    """Render SQLite database tab."""
    trades_db = load_sqlite_table(DATABASE_PATH, "trades")

    if trades_db.empty:
        st.warning("Nessun trade trovato nel database SQLite.")
        st.code("python -m src.main")
        st.code("python scripts/run_paper_trading.py")
        return

    st.subheader("Trade salvati in SQLite")

    col1, col2, col3, col4 = st.columns(4)

    total_trades = len(trades_db)
    total_pnl = trades_db["profit_loss"].fillna(0).sum() if "profit_loss" in trades_db.columns else 0
    wins = int((trades_db["profit_loss"].fillna(0) > 0).sum()) if "profit_loss" in trades_db.columns else 0
    losses = int((trades_db["profit_loss"].fillna(0) < 0).sum()) if "profit_loss" in trades_db.columns else 0
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    col1.metric("Trade DB", total_trades)
    col2.metric("P&L DB", f"{total_pnl:.2f}")
    col3.metric("Win rate DB", f"{win_rate:.2f}%")
    col4.metric("Losses DB", losses)

    st.divider()

    if "mode" in trades_db.columns:
        st.subheader("Trade per modalità")
        mode_counts = trades_db["mode"].value_counts()
        st.bar_chart(mode_counts)

    st.divider()

    if "profit_loss" in trades_db.columns:
        st.subheader("Equity Curve da SQLite")
        trades_db_sorted = trades_db.copy()

        if "timestamp_close" in trades_db_sorted.columns:
            trades_db_sorted["timestamp_close"] = pd.to_datetime(
                trades_db_sorted["timestamp_close"],
                errors="coerce",
            )
            trades_db_sorted = trades_db_sorted.sort_values("timestamp_close")

        trades_db_sorted["equity"] = 1000 + trades_db_sorted["profit_loss"].fillna(0).cumsum()
        st.line_chart(trades_db_sorted["equity"])

    st.divider()

    st.subheader("Filtri")

    filtered = trades_db.copy()

    if "mode" in filtered.columns:
        modes = sorted(filtered["mode"].dropna().unique().tolist())
        selected_modes = st.multiselect("Modalità", modes, default=modes)

        if selected_modes:
            filtered = filtered[filtered["mode"].isin(selected_modes)]

    if "result" in filtered.columns:
        results = sorted(filtered["result"].dropna().unique().tolist())
        selected_results = st.multiselect("Risultato", results, default=results)

        if selected_results:
            filtered = filtered[filtered["result"].isin(selected_results)]

    st.divider()

    st.subheader("Tabella trade SQLite")
    st.dataframe(filtered, width="stretch")

    st.divider()

    st.subheader("Download trade SQLite")

    csv_data = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Scarica trade filtrati CSV",
        data=csv_data,
        file_name="sqlite_trades_filtered.csv",
        mime="text/csv",
    )


def render_safety_tab() -> None:
    """Render project safety tab."""
    st.subheader("Sicurezza progetto")

    st.success("Live broker protetto: nessun ordine reale viene inviato.")
    st.info("Il live trading resta bloccato finché LIVE_MODE=false.")

    st.markdown(
        """
        Checklist minima prima di pensare al live:

        - Backtest su dati reali, non finti
        - Paper trading per settimane/mesi
        - Risk manager verificato
        - Stop loss obbligatorio
        - Max daily loss funzionante
        - Broker API testata in ambiente demo
        - Nessuna API key caricata su GitHub
        """
    )

    st.warning(
        "Anche con backtest positivi, nessun sistema garantisce profitti. "
        "Prima si valida la strategia, poi si valuta il rischio reale."
    )


def main() -> None:
    """Render dashboard."""
    st.set_page_config(
        page_title="XAU Auto Trader Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("📊 XAU Auto Trader Dashboard")
    st.caption("Dashboard locale per backtest, paper trading e database SQLite.")

    tab_backtest, tab_database, tab_safety = st.tabs(
        ["Backtest CSV", "Database SQLite", "Sicurezza Live"]
    )

    with tab_backtest:
        render_backtest_report_tab()

    with tab_database:
        render_database_tab()

    with tab_safety:
        render_safety_tab()


if __name__ == "__main__":
    main()
