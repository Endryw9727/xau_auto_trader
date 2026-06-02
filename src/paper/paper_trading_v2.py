"""
Paper Trading Engine V2.

Integrates all layers:
- Technical signals with SMC confluence
- Macro fundamental filter
- News & calendar filter
- AI reasoning engine (explanation + warnings)
- Risk manager
- Demo broker (read-only)

This module does NOT execute real trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from src.ai_reasoning.context_builder import build_context
from src.ai_reasoning.explanation_engine import generate_explanation, generate_summary
from src.ai_reasoning.score_composer import ScoreWeights, compose_score
from src.ai_reasoning.warning_system import generate_warnings, should_block
from src.broker.demo_broker_guardrails import DemoBrokerGuardrails, GuardrailsConfig
from src.broker.demo_broker_readonly import DemoBrokerReadOnly
from src.data_feed.market_data import check_data_freshness, load_csv_data
from src.journal.trade_journal import save_trades_dataframe_to_db
from src.macro.macro_engine import MacroEngine
from src.news.news_filter import NewsFilter
from src.risk.risk_manager import RiskConfig, RiskManager, TradeProposal
from src.settings import load_settings
from src.strategy.rules import StrategyConfig
from src.strategy.signals_v2 import generate_signals_v2

TradeSide = Literal["BUY", "SELL", "NO_TRADE"]

@dataclass(frozen=True)
class PaperTradeV2:
    """A paper trade record with full context."""

    id: str
    timestamp: str
    side: TradeSide
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    units: float
    risk_amount: float

    # Context
    macro_score: float
    macro_label: str
    news_allowed: bool
    smc_score: float
    ai_score: float
    ai_recommendation: str
    ai_warnings: list[str]
    ai_explanation: str

    # Outcome (filled later)
    exit_price: float | None = None
    exit_time: str | None = None
    outcome: float | None = None
    outcome_label: str | None = None

class PaperTradingEngineV2:
    """Paper trading engine with full V2 layer integration."""

    def __init__(self, settings=None, initial_balance: float = 1000.0):
        self.settings = settings or load_settings()
        self.risk_config = RiskConfig(
            risk_per_trade=self.settings.risk.risk_per_trade,
            max_risk_per_trade=self.settings.risk.max_risk_per_trade,
            max_daily_loss=self.settings.risk.max_daily_loss,
            max_open_trades=self.settings.risk.max_open_trades,
            max_consecutive_losses=self.settings.risk.max_consecutive_losses,
            min_risk_reward=self.settings.risk.min_risk_reward,
            value_per_point=self.settings.risk.value_per_point,
        )
        self.risk_manager = RiskManager(self.risk_config, initial_balance)
        self.broker = DemoBrokerReadOnly(initial_balance)
        self.guardrails = DemoBrokerGuardrails(GuardrailsConfig())
        self.trades: list[PaperTradeV2] = []

        self.macro_engine = MacroEngine() if self.settings.macro.enabled else None
        self.news_filter = NewsFilter(
            block_before_minutes=self.settings.news.block_before_minutes,
            block_after_minutes=self.settings.news.block_after_minutes,
        ) if self.settings.news.enabled else None

    def run_cycle(self, df: pd.DataFrame | None = None, csv_path: Path = Path("data/raw/xauusd.csv")) -> dict:
        """
        Run one paper trading cycle.

        Parameters:
        - df: Optional OHLCV DataFrame
        - csv_path: Path to CSV if df not provided

        Returns:
        - dict with cycle results
        """
        if df is None:
            if not csv_path.exists():
                return {"error": f"CSV not found: {csv_path}"}
            df = load_csv_data(csv_path)

        # Data freshness check
        freshness = check_data_freshness(df, max_age_minutes=30)
        if not freshness["is_fresh"]:
            return {
                "error": f"Data stale: {freshness['age_minutes']:.0f} minutes old",
                "last_candle": str(freshness["last_candle_time"]),
            }

        # Macro analysis
        macro_result = None
        if self.macro_engine:
            try:
                macro_result = self.macro_engine.analyze(df)
            except Exception as e:
                print(f"Macro analysis error: {e}")

        # News filter
        news_result = None
        if self.news_filter:
            try:
                news_result = self.news_filter.check()
            except Exception as e:
                print(f"News filter error: {e}")

        # Generate signals with SMC
        strategy_config = StrategyConfig(
            symbol=self.settings.trading.symbol,
            timeframe=self.settings.trading.base_timeframe,
            min_adx=self.settings.filters.min_adx,
            min_risk_reward=self.settings.risk.min_risk_reward,
            atr_multiplier_sl=self.settings.strategy.atr_multiplier_sl,
            atr_multiplier_tp=self.settings.strategy.atr_multiplier_tp,
            rsi_buy_max=self.settings.strategy.rsi_buy_max,
            rsi_sell_min=self.settings.strategy.rsi_sell_min,
        )

        signals_df = generate_signals_v2(df, strategy_config, use_smc=self.settings.smart_money.enabled)
        last_row = signals_df.iloc[-1]
        signal = str(last_row["signal"])

        if signal == "NO_TRADE":
            return {
                "action": "NO_TRADE",
                "reason": str(last_row["signal_reason"]),
                "smc_score": float(last_row["smc_score"]) if pd.notna(last_row["smc_score"]) else 0.0,
                "macro_score": macro_result.score if macro_result else 0.0,
                "news_allowed": news_result.allowed if news_result else True,
            }

        entry = float(last_row["entry"])
        stop_loss = float(last_row["stop_loss"])
        take_profit = float(last_row["take_profit"])
        risk_reward = float(last_row["risk_reward"])

        # AI Reasoning
        ai_score = None
        ai_recommendation = "NO_AI"
        ai_warnings_list = []
        ai_explanation = ""
        blocked_by_ai = False
        block_reason = None

        if self.settings.ai_reasoning.enabled:
            try:
                context = build_context(
                    df=df,
                    signal_row=last_row,
                    macro_result=macro_result,
                    news_result=news_result,
                    account_balance=self.risk_manager.balance,
                    open_trades=len(self.risk_manager.open_trades),
                    daily_loss=self.risk_manager.daily_loss,
                    consecutive_losses=self.risk_manager.consecutive_losses,
                )

                weights = ScoreWeights(
                    technical=self.settings.ai_reasoning.weights.technical,
                    macro=self.settings.ai_reasoning.weights.macro,
                    news=self.settings.ai_reasoning.weights.news,
                    session=self.settings.ai_reasoning.weights.session,
                    risk=self.settings.ai_reasoning.weights.risk,
                )

                composite = compose_score(context, weights)
                warnings = generate_warnings(context, composite)
                blocked_by_ai, block_reason = should_block(warnings)

                ai_score = composite.score
                ai_recommendation = composite.recommendation
                ai_warnings_list = [f"[{w.level}] {w.category}: {w.message}" for w in warnings]
                ai_explanation = generate_explanation(context, composite)

                if self.settings.ai_reasoning.generate_explanations:
                    print(ai_explanation)

            except Exception as e:
                print(f"AI reasoning error: {e}")

        # Risk manager check
        proposal = TradeProposal(
            side=signal,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            timestamp=pd.Timestamp.now(),
        )

        risk_check = self.risk_manager.can_open_trade(proposal)
        if not risk_check.allowed:
            return {
                "action": "BLOCKED_BY_RISK",
                "reason": risk_check.reason,
                "signal": signal,
                "entry": entry,
                "ai_recommendation": ai_recommendation,
            }

        # Macro block check
        if macro_result and self.settings.macro.block_trade_against_macro:
            blocked, macro_reason = self.macro_engine.should_block_side(macro_result, signal)
            if blocked:
                return {
                    "action": "BLOCKED_BY_MACRO",
                    "reason": macro_reason,
                    "signal": signal,
                    "macro_score": macro_result.score,
                    "ai_recommendation": ai_recommendation,
                }

        # AI block check
        if blocked_by_ai:
            return {
                "action": "BLOCKED_BY_AI",
                "reason": block_reason,
                "signal": signal,
                "ai_recommendation": ai_recommendation,
                "ai_score": ai_score,
            }

        # News block check
        if news_result and not news_result.allowed:
            return {
                "action": "BLOCKED_BY_NEWS",
                "reason": news_result.reason,
                "signal": signal,
                "next_event": news_result.next_event.name if news_result.next_event else None,
            }

        # Guardrails check
        guard_check = self.guardrails.check_order(signal, entry, stop_loss)
        if not guard_check["allowed"]:
            return {
                "action": "BLOCKED_BY_GUARD",
                "reason": guard_check["reason"],
                "signal": signal,
            }

        # Execute paper trade
        position_size = risk_check.position_size
        if position_size is None:
            return {"error": "Position sizing failed"}

        order = self.broker.place_order(
            side=signal,
            symbol=self.settings.trading.symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            units=position_size.units,
        )

        self.risk_manager.register_trade({
            "id": order.id,
            "side": signal,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "units": position_size.units,
            "risk_amount": position_size.risk_amount,
        })

        self.guardrails.register_trade()

        trade = PaperTradeV2(
            id=order.id,
            timestamp=str(pd.Timestamp.now()),
            side=signal,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            units=position_size.units,
            risk_amount=position_size.risk_amount,
            macro_score=macro_result.score if macro_result else 0.0,
            macro_label=macro_result.score_label if macro_result else "NEUTRAL",
            news_allowed=news_result.allowed if news_result else True,
            smc_score=float(last_row["smc_score"]) if pd.notna(last_row["smc_score"]) else 0.0,
            ai_score=ai_score if ai_score is not None else 0.0,
            ai_recommendation=ai_recommendation,
            ai_warnings=ai_warnings_list,
            ai_explanation=ai_explanation,
        )
        self.trades.append(trade)

        return {
            "action": "PAPER_TRADE_EXECUTED",
            "trade_id": trade.id,
            "side": signal,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "units": position_size.units,
            "risk_amount": position_size.risk_amount,
            "macro_score": trade.macro_score,
            "macro_label": trade.macro_label,
            "smc_score": trade.smc_score,
            "ai_score": trade.ai_score,
            "ai_recommendation": trade.ai_recommendation,
            "balance": self.risk_manager.balance,
            "open_trades": len(self.risk_manager.open_trades),
        }

    def get_stats(self) -> dict:
        """Get engine statistics."""
        return {
            "balance": self.risk_manager.balance,
            "open_trades": len(self.risk_manager.open_trades),
            "total_trades": len(self.trades),
            "daily_loss": self.risk_manager.daily_loss,
            "consecutive_losses": self.risk_manager.consecutive_losses,
            "risk_manager_stats": self.risk_manager.get_stats(),
        }

    def export_trades(self, path: Path = Path("reports/paper_trading/paper_trades_v2.csv")) -> Path:
        """Export trades to CSV."""
        if not self.trades:
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([{
            "id": t.id,
            "timestamp": t.timestamp,
            "side": t.side,
            "entry": t.entry,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "risk_reward": t.risk_reward,
            "units": t.units,
            "risk_amount": t.risk_amount,
            "macro_score": t.macro_score,
            "macro_label": t.macro_label,
            "news_allowed": t.news_allowed,
            "smc_score": t.smc_score,
            "ai_score": t.ai_score,
            "ai_recommendation": t.ai_recommendation,
            "ai_warnings": " | ".join(t.ai_warnings),
        } for t in self.trades])
        df.to_csv(path, index=False)
        return path
