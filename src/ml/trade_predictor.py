"""
Trade outcome predictor using simple ML.

Uses scikit-learn if available, otherwise falls back to weighted heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.ml.trade_features import build_feature_matrix, extract_features_from_trade_row

SKLEARN_AVAILABLE = False
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    SKLEARN_AVAILABLE = True
except ImportError:
    pass

@dataclass(frozen=True)
class PredictionResult:
    will_win: bool
    probability: float
    confidence: str
    model_type: str
    feature_importance: dict[str, float] | None


class TradePredictor:
    def __init__(self, model_type: str = "auto"):
        self.model_type = model_type
        self.model = None
        self.is_trained = False
        self.feature_names: list[str] = []
        self._heuristic_weights = {
            "risk_reward": 0.20,
            "macro_score": 0.15,
            "smc_score": 0.15,
            "adx_at_entry": 0.10,
            "rsi_at_entry": 0.10,
            "trend_aligned": 0.10,
            "fvg_aligned": 0.05,
            "ob_nearby": 0.05,
            "sweep_confirmed": 0.05,
            "session_london": 0.03,
            "session_ny": 0.02,
        }

    def train(self, trades_df: pd.DataFrame) -> dict[str, Any]:
        if trades_df.empty or len(trades_df) < 10:
            return {"error": "Need at least 10 trades to train"}

        X, y = build_feature_matrix(trades_df)
        if X.empty:
            return {"error": "No valid features extracted"}

        self.feature_names = list(X.columns)

        if SKLEARN_AVAILABLE and self.model_type in ("auto", "sklearn"):
            return self._train_sklearn(X, y)
        else:
            return self._train_heuristic(X, y)

    def _train_sklearn(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42,
            stratify=y if len(y.unique()) > 1 else None
        )
        self.model = RandomForestClassifier(
            n_estimators=100, max_depth=5, min_samples_split=5,
            random_state=42, class_weight="balanced",
        )
        self.model.fit(X_train, y_train)
        self.is_trained = True
        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        importance = dict(zip(X.columns, self.model.feature_importances_))
        return {
            "model_type": "sklearn_random_forest",
            "accuracy": round(accuracy, 3),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "feature_importance": {k: round(v, 3) for k, v in sorted(importance.items(), key=lambda x: -x[1])},
        }

    def _train_heuristic(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        self.is_trained = True
        win_rate = y.mean()
        return {
            "model_type": "heuristic_weighted",
            "accuracy": round(win_rate, 3),
            "train_samples": len(X),
            "win_rate": round(win_rate, 3),
            "feature_importance": self._heuristic_weights,
        }

    def predict(self, trade_setup: dict[str, Any]) -> PredictionResult:
        if not self.is_trained:
            return PredictionResult(False, 0.5, "LOW", "untrained", None)

        if SKLEARN_AVAILABLE and self.model_type in ("auto", "sklearn") and self.model is not None:
            return self._predict_sklearn(trade_setup)
        else:
            return self._predict_heuristic(trade_setup)

    def _predict_sklearn(self, trade_setup: dict[str, Any]) -> PredictionResult:
        features = extract_features_from_trade_row(pd.Series(trade_setup))
        X = pd.DataFrame([{k: features.get(k, 0) for k in self.feature_names}])
        proba = self.model.predict_proba(X)[0]
        win_prob = proba[1] if len(proba) > 1 else proba[0]
        confidence = "HIGH" if max(proba) > 0.7 else ("MEDIUM" if max(proba) > 0.55 else "LOW")
        importance = dict(zip(self.feature_names, self.model.feature_importances_))
        return PredictionResult(
            will_win=win_prob > 0.5,
            probability=round(win_prob, 3),
            confidence=confidence,
            model_type="sklearn",
            feature_importance={k: round(v, 3) for k, v in sorted(importance.items(), key=lambda x: -x[1])[:5]},
        )

    def _predict_heuristic(self, trade_setup: dict[str, Any]) -> PredictionResult:
        features = extract_features_from_trade_row(pd.Series(trade_setup))
        score = 0.0
        total_weight = 0.0
        for feature, weight in self._heuristic_weights.items():
            value = features.get(feature, 0)
            if feature == "risk_reward":
                normalized = min(1.0, value / 3.0)
            elif feature in ("macro_score", "smc_score"):
                normalized = abs(value)
            elif feature == "adx_at_entry":
                normalized = min(1.0, value / 40.0)
            elif feature == "rsi_at_entry":
                normalized = 1.0 - abs(value - 50) / 50.0
            elif feature in ("fvg_aligned", "ob_nearby", "sweep_confirmed", "trend_aligned"):
                normalized = float(value)
            elif feature in ("session_london", "session_ny"):
                normalized = float(value)
            else:
                normalized = 0.5
            score += normalized * weight
            total_weight += weight

        probability = score / total_weight if total_weight > 0 else 0.5
        confidence = "HIGH" if probability > 0.7 or probability < 0.3 else ("MEDIUM" if probability > 0.6 or probability < 0.4 else "LOW")
        return PredictionResult(
            will_win=probability > 0.5,
            probability=round(probability, 3),
            confidence=confidence,
            model_type="heuristic",
            feature_importance=dict(sorted(self._heuristic_weights.items(), key=lambda x: -x[1])[:5]),
        )
