"""Tests for ML modules."""
import pandas as pd
import pytest

from src.ml.trade_features import build_feature_matrix, extract_features_from_trade_row
from src.ml.trade_predictor import TradePredictor, PredictionResult
from src.ml.regime_detector import detect_regime


def test_extract_features():
    row = pd.Series({
        "risk_reward": 2.5,
        "macro_score": 0.3,
        "smc_score": 0.6,
        "outcome": 15.0,
        "session": "London",
    })
    features = extract_features_from_trade_row(row)
    assert features["risk_reward"] == 2.5
    assert features["won"] == 1
    assert features["session_london"] == 1


def test_build_feature_matrix():
    df = pd.DataFrame({
        "risk_reward": [2.0, 1.5, 3.0],
        "macro_score": [0.1, -0.2, 0.5],
        "outcome": [10.0, -5.0, 20.0],
        "session": ["London", "Asia", "New York"],
    })
    X, y = build_feature_matrix(df)
    assert len(X) == 3
    assert len(y) == 3
    assert "risk_reward" in X.columns


def test_predictor_train_mock():
    df = pd.DataFrame({
        "risk_reward": [2.0]*20 + [3.0]*20,
        "macro_score": [0.1]*20 + [0.5]*20,
        "outcome": [10.0]*25 + [-5.0]*15,
        "session": ["London"]*40,
    })
    predictor = TradePredictor(model_type="heuristic")
    result = predictor.train(df)
    assert "error" not in result
    assert predictor.is_trained is True


def test_predictor_predict():
    df = pd.DataFrame({
        "risk_reward": [2.0]*30,
        "macro_score": [0.1]*30,
        "outcome": [10.0]*20 + [-5.0]*10,
        "session": ["London"]*30,
    })
    predictor = TradePredictor(model_type="heuristic")
    predictor.train(df)

    setup = {"risk_reward": 2.5, "macro_score": 0.3, "smc_score": 0.5}
    pred = predictor.predict(setup)
    assert isinstance(pred, PredictionResult)
    assert 0 <= pred.probability <= 1


def test_regime_detector_trending():
    prices = list(range(1, 101))
    df = pd.DataFrame({
        "Open": [p - 0.5 for p in prices],
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": prices,
        "Volume": [1000]*100,
    })
    regime = detect_regime(df, lookback=50)
    assert regime.regime in {"TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "LOW_VOLATILITY"}
    assert regime.adx >= 0


def test_regime_detector_empty():
    df = pd.DataFrame()
    regime = detect_regime(df)
    assert regime.regime == "RANGING"
