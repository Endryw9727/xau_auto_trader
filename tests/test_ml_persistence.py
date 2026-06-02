"""Tests for ML persistence and continuous training."""
import pandas as pd
import pytest

from src.ml.model_persistence import ModelPersistence, ModelCheckpoint
from src.ml.continuous_trainer import ContinuousTrainer, RetrainTrigger


def test_model_persistence_init():
    mp = ModelPersistence()
    assert mp.model_dir.exists()
    assert mp.checkpoint_dir.exists()


def test_model_checkpoint_creation():
    cp = ModelCheckpoint(
        version="v1",
        timestamp="2026-01-01T00:00:00",
        train_samples=100,
        accuracy=0.65,
        feature_importance={"risk_reward": 0.3},
        regime_distribution={"TRENDING_UP": 50},
    )
    assert cp.version == "v1"
    assert cp.accuracy == 0.65


def test_continuous_trainer_init():
    ct = ContinuousTrainer()
    assert ct.retrain_threshold == 50
    assert ct.performance_drop_threshold == 0.15


def test_should_retrain_count_threshold():
    ct = ContinuousTrainer(retrain_threshold=10)
    df = pd.DataFrame({
        "risk_reward": [2.0]*15,
        "macro_score": [0.1]*15,
        "outcome": [10.0]*15,
        "session": ["London"]*15,
    })
    trigger = ct._should_retrain(df)
    assert trigger.triggered is True
    assert "New trades threshold" in trigger.reason


def test_should_not_retrain():
    ct = ContinuousTrainer(retrain_threshold=100)
    df = pd.DataFrame({
        "risk_reward": [2.0]*5,
        "macro_score": [0.1]*5,
        "outcome": [10.0]*5,
        "session": ["London"]*5,
    })
    trigger = ct._should_retrain(df)
    assert trigger.triggered is False


def test_retrain_insufficient_trades():
    ct = ContinuousTrainer()
    df = pd.DataFrame()
    result = ct.check_and_retrain(df)
    assert result["retrained"] is False
    assert "Insufficient" in result["reason"]


def test_drift_report_insufficient():
    mp = ModelPersistence()
    report = mp.get_drift_report()
    assert report["status"] == "insufficient_data"
