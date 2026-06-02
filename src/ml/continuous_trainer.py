"""
Continuous training system for ML trade predictor.

Automatically retrains the model when:
- N new trades have been recorded
- Model performance degrades (drift detection)
- Regime distribution changes significantly

Usage:
    from src.ml.continuous_trainer import ContinuousTrainer
    trainer = ContinuousTrainer(retrain_threshold=50)
    trainer.check_and_retrain(trades_df)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.ml.model_persistence import ModelCheckpoint, ModelPersistence
from src.ml.regime_detector import detect_regime
from src.ml.trade_features import build_feature_matrix
from src.ml.trade_predictor import TradePredictor

@dataclass(frozen=True)
class RetrainTrigger:
    """Reason for retraining."""

    triggered: bool
    reason: str | None
    urgency: str  # "low", "medium", "high", "critical"
    metrics: dict[str, Any]

class ContinuousTrainer:
    """Manages continuous model training and drift detection."""

    def __init__(
        self,
        retrain_threshold: int = 50,
        performance_drop_threshold: float = 0.15,
        regime_shift_threshold: float = 0.30,
        min_trades_for_retrain: int = 30,
        model_type: str = "auto",
    ):
        self.retrain_threshold = retrain_threshold
        self.performance_drop_threshold = performance_drop_threshold
        self.regime_shift_threshold = regime_shift_threshold
        self.min_trades_for_retrain = min_trades_for_retrain
        self.model_type = model_type
        self.persistence = ModelPersistence()
        self._last_train_count = 0
        self._last_regime_distribution: dict[str, int] | None = None
        self._last_accuracy: float | None = None

    def check_and_retrain(self, trades_df: pd.DataFrame, market_df: pd.DataFrame | None = None) -> dict[str, Any]:
        """
        Check if retraining is needed and execute if so.

        Parameters:
        - trades_df: DataFrame with trade history
        - market_df: Optional OHLCV for regime detection

        Returns:
        - dict with retraining status and metrics
        """
        if trades_df.empty or len(trades_df) < self.min_trades_for_retrain:
            return {"retrained": False, "reason": "Insufficient trades", "trades": len(trades_df)}

        trigger = self._should_retrain(trades_df, market_df)

        if not trigger.triggered:
            return {
                "retrained": False,
                "reason": trigger.reason,
                "urgency": trigger.urgency,
                "metrics": trigger.metrics,
            }

        # Execute retraining
        result = self._retrain(trades_df)
        result["retrained"] = True
        result["trigger_reason"] = trigger.reason
        result["urgency"] = trigger.urgency

        return result

    def _should_retrain(self, trades_df: pd.DataFrame, market_df: pd.DataFrame | None = None) -> RetrainTrigger:
        """Determine if retraining should be triggered."""
        metrics: dict[str, Any] = {}
        reasons: list[str] = []
        urgency = "low"

        current_count = len(trades_df)
        new_trades = current_count - self._last_train_count

        # Trigger 1: Trade count threshold
        metrics["new_trades"] = new_trades
        metrics["total_trades"] = current_count
        metrics["threshold"] = self.retrain_threshold

        if new_trades >= self.retrain_threshold:
            reasons.append(f"New trades threshold reached ({new_trades} >= {self.retrain_threshold})")
            urgency = max(urgency, "medium", key=lambda x: ["low", "medium", "high", "critical"].index(x))

        # Trigger 2: Performance degradation
        if self._last_accuracy is not None:
            # Calculate recent accuracy from last N trades
            recent_trades = trades_df.tail(self.retrain_threshold)
            if not recent_trades.empty and "outcome" in recent_trades.columns:
                recent_win_rate = (recent_trades["outcome"] > 0).mean()
                metrics["recent_win_rate"] = round(recent_win_rate, 3)
                metrics["last_accuracy"] = self._last_accuracy

                if recent_win_rate < self._last_accuracy * (1 - self.performance_drop_threshold):
                    reasons.append(
                        f"Performance degradation ({recent_win_rate:.1%} < "
                        f"{self._last_accuracy:.1%} * {1 - self.performance_drop_threshold:.0%})"
                    )
                    urgency = max(urgency, "high", key=lambda x: ["low", "medium", "high", "critical"].index(x))

        # Trigger 3: Regime shift
        if market_df is not None and not market_df.empty:
            regime = detect_regime(market_df)
            current_distribution = {regime.regime: 1}  # Simplified

            if self._last_regime_distribution is not None:
                # Calculate distribution shift
                total_last = sum(self._last_regime_distribution.values())
                total_current = sum(current_distribution.values())

                if total_last > 0 and total_current > 0:
                    all_regimes = set(self._last_regime_distribution) | set(current_distribution)
                    shift = sum(
                        abs(
                            self._last_regime_distribution.get(r, 0) / total_last -
                            current_distribution.get(r, 0) / total_current
                        )
                        for r in all_regimes
                    ) / 2

                    metrics["regime_shift"] = round(shift, 3)
                    if shift > self.regime_shift_threshold:
                        reasons.append(f"Regime shift detected ({shift:.1%} > {self.regime_shift_threshold:.0%})")
                        urgency = max(urgency, "high", key=lambda x: ["low", "medium", "high", "critical"].index(x))

        if reasons:
            return RetrainTrigger(
                triggered=True,
                reason=" | ".join(reasons),
                urgency=urgency,
                metrics=metrics,
            )

        return RetrainTrigger(
            triggered=False,
            reason=f"No triggers: {new_trades} new trades, stable performance",
            urgency="low",
            metrics=metrics,
        )

    def _retrain(self, trades_df: pd.DataFrame) -> dict[str, Any]:
        """Execute model retraining."""
        predictor = TradePredictor(model_type=self.model_type)
        train_result = predictor.train(trades_df)

        if "error" in train_result:
            return {"success": False, "error": train_result["error"]}

        # Save model
        version = f"v{self._last_train_count // self.retrain_threshold + 1}"
        timestamp = pd.Timestamp.now().isoformat()

        metadata = {
            "version": version,
            "timestamp": timestamp,
            "train_samples": train_result.get("train_samples", len(trades_df)),
            "accuracy": train_result.get("accuracy", 0),
            "model_type": train_result.get("model_type", "unknown"),
        }

        model_path = self.persistence.save_model(predictor, metadata)

        # Save checkpoint
        X, _ = build_feature_matrix(trades_df)
        regime_dist = trades_df.get("regime", pd.Series(["unknown"] * len(trades_df))).value_counts().to_dict()

        checkpoint = ModelCheckpoint(
            version=version,
            timestamp=timestamp,
            train_samples=len(trades_df),
            accuracy=train_result.get("accuracy", 0),
            feature_importance=train_result.get("feature_importance", {}),
            regime_distribution=regime_dist,
        )
        checkpoint_path = self.persistence.save_checkpoint(checkpoint)

        # Update state
        self._last_train_count = len(trades_df)
        self._last_accuracy = train_result.get("accuracy", 0)

        return {
            "success": True,
            "version": version,
            "model_path": str(model_path),
            "checkpoint_path": str(checkpoint_path),
            "accuracy": train_result.get("accuracy"),
            "train_samples": train_result.get("train_samples"),
            "model_type": train_result.get("model_type"),
        }

    def get_training_history(self) -> pd.DataFrame:
        """Get training history from checkpoints."""
        checkpoints = self.persistence.list_checkpoints()
        if not checkpoints:
            return pd.DataFrame()

        return pd.DataFrame([{
            "version": c.version,
            "timestamp": c.timestamp,
            "train_samples": c.train_samples,
            "accuracy": c.accuracy,
        } for c in checkpoints])

    def get_drift_status(self) -> dict[str, Any]:
        """Get current drift detection status."""
        return self.persistence.get_drift_report()
