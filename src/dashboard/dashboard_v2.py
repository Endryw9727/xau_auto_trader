"""
Streamlit Dashboard V2 for XAU Auto Trader.

Tabs:
- Asset Selector
- Backtest CSV
- Database SQLite
- Strategy Analysis
- Live Safety
- Macro Fundamental
- AI Reasoning
- Smart Money
- ML Training
- Live Data Feed
- Paper Trading V2

Usage:
    streamlit run src/dashboard/dashboard_v2.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="XAU Auto Trader V2", layout="wide", initial_sidebar_state="expanded")

st.title("📊 XAU Auto Trader V2 Dashboard")
st.markdown("*Technical + Macro + News + AI Reasoning + Smart Money + ML + Multi-Asset*")

# Sidebar
st.sidebar.header("⚙️ Settings")

# Asset selector
from src.market_data.asset_registry import list_available_assets, get_asset_config
available_assets = list_available_assets()
selected_asset = st.sidebar.selectbox("Asset", available_assets, index=available_assets.index("XAUUSD") if "XAUUSD" in available_assets else 0)

asset_config = get_asset_config(selected_asset)
st.sidebar.markdown(f"**{asset_config.display_name}**")
st.sidebar.markdown(f"Class: {asset_config.asset_class}")
st.sidebar.markdown(f"Volatility: {asset_config.volatility_profile}")
st.sidebar.markdown(f"Hours: {asset_config.trading_hours}")

show_smc = st.sidebar.checkbox("Show Smart Money", value=True)
show_macro = st.sidebar.checkbox("Show Macro Layer", value=True)
show_ai = st.sidebar.checkbox("Show AI Reasoning", value=True)
show_ml = st.sidebar.checkbox("Show ML Training", value=True)
show_live = st.sidebar.checkbox("Show Live Feed", value=True)

# Tabs
tabs = st.tabs([
    "🏠 Overview",
    "📁 Backtest",
    "🗄️ Database",
    "📈 Strategy",
    "🛡️ Safety",
    "🌍 Macro",
    "🤖 AI Reasoning",
    "🏗️ Smart Money",
    "🧠 ML Training",
    "📡 Live Feed",
    "📰 Paper Trading",
])

# Tab 0: Overview
with tabs[0]:
    st.header("🏠 System Overview")

    col1, col2, col3 = st.columns(3)
    col1.metric("Selected Asset", selected_asset)
    col2.metric("Asset Class", asset_config.asset_class)
    col3.metric("Volatility", asset_config.volatility_profile)

    st.subheader("Active Layers")
    layers = {
        "Technical": True,
        "Smart Money": show_smc,
        "Macro": show_macro,
        "News": True,
        "AI Reasoning": show_ai,
        "ML": show_ml,
        "Live Feed": show_live,
    }
    for layer, active in layers.items():
        status = "🟢 Active" if active else "⚪ Inactive"
        st.write(f"{status} — {layer}")

# Tab 1: Backtest
with tabs[1]:
    st.header("📁 Backtest Reports")
    trades_path = Path("reports/backtests/trades.csv")
    metrics_path = Path("reports/backtests/metrics.csv")

    if trades_path.exists():
        trades = pd.read_csv(trades_path)
        st.subheader("Trades")
        st.dataframe(trades, use_container_width=True)
        st.metric("Total Trades", len(trades))
        if "outcome_label" in trades.columns:
            wins = len(trades[trades["outcome_label"] == "win"])
            losses = len(trades[trades["outcome_label"] == "loss"])
            col1, col2, col3 = st.columns(3)
            col1.metric("Wins", wins)
            col2.metric("Losses", losses)
            col3.metric("Win Rate", f"{wins/(wins+losses)*100:.1f}%" if (wins+losses) > 0 else "N/A")
    else:
        st.info("Run backtest first: `python -m src.main`")

    if metrics_path.exists():
        metrics = pd.read_csv(metrics_path)
        st.subheader("Metrics")
        st.dataframe(metrics, use_container_width=True)

# Tab 2: Database
with tabs[2]:
    st.header("🗄️ SQLite Database")
    db_path = Path("data/database/trading.db")
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(db_path)
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
        st.subheader("Tables")
        st.dataframe(tables)

        for table in tables["name"]:
            with st.expander(f"Table: {table}"):
                df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 100", conn)
                st.dataframe(df, use_container_width=True)
        conn.close()
    else:
        st.info("Database not found. Run backtest or paper trading first.")

# Tab 3: Strategy
with tabs[3]:
    st.header("📈 Strategy Analysis")
    st.markdown(f"""
    **Current Asset:** {selected_asset} ({asset_config.display_name})

    **Asset-Specific Parameters:**
    - ATR SL Multiplier: {asset_config.atr_multiplier_sl or 'Default'}
    - ATR TP Multiplier: {asset_config.atr_multiplier_tp or 'Default'}
    - RSI Buy Max: {asset_config.rsi_buy_max or 'Default'}
    - RSI Sell Min: {asset_config.rsi_sell_min or 'Default'}
    - Min ADX: {asset_config.min_adx or 'Default'}
    - Min R:R: {asset_config.min_risk_reward or 'Default'}
    """)

    if trades_path.exists():
        trades = pd.read_csv(trades_path)
        if "risk_reward" in trades.columns:
            st.subheader("Risk:Reward Distribution")
            st.bar_chart(trades["risk_reward"].value_counts().sort_index())

# Tab 4: Safety
with tabs[4]:
    st.header("🛡️ Live Trading Safety")
    from src.settings import load_settings
    settings = load_settings()
    st.json({
        "LIVE_MODE": settings.trading.live_mode,
        "SYMBOL": settings.trading.symbol,
        "BASE_TIMEFRAME": settings.trading.base_timeframe,
        "MAX_OPEN_TRADES": settings.risk.max_open_trades,
        "MAX_DAILY_LOSS": f"{settings.risk.max_daily_loss*100:.1f}%",
        "MIN_RISK_REWARD": settings.risk.min_risk_reward,
    })
    if settings.trading.live_mode:
        st.error("⚠️ LIVE MODE IS ENABLED — THIS SHOULD ONLY BE USED WITH DEMO BROKER")
    else:
        st.success("✅ LIVE MODE IS DISABLED — Safe for research")

# Tab 5: Macro
with tabs[5]:
    st.header("🌍 Macro Fundamental Layer")
    if show_macro:
        try:
            from src.macro.macro_engine import MacroEngine
            engine = MacroEngine()
            result = engine.analyze()

            col1, col2, col3 = st.columns(3)
            col1.metric("Macro Score", f"{result.score:+.2f}")
            col2.metric("Bias", result.score_label)
            col3.metric("Confidence", f"{result.confidence:.0%}")

            st.subheader("Snapshot")
            st.json({
                "DXY": result.snapshot.dxy_value,
                "DXY Trend": result.snapshot.dxy_trend,
                "US10Y": result.snapshot.us10y_value,
                "US10Y Trend": result.snapshot.us10y_trend,
                "VIX": result.snapshot.vix_value,
                "VIX Level": result.snapshot.vix_level,
                "SPX": result.snapshot.spx_value,
                "SPX Trend": result.snapshot.spx_trend,
                "Timestamp": result.snapshot.timestamp,
            })

            st.subheader("Explanation")
            st.text(result.explanation)

            if result.dxy_correlation:
                st.metric("XAU/DXY Correlation", f"{result.dxy_correlation:.2f}")
        except Exception as e:
            st.error(f"Macro analysis error: {e}")
            st.info("Ensure internet connection is available for Yahoo Finance data.")
    else:
        st.info("Macro layer disabled in sidebar.")

# Tab 6: AI Reasoning
with tabs[6]:
    st.header("🤖 AI Reasoning Engine")
    if show_ai:
        st.markdown("""
        The AI Reasoning Engine analyzes:
        - **Technical Score** (40%): Trend, ADX, RSI, R:R
        - **Macro Score** (30%): DXY, US10Y, VIX, SPX
        - **News Score** (15%): Economic calendar events
        - **Session Score** (10%): London, NY, Asia
        - **Risk Score** (5%): Drawdown, consecutive losses
        """)

        try:
            from src.ai_reasoning.context_builder import build_context
            from src.ai_reasoning.score_composer import ScoreWeights, compose_score
            from src.ai_reasoning.warning_system import generate_warnings, should_block
            from src.ai_reasoning.explanation_engine import generate_explanation
            from src.data_feed.market_data import load_csv_data
            from src.macro.macro_engine import MacroEngine
            from src.news.news_filter import NewsFilter
            from src.strategy.signals_v2 import generate_signals_v2
            from src.strategy.rules import StrategyConfig

            csv_path = Path(f"data/raw/{selected_asset.lower()}.csv")
            if not csv_path.exists():
                csv_path = Path("data/raw/xauusd.csv")

            if csv_path.exists():
                df = load_csv_data(csv_path)
                strategy_config = StrategyConfig()
                signals_df = generate_signals_v2(df, strategy_config)
                last = signals_df.iloc[-1]

                if str(last["signal"]) != "NO_TRADE":
                    macro = MacroEngine()
                    macro_result = macro.analyze(df)
                    news = NewsFilter()
                    news_result = news.check()

                    context = build_context(
                        df=df, signal_row=last,
                        macro_result=macro_result, news_result=news_result,
                        account_balance=1000, open_trades=0,
                        daily_loss=0.0, consecutive_losses=0,
                    )
                    weights = ScoreWeights()
                    composite = compose_score(context, weights)
                    warnings = generate_warnings(context, composite)
                    blocked, reason = should_block(warnings)

                    col1, col2, col3 = st.columns(3)
                    col1.metric("Composite Score", f"{composite.score:.2f}")
                    col2.metric("Confidence", f"{composite.confidence:.0%}")
                    col3.metric("Recommendation", composite.recommendation)

                    st.subheader("Score Breakdown")
                    breakdown_df = pd.DataFrame([
                        {"Component": k, "Value": round(v, 3)}
                        for k, v in composite.breakdown.items()
                    ])
                    st.dataframe(breakdown_df, use_container_width=True)

                    if warnings:
                        st.subheader("⚠️ Warnings")
                        for w in warnings:
                            level_color = "🔴" if w.level == "CRITICAL" else ("🟡" if w.level == "WARNING" else "🟢")
                            st.write(f"{level_color} **[{w.level}]** {w.category}: {w.message} → `{w.action}`")

                    if blocked:
                        st.error(f"❌ Trade BLOCKED: {reason}")
                    else:
                        st.success(f"✅ Trade ALLOWED: {composite.recommendation}")

                    with st.expander("Full Explanation"):
                        st.text(generate_explanation(context, composite))
                else:
                    st.info(f"No active signal. Reason: {last['signal_reason']}")
            else:
                st.info(f"Load data first: {csv_path}")
        except Exception as e:
            st.error(f"AI analysis error: {e}")
    else:
        st.info("AI Reasoning disabled in sidebar.")

# Tab 7: Smart Money
with tabs[7]:
    st.header("🏗️ Smart Money Concepts")
    if show_smc:
        try:
            from src.data_feed.market_data import load_csv_data
            from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money

            csv_path = Path(f"data/raw/{selected_asset.lower()}.csv")
            if not csv_path.exists():
                csv_path = Path("data/raw/xauusd.csv")

            if csv_path.exists():
                df = load_csv_data(csv_path)
                sm = analyze_smart_money(df, lookback=50)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Bias", sm.bias)
                col2.metric("FVGs", len(sm.fvgs))
                col3.metric("Order Blocks", len(sm.order_blocks))
                col4.metric("Sweeps", len(sm.liquidity_sweeps))

                if sm.key_support:
                    st.metric("Key Support", f"{sm.key_support:.2f}")
                if sm.key_resistance:
                    st.metric("Key Resistance", f"{sm.key_resistance:.2f}")

                st.subheader("Explanation")
                st.text(sm.explanation)

                if sm.fvgs:
                    st.subheader("Recent FVGs")
                    fvg_df = pd.DataFrame([
                        {"Type": f.type, "Top": f.top, "Bottom": f.bottom, "Size": f.size}
                        for f in sm.fvgs[-10:]
                    ])
                    st.dataframe(fvg_df, use_container_width=True)

                if sm.order_blocks:
                    st.subheader("Recent Order Blocks")
                    ob_df = pd.DataFrame([
                        {"Type": o.type, "Time": str(o.time), "Low": o.low, "High": o.high}
                        for o in sm.order_blocks[-10:]
                    ])
                    st.dataframe(ob_df, use_container_width=True)
            else:
                st.info(f"Load data first: {csv_path}")
        except Exception as e:
            st.error(f"Smart Money error: {e}")
    else:
        st.info("Smart Money disabled in sidebar.")

# Tab 8: ML Training
with tabs[8]:
    st.header("🧠 Machine Learning")
    if show_ml:
        try:
            from src.ml.continuous_trainer import ContinuousTrainer
            from src.ml.model_persistence import ModelPersistence

            trainer = ContinuousTrainer()
            persistence = ModelPersistence()

            st.subheader("Training History")
            history = trainer.get_training_history()
            if not history.empty:
                st.dataframe(history, use_container_width=True)
                st.line_chart(history.set_index("timestamp")[["accuracy", "train_samples"]])
            else:
                st.info("No training history found. Run: `python scripts/run_continuous_ml.py`")

            st.subheader("Drift Detection")
            drift = trainer.get_drift_status()
            if drift.get("status") == "ok":
                col1, col2, col3 = st.columns(3)
                col1.metric("Checkpoints", drift.get("checkpoints_count", 0))
                col2.metric("Latest Accuracy", f"{drift.get('latest_accuracy', 0):.1%}")
                col3.metric("Trend", drift.get("accuracy_trend", "unknown"))
            else:
                st.info(drift.get("message", "No drift data available"))

            st.subheader("Model Checkpoints")
            checkpoints = persistence.list_checkpoints()
            if checkpoints:
                cp_df = pd.DataFrame([{
                    "Version": c.version,
                    "Timestamp": c.timestamp,
                    "Samples": c.train_samples,
                    "Accuracy": f"{c.accuracy:.1%}",
                } for c in checkpoints[-10:]])
                st.dataframe(cp_df, use_container_width=True)
            else:
                st.info("No checkpoints saved yet.")
        except Exception as e:
            st.error(f"ML error: {e}")
    else:
        st.info("ML disabled in sidebar.")

# Tab 9: Live Feed
with tabs[9]:
    st.header("📡 Live Data Feed")
    if show_live:
        try:
            from src.data_feed.websocket_client import WebSocketDataFeed

            feed = WebSocketDataFeed(
                provider="yahoo_fallback",
                symbols=[selected_asset],
                poll_interval=5.0,
            )

            st.subheader("Latest Prices")
            prices = feed.get_all_prices()
            if prices:
                for symbol, tick in prices.items():
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Symbol", symbol)
                    col2.metric("Bid", f"{tick.bid:.2f}")
                    col3.metric("Ask", f"{tick.ask:.2f}")
                    col4.metric("Spread", f"{(tick.ask - tick.bid):.2f}")
            else:
                st.info("No live prices available. Start the data feed daemon.")

            st.subheader("Feed Status")
            st.json({
                "Provider": "yahoo_fallback",
                "Symbols": [selected_asset],
                "Poll Interval": "5s",
                "Status": "Ready to start",
            })
        except Exception as e:
            st.error(f"Live feed error: {e}")
    else:
        st.info("Live feed disabled in sidebar.")

# Tab 10: Paper Trading
with tabs[10]:
    st.header("📰 Paper Trading V2")
    try:
        from src.paper.paper_trading_v2 import PaperTradingEngineV2
        from src.settings import load_settings

        settings = load_settings()
        engine = PaperTradingEngineV2(settings)
        stats = engine.get_stats()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Balance", f"{stats['balance']:.2f}")
        col2.metric("Open Trades", stats['open_trades'])
        col3.metric("Total Trades", stats['total_trades'])
        col4.metric("Consecutive Losses", stats['consecutive_losses'])

        st.subheader("Run Paper Trading Cycle")
        if st.button("▶️ Run Single Cycle"):
            with st.spinner("Running paper trading cycle..."):
                result = engine.run_cycle()
            st.json(result)

        if engine.trades:
            st.subheader("Trade History")
            trades_df = pd.DataFrame([
                {
                    "ID": t.id,
                    "Time": t.timestamp,
                    "Side": t.side,
                    "Entry": t.entry,
                    "SL": t.stop_loss,
                    "TP": t.take_profit,
                    "R:R": t.risk_reward,
                    "Units": t.units,
                    "Macro": t.macro_label,
                    "SMC": t.smc_score,
                    "AI": t.ai_recommendation,
                }
                for t in engine.trades[-20:]
            ])
            st.dataframe(trades_df, use_container_width=True)
    except Exception as e:
        st.error(f"Paper Trading V2 error: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("**XAU Auto Trader V2**")
st.sidebar.markdown("*Multi-Asset | AI-Powered | Cloud-Ready*")
