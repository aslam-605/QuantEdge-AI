"""Prediction rendering helpers for pages."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def format_probability(label: str, value: float) -> str:
    return f"{label}: {value * 100:.1f}%"


def classify_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("available"):
        return {
            "label": "No prediction",
            "class": "NEUTRAL",
            "probabilities": {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0},
            "model_stats": {"accuracy": None, "precision": None, "recall": None, "f1": None},
            "trained_at": None,
            "data_period": None,
        }
    return {
        "label": "ML Prediction",
        "class": result.get("class", "NEUTRAL"),
        "probabilities": result.get("probabilities", {}),
        "model_stats": result.get("metadata", {}).get("metrics", {}),
        "trained_at": result.get("metadata", {}).get("training_timestamp"),
        "data_period": result.get("metadata", {}).get("training_start"),
    }
