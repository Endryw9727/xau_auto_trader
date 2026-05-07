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
import sys

import pandas as pd
import streamlit as st



TRADES_PATH = Path("reports/backtests/trades.csv")
METRICS_PATH = Path("reports/backtests/metrics.csv")
DATABASE_PATH = Path("data/database/trading.db")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.session_analysis import add_session_column, calculate_session_summary


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



def calculate_profit_factor(df: pd.DataFrame) -> float:
    """Calculate profit factor from profit_loss column."""
    if df.empty or "profit_loss" not in df.columns:
        return 0.0

    pnl = df["profit_loss"].fillna(0)
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return float(gross_profit / gross_loss)


def render_strategy_analysis_tab() -> None:
    """Render strategy analysis from SQLite trades."""
    trades_db = load_sqlite_table(DATABASE_PATH, "trades")

    if trades_db.empty:
        st.warning("Nessun trade trovato nel database SQLite.")
        st.code("python -m src.main")
        st.code("python scripts/run_paper_trading.py")
        return

    st.subheader("Analisi Strategia da SQLite")

    if "profit_loss" not in trades_db.columns:
        st.error("Colonna profit_loss non trovata nel database.")
        return

    trades_db = trades_db.copy()
    trades_db["profit_loss"] = pd.to_numeric(trades_db["profit_loss"], errors="coerce").fillna(0)

    if "mode" not in trades_db.columns:
        trades_db["mode"] = "unknown"

    summary_rows = []

    for mode, group in trades_db.groupby("mode"):
        total_trades = len(group)
        wins = int((group["profit_loss"] > 0).sum())
        losses = int((group["profit_loss"] < 0).sum())
        breakeven = int((group["profit_loss"] == 0).sum())
        net_profit = float(group["profit_loss"].sum())
        win_rate = wins / total_trades * 100 if total_trades else 0.0
        profit_factor = calculate_profit_factor(group)
        average_trade = float(group["profit_loss"].mean()) if total_trades else 0.0
        best_trade = float(group["profit_loss"].max()) if total_trades else 0.0
        worst_trade = float(group["profit_loss"].min()) if total_trades else 0.0

        summary_rows.append(
            {
                "mode": mode,
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "net_profit": net_profit,
                "average_trade": average_trade,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
            }
        )

    summary = pd.DataFrame(summary_rows)

    st.subheader("Riepilogo per modalità")
    st.dataframe(summary, width="stretch")

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    total_trades_all = len(trades_db)
    net_profit_all = float(trades_db["profit_loss"].sum())
    wins_all = int((trades_db["profit_loss"] > 0).sum())
    win_rate_all = wins_all / total_trades_all * 100 if total_trades_all else 0.0
    profit_factor_all = calculate_profit_factor(trades_db)

    col1.metric("Trade totali", total_trades_all)
    col2.metric("P&L totale", f"{net_profit_all:.2f}")
    col3.metric("Win rate totale", f"{win_rate_all:.2f}%")
    col4.metric("Profit factor totale", f"{profit_factor_all:.2f}")

    st.divider()

    st.subheader("Equity Curve per modalità")

    if "timestamp_close" in trades_db.columns:
        trades_db["timestamp_close"] = pd.to_datetime(trades_db["timestamp_close"], errors="coerce")
        trades_db = trades_db.sort_values("timestamp_close")

    modes = sorted(trades_db["mode"].dropna().unique().tolist())

    selected_mode = st.selectbox("Scegli modalità", modes)

    mode_trades = trades_db[trades_db["mode"] == selected_mode].copy()

    if not mode_trades.empty:
        mode_trades["equity"] = 1000 + mode_trades["profit_loss"].cumsum()
        st.line_chart(mode_trades["equity"])

    st.divider()

    st.subheader("Migliori e peggiori trade")

    col_best, col_worst = st.columns(2)

    best_trades = trades_db.sort_values("profit_loss", ascending=False).head(10)
    worst_trades = trades_db.sort_values("profit_loss", ascending=True).head(10)

    with col_best:
        st.markdown("**Top 10 trade migliori**")
        st.dataframe(best_trades, width="stretch")

    with col_worst:
        st.markdown("**Top 10 trade peggiori**")
        st.dataframe(worst_trades, width="stretch")

    st.warning(
        "Questa analisi è utile solo se i dati sono reali o paper trading serio. "
        "Con dati finti serve soltanto a verificare che il software funzioni."
    )



def render_signals_tab() -> None:
    """Render generated signals saved in SQLite."""
    signals_db = load_sqlite_table(DATABASE_PATH, "signals")

    if signals_db.empty:
        st.warning("Nessun segnale trovato nel database SQLite.")
        st.code("python -m src.main")
        st.code("python scripts/run_paper_trading.py")
        return

    st.subheader("Segnali salvati in SQLite")

    signals_db = signals_db.copy()

    if "timestamp" in signals_db.columns:
        signals_db["timestamp"] = pd.to_datetime(signals_db["timestamp"], errors="coerce")
        signals_db = signals_db.sort_values("timestamp")

    col1, col2, col3, col4 = st.columns(4)

    total_signals = len(signals_db)
    approved = int(signals_db["approved_by_risk_manager"].fillna(False).sum()) if "approved_by_risk_manager" in signals_db.columns else 0
    blocked = total_signals - approved

    avg_confidence = (
        signals_db["confidence"].fillna(0).mean()
        if "confidence" in signals_db.columns
        else 0
    )

    avg_rr = (
        signals_db["risk_reward"].dropna().mean()
        if "risk_reward" in signals_db.columns and not signals_db["risk_reward"].dropna().empty
        else 0
    )

    col1.metric("Segnali totali", total_signals)
    col2.metric("Approvati", approved)
    col3.metric("Bloccati", blocked)
    col4.metric("Confidence media", f"{avg_confidence:.2f}")

    col5, col6, col7, col8 = st.columns(4)

    buy_count = int((signals_db["side"] == "BUY").sum()) if "side" in signals_db.columns else 0
    sell_count = int((signals_db["side"] == "SELL").sum()) if "side" in signals_db.columns else 0
    no_trade_count = int((signals_db["side"] == "NO_TRADE").sum()) if "side" in signals_db.columns else 0

    col5.metric("BUY", buy_count)
    col6.metric("SELL", sell_count)
    col7.metric("NO_TRADE", no_trade_count)
    col8.metric("RR medio", f"{avg_rr:.2f}")

    st.divider()

    if "side" in signals_db.columns:
        st.subheader("Distribuzione segnali")
        st.bar_chart(signals_db["side"].value_counts())

    st.divider()

    if "approved_by_risk_manager" in signals_db.columns:
        st.subheader("Approvati vs bloccati")
        approval_counts = signals_db["approved_by_risk_manager"].map(
            {True: "Approvato", False: "Bloccato"}
        ).value_counts()
        st.bar_chart(approval_counts)

    st.divider()

    st.subheader("Motivi di blocco")

    if "blocked_reason" in signals_db.columns:
        blocked_reasons = signals_db["blocked_reason"].dropna()

        if blocked_reasons.empty:
            st.info("Nessun motivo di blocco presente.")
        else:
            blocked_reason_counts = (
                blocked_reasons
                .value_counts()
                .rename_axis("blocked_reason")
                .reset_index(name="count")
            )

            st.dataframe(
                blocked_reason_counts,
                width="stretch",
            )

    st.divider()

    st.subheader("Filtri segnali")

    filtered = signals_db.copy()

    if "side" in filtered.columns:
        sides = sorted(filtered["side"].dropna().unique().tolist())
        selected_sides = st.multiselect("Side", sides, default=sides)

        if selected_sides:
            filtered = filtered[filtered["side"].isin(selected_sides)]

    if "approved_by_risk_manager" in filtered.columns:
        approval_options = ["Approvati", "Bloccati"]
        selected_approval = st.multiselect(
            "Stato risk manager",
            approval_options,
            default=approval_options,
        )

        if selected_approval != approval_options:
            if selected_approval == ["Approvati"]:
                filtered = filtered[filtered["approved_by_risk_manager"] == True]
            elif selected_approval == ["Bloccati"]:
                filtered = filtered[filtered["approved_by_risk_manager"] == False]

    st.divider()

    st.subheader("Tabella segnali SQLite")
    st.dataframe(filtered, width="stretch")

    st.divider()

    csv_data = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Scarica segnali filtrati CSV",
        data=csv_data,
        file_name="sqlite_signals_filtered.csv",
        mime="text/csv",
    )



def render_session_analysis_tab() -> None:
    """Render session analysis from SQLite trades."""
    trades_db = load_sqlite_table(DATABASE_PATH, "trades")

    if trades_db.empty:
        st.warning("Nessun trade trovato nel database SQLite.")
        st.code("python -m src.main")
        st.code("python scripts/run_paper_trading.py")
        return

    st.subheader("Analisi per sessione")

    if "timestamp_open" not in trades_db.columns or "profit_loss" not in trades_db.columns:
        st.error("Servono le colonne timestamp_open e profit_loss.")
        return

    trades_with_session = add_session_column(trades_db, timestamp_column="timestamp_open")
    summary = calculate_session_summary(trades_with_session)

    st.subheader("Riepilogo sessioni")
    st.dataframe(summary, width="stretch")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**P&L per sessione**")
        if not summary.empty:
            st.bar_chart(summary.set_index("session")["net_profit"])

    with col2:
        st.markdown("**Numero trade per sessione**")
        if not summary.empty:
            st.bar_chart(summary.set_index("session")["total_trades"])

    st.divider()

    st.subheader("Filtra trade per sessione")

    sessions = sorted(trades_with_session["session"].dropna().unique().tolist())
    selected_sessions = st.multiselect("Sessioni", sessions, default=sessions)

    filtered = trades_with_session.copy()

    if selected_sessions:
        filtered = filtered[filtered["session"].isin(selected_sessions)]

    st.dataframe(filtered, width="stretch")

    st.warning(
        "Per ora le sessioni sono calcolate su fasce orarie semplici. "
        "Più avanti possiamo gestire timezone e ora legale in modo più preciso."
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

    tab_backtest, tab_database, tab_signals, tab_analysis, tab_sessions, tab_safety = st.tabs(
        ["Backtest CSV", "Database SQLite", "Segnali SQLite", "Analisi Strategia", "Sessioni", "Sicurezza Live"]
    )

    with tab_backtest:
        render_backtest_report_tab()

    with tab_database:
        render_database_tab()

    with tab_signals:
        render_signals_tab()

    with tab_analysis:
        render_strategy_analysis_tab()

    with tab_sessions:
        render_session_analysis_tab()

    with tab_safety:
        render_safety_tab()


if __name__ == "__main__":
    main()
