"""
Model persistence for ML trade predictor.

Handles saving/loading trained models, feature history,
and drift detection checkpoints.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

MODEL_DIR = Path("data/models")
CHECKPOINT_DIR = Path("data/models/checkpoints")

@dataclass(frozen=True)
class ModelCheckpoint:
    """A saved model checkpoint."""

    version: str
    timestamp: str
    train_samples: int
    accuracy: float
    feature_importance: dict[str, float]
    regime_distribution: dict[str, int]

class ModelPersistence:
    """Handles model save/load and versioning."""

    def __init__(self, model_dir: Path = MODEL_DIR):
        self.model_dir = model_dir
        self.checkpoint_dir = CHECKPOINT_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_model(self, predictor, metadata: dict[str, Any]) -> Path:
        """Save a trained model with metadata."""
        version = metadata.get("version", "v1")
        timestamp = metadata.get("timestamp", pd.Timestamp.now().isoformat())

        model_path = self.model_dir / f"predictor_{version}.pkl"
        meta_path = self.model_dir / f"predictor_{version}_meta.json"

        with open(model_path, "wb") as f:
            pickle.dump(predictor, f)

        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2, default=str)

        return model_path

    def load_model(self, version: str = "latest") -> tuple[Any, dict]:
        """Load a saved model and its metadata."""
        if version == "latest":
            # Find latest version
            models = sorted(self.model_dir.glob("predictor_v*.pkl"))
            if not models:
                raise FileNotFoundError("No saved models found")
            model_path = models[-1]
            version = model_path.stem.replace("predictor_", "")
        else:
            model_path = self.model_dir / f"predictor_{version}.pkl"

        meta_path = self.model_dir / f"predictor_{version}_meta.json"

        with open(model_path, "rb") as f:
            predictor = pickle.load(f)

        metadata = {}
        if meta_path.exists():
            with open(meta_path, "r") as f:
                metadata = json.load(f)

        return predictor, metadata

    def save_checkpoint(self, checkpoint: ModelCheckpoint) -> Path:
        """Save a training checkpoint."""
        path = self.checkpoint_dir / f"checkpoint_{checkpoint.version}_{checkpoint.timestamp.replace(':', '-')}.json"
        with open(path, "w") as f:
            json.dump({
                "version": checkpoint.version,
                "timestamp": checkpoint.timestamp,
                "train_samples": checkpoint.train_samples,
                "accuracy": checkpoint.accuracy,
                "feature_importance": checkpoint.feature_importance,
                "regime_distribution": checkpoint.regime_distribution,
            }, f, indent=2)
        return path

    def list_checkpoints(self) -> list[ModelCheckpoint]:
        """List all saved checkpoints."""
        checkpoints = []
        for path in self.checkpoint_dir.glob("checkpoint_*.json"):
            with open(path, "r") as f:
                data = json.load(f)
            checkpoints.append(ModelCheckpoint(**data))
        return sorted(checkpoints, key=lambda c: c.timestamp)

    def get_drift_report(self, recent_window: int = 50) -> dict[str, Any]:
        """Generate model drift report from checkpoints."""
        checkpoints = self.list_checkpoints()
        if len(checkpoints) < 2:
            return {"status": "insufficient_data", "message": "Need at least 2 checkpoints"}

        recent = checkpoints[-recent_window:]
        accuracies = [c.accuracy for c in recent]

        return {
            "status": "ok",
            "checkpoints_count": len(checkpoints),
            "recent_window": len(recent),
            "accuracy_trend": "declining" if accuracies[-1] < accuracies[0] * 0.9 else "stable",
            "latest_accuracy": accuracies[-1],
            "earliest_accuracy": accuracies[0],
            "accuracy_change_pct": round((accuracies[-1] - accuracies[0]) / accuracies[0] * 100, 2) if accuracies[0] > 0 else 0,
        }
