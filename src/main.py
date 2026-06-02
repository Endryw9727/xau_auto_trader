"""
Main entry point V2 for XAU Auto Trader.

Integrates:
- Technical signals (EMA, ADX, RSI, ATR)
- Macro fundamental layer (DXY, US10Y, VIX)
- News & calendar filter
- AI reasoning engine (explanation, warnings, composite score)
- Smart Money concepts (FVG, OB, Liquidity)

Usage:
 python -m src.main

Expected CSV file:
 data/raw/xauusd.csv

This script does not execute real trades.
It only runs a local backtest and exports reports.
"""

from __future__ import annotations

from pathlib import Path

from src.ai_reasoning.context_builder import build_context
from src.ai_reasoning.explanation_engine import generate_explanation, generate_summary
from src.ai_reasoning.score_composer import ScoreWeights, compose_score
from src.ai_reasoning.warning_system import generate_warnings, should_block
from src.backtesting.backtester import BacktestConfig, export_backtest_report, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.data_feed.market_data import load_csv_data
from src.journal.trade_journal import save_trades_dataframe_to_db
from src.macro.macro_engine import MacroEngine
from src.news.news_filter import NewsFilter
from src.settings import load_settings
from src.strategy.rules import StrategyConfig
from src.strategy.signals import generate_signals
from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money, smart_money_to_dict

RAW_DATA_PATH = Path("data/raw/xauusd.csv")
REPORT_DIR = Path("reports/backtests")

def main() -> None:
    """Run a local backtest with full AI reasoning and macro analysis."""
    print("=" * 70)
    print("XAU Auto Trader V2 - Local Backtest with AI Reasoning")
    print("=" * 70)

    settings = load_settings()

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Create this file first: data/raw/xauusd.csv")
        print("Required columns: Date, Open, High, Low, Close, Volume")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print(f"Macro enabled: {settings.macro.enabled}")
    print(f"News enabled: {settings.news.enabled}")
    print(f"AI reasoning enabled: {settings.ai_reasoning.enabled}")
    print(f"Smart Money enabled: {settings.smart_money.enabled}")
    print("")

    print(f"Loading market data from: {RAW_DATA_PATH}")
    df = load_csv_data(RAW_DATA_PATH)
    print(f"Loaded candles: {len(df)}")
    print(f"From: {df.index.min()}  To: {df.index.max()}")
    print("")

    # ===================== MACRO LAYER =====================
    macro_result = None
    if settings.macro.enabled:
        print("🌍 Running macro fundamental analysis...")
        try:
            macro_engine = MacroEngine()
            macro_result = macro_engine.analyze(df)
            print(f"   Macro score: {macro_result.score:+.2f} ({macro_result.score_label})")
            print(f"   Confidence: {macro_result.confidence:.0%}")
            print(f"   {macro_result.explanation}")
        except Exception as e:
            print(f"   ⚠️  Macro analysis failed: {e}")
        print("")

    # ===================== NEWS LAYER =====================
    news_result = None
    if settings.news.enabled:
        print("📰 Running news & calendar filter...")
        try:
            news_filter = NewsFilter(
                block_before_minutes=settings.news.block_before_minutes,
                block_after_minutes=settings.news.block_after_minutes,
            )
            news_result = news_filter.check()
            if news_result.allowed:
                print("   ✅ Trading allowed")
                if news_result.next_event:
                    print(f"   Next event: {news_result.next_event.name}")
            else:
                print(f"   ❌ BLOCKED: {news_result.reason}")
        except Exception as e:
            print(f"   ⚠️  News filter failed: {e}")
        print("")

    # ===================== SMART MONEY =====================
    sm_analysis = None
    if settings.smart_money.enabled:
        print("🏗️  Running Smart Money analysis...")
        try:
            sm_analysis = analyze_smart_money(df, lookback=settings.smart_money.fvg_lookback)
            print(f"   Bias: {sm_analysis.bias}")
            print(f"   FVGs: {len(sm_analysis.fvgs)} | OBs: {len(sm_analysis.order_blocks)} | Sweeps: {len(sm_analysis.liquidity_sweeps)}")
            if sm_analysis.key_support:
                print(f"   Key Support: {sm_analysis.key_support:.2f}")
            if sm_analysis.key_resistance:
                print(f"   Key Resistance: {sm_analysis.key_resistance:.2f}")
        except Exception as e:
            print(f"   ⚠️  Smart Money analysis failed: {e}")
        print("")

    # ===================== SIGNAL GENERATION =====================
    strategy_config = build_strategy_config(settings)
    backtest_config = build_backtest_config(settings)

    print("📈 Generating signals...")
    signals_df = generate_signals(df, strategy_config)
    last_signal = signals_df.iloc[-1]
    print(f"   Last signal: {last_signal['signal']}")
    if last_signal['signal'] != 'NO_TRADE':
        print(f"   Entry: {last_signal['entry']:.2f} | SL: {last_signal['stop_loss']:.2f} | TP: {last_signal['take_profit']:.2f}")
        print(f"   R:R = 1:{last_signal['risk_reward']:.2f}")
    print("")

    # ===================== AI REASONING =====================
    if settings.ai_reasoning.enabled and last_signal['signal'] != 'NO_TRADE':
        print("🤖 Running AI reasoning engine...")
        try:
            context = build_context(
                df=df,
                signal_row=last_signal,
                macro_result=macro_result,
                news_result=news_result,
                account_balance=settings.backtest.initial_balance,
                open_trades=0,
                daily_loss=0.0,
                consecutive_losses=0,
            )

            weights = ScoreWeights(
                technical=settings.ai_reasoning.weights.technical,
                macro=settings.ai_reasoning.weights.macro,
                news=settings.ai_reasoning.weights.news,
                session=settings.ai_reasoning.weights.session,
                risk=settings.ai_reasoning.weights.risk,
            )

            composite = compose_score(context, weights)
            warnings = generate_warnings(context, composite)
            blocked, block_reason = should_block(warnings)

            if settings.ai_reasoning.generate_explanations:
                explanation = generate_explanation(context, composite)
                print(explanation)

            if settings.ai_reasoning.generate_warnings and warnings:
                print("\n⚠️  WARNINGS:")
                for w in warnings:
                    icon = "🔴" if w.level == "CRITICAL" else ("🟡" if w.level == "WARNING" else "🟢")
                    print(f"   {icon} [{w.level}] {w.category}: {w.message} → {w.action}")

            if blocked:
                print(f"\n❌ TRADE BLOCKED by AI: {block_reason}")
            else:
                print(f"\n✅ AI RECOMMENDATION: {composite.recommendation} (score={composite.score:.2f}, conf={composite.confidence:.0%})")

        except Exception as e:
            print(f"   ⚠️  AI reasoning failed: {e}")
        print("")

    # ===================== BACKTEST =====================
    print("📊 Running backtest...")
    result = run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
    )

    trades_path, metrics_path = export_backtest_report(result, REPORT_DIR)
    inserted_trades = save_trades_dataframe_to_db(result.trades, mode="backtest")
    metrics = metrics_to_dict(result.metrics)

    print("")
    print("=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    print(f"Initial balance: {backtest_config.initial_balance:.2f}")
    print(f"Final balance: {result.final_balance:.2f}")
    print(f"Net profit: {metrics['net_profit']:.2f}")
    print(f"Total trades: {metrics['total_trades']}")
    print(f"Wins: {metrics['wins']} | Losses: {metrics['losses']} | Breakeven: {metrics['breakeven']}")
    print(f"Win rate: {metrics['win_rate']:.2f}%")
    print(f"Profit factor: {metrics['profit_factor']:.2f}")
    print(f"Expectancy: {metrics['expectancy']:.2f}")
    print(f"Max drawdown: {metrics['max_drawdown']:.2f}")
    print(f"Max consecutive wins: {metrics['max_consecutive_wins']}")
    print(f"Max consecutive losses: {metrics['max_consecutive_losses']}")
    print("")
    print(f"Reports: {trades_path} | {metrics_path}")
    print(f"Trades saved to SQLite: {inserted_trades}")
    print("")
    print("⚠️  IMPORTANT: This is a backtest only, not live trading.")
    print("=" * 70)

def build_strategy_config(settings) -> StrategyConfig:
    return StrategyConfig(
        symbol=settings.trading.symbol,
        timeframe=settings.trading.base_timeframe,
        min_adx=settings.filters.min_adx,
        min_risk_reward=settings.risk.min_risk_reward,
        atr_multiplier_sl=settings.strategy.atr_multiplier_sl,
        atr_multiplier_tp=settings.strategy.atr_multiplier_tp,
        rsi_buy_max=settings.strategy.rsi_buy_max,
        rsi_sell_min=settings.strategy.rsi_sell_min,
    )

def build_backtest_config(settings) -> BacktestConfig:
    return BacktestConfig(
        initial_balance=settings.backtest.initial_balance,
        risk_per_trade=settings.risk.risk_per_trade,
        max_risk_per_trade=settings.risk.max_risk_per_trade,
        max_daily_loss=settings.risk.max_daily_loss,
        max_open_trades=settings.risk.max_open_trades,
        max_consecutive_losses=settings.risk.max_consecutive_losses,
        min_risk_reward=settings.risk.min_risk_reward,
        value_per_point=settings.risk.value_per_point,
        commission_per_trade=settings.backtest.commission_per_trade,
        slippage_points=settings.backtest.slippage_points,
        warmup_candles=settings.backtest.warmup_candles,
        rolling_window_candles=settings.backtest.rolling_window_candles,
        allowed_sessions=settings.sessions.enabled_sessions,
    )

if __name__ == "__main__":
    main()
