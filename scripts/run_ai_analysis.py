"""
Demo script: Run AI Reasoning Analysis on current data.

This script demonstrates the full V2 pipeline:
1. Load market data
2. Run macro analysis
3. Run news filter
4. Generate signals with SMC
5. Build AI context
6. Generate explanation and warnings
7. Print full report

Usage:
    python scripts/run_ai_analysis.py

Does NOT execute trades.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ai_reasoning.context_builder import build_context
from src.ai_reasoning.explanation_engine import generate_explanation
from src.ai_reasoning.score_composer import ScoreWeights, compose_score
from src.ai_reasoning.warning_system import generate_warnings, should_block
from src.data_feed.market_data import load_csv_data
from src.macro.macro_engine import MacroEngine
from src.news.news_filter import NewsFilter
from src.settings import load_settings
from src.strategy.rules import StrategyConfig
from src.strategy.signals_v2 import generate_signals_v2
from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money

CSV_PATH = Path("data/raw/xauusd.csv")


def main():
    print("=" * 70)
    print("XAU Auto Trader V2 — AI Reasoning Demo")
    print("=" * 70)
    print()

    settings = load_settings()

    if not CSV_PATH.exists():
        print(f"❌ CSV not found: {CSV_PATH}")
        print("   Generate fake data: python scripts/generate_fake_xauusd_data.py")
        return

    print(f"📁 Loading: {CSV_PATH}")
    df = load_csv_data(CSV_PATH)
    print(f"   Candles: {len(df)} | From: {df.index.min()} | To: {df.index.max()}")
    print()

    # Strategy config
    strategy_config = StrategyConfig(
        symbol=settings.trading.symbol,
        timeframe=settings.trading.base_timeframe,
        min_adx=settings.filters.min_adx,
        min_risk_reward=settings.risk.min_risk_reward,
        atr_multiplier_sl=settings.strategy.atr_multiplier_sl,
        atr_multiplier_tp=settings.strategy.atr_multiplier_tp,
        rsi_buy_max=settings.strategy.rsi_buy_max,
        rsi_sell_min=settings.strategy.rsi_sell_min,
    )

    # 1. Smart Money Analysis
    print("🏗️  Smart Money Concepts Analysis")
    print("-" * 70)
    sm = analyze_smart_money(df, lookback=settings.smart_money.fvg_lookback)
    print(f"   Bias: {sm.bias}")
    print(f"   FVGs: {len(sm.fvgs)} | OBs: {len(sm.order_blocks)} | Sweeps: {len(sm.liquidity_sweeps)}")
    if sm.key_support:
        print(f"   Key Support: {sm.key_support:.2f}")
    if sm.key_resistance:
        print(f"   Key Resistance: {sm.key_resistance:.2f}")
    print(f"   {sm.explanation}")
    print()

    # 2. Macro Analysis
    print("🌍 Macro Fundamental Analysis")
    print("-" * 70)
    if settings.macro.enabled:
        try:
            macro = MacroEngine()
            macro_result = macro.analyze(df)
            print(f"   Macro Score: {macro_result.score:+.2f} ({macro_result.score_label})")
            print(f"   Confidence: {macro_result.confidence:.0%}")
            print(f"   DXY Correlation: {macro_result.dxy_correlation:.2f}" if macro_result.dxy_correlation else "   DXY Correlation: N/A")
            print(f"   {macro_result.explanation}")
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    else:
        print("   Macro layer disabled in config")
    print()

    # 3. News Filter
    print("📰 News & Calendar Filter")
    print("-" * 70)
    if settings.news.enabled:
        try:
            news = NewsFilter(
                block_before_minutes=settings.news.block_before_minutes,
                block_after_minutes=settings.news.block_after_minutes,
            )
            news_result = news.check()
            if news_result.allowed:
                print("   ✅ Trading ALLOWED")
            else:
                print(f"   ❌ Trading BLOCKED: {news_result.reason}")
            print(f"   Risk Level: {news_result.risk_level}")
            if news_result.next_event:
                print(f"   Next Event: {news_result.next_event.name} in {news_result.minutes_until_event:.0f}min")
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    else:
        print("   News layer disabled in config")
    print()

    # 4. Signal Generation with SMC
    print("📈 Signal Generation (with SMC Confluence)")
    print("-" * 70)
    signals_df = generate_signals_v2(df, strategy_config, use_smc=settings.smart_money.enabled)
    last = signals_df.iloc[-1]
    signal = str(last["signal"])

    print(f"   Signal: {signal}")
    if signal != "NO_TRADE":
        print(f"   Entry: {last['entry']:.2f}")
        print(f"   Stop:  {last['stop_loss']:.2f}")
        print(f"   Target: {last['take_profit']:.2f}")
        print(f"   R:R = 1:{last['risk_reward']:.2f}")
        print(f"   SMC Score: {last['smc_score']:.2f}")
        print(f"   SMC: {last['smc_confluence']}")
    else:
        print(f"   Reason: {last['signal_reason']}")
    print()

    # 5. AI Reasoning
    if signal != "NO_TRADE" and settings.ai_reasoning.enabled:
        print("🤖 AI Reasoning Engine")
        print("-" * 70)
        try:
            macro_result = macro_result if 'macro_result' in dir() and macro_result else None
            news_result = news_result if 'news_result' in dir() and news_result else None

            context = build_context(
                df=df,
                signal_row=last,
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

            explanation = generate_explanation(context, composite)
            print(explanation)
            print()

            if warnings:
                print("⚠️  WARNINGS:")
                for w in warnings:
                    icon = "🔴" if w.level == "CRITICAL" else ("🟡" if w.level == "WARNING" else "🟢")
                    print(f"   {icon} [{w.level}] {w.category}: {w.message} → {w.action}")
                print()

            if blocked:
                print(f"❌ TRADE BLOCKED BY AI: {block_reason}")
            else:
                print(f"✅ AI RECOMMENDATION: {composite.recommendation}")
                print(f"   Score: {composite.score:.2f}/1.00 | Confidence: {composite.confidence:.0%}")

        except Exception as e:
            print(f"   ⚠️  AI Reasoning Error: {e}")
        print()

    print("=" * 70)
    print("Demo complete. No trades executed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
