"""Machine learning prediction module.

Uses a Scikit-learn RandomForestClassifier with chronological train/test
splits and walk-forward validation. No future data leakage, no random
shuffling of time-series data, and no synthetic performance claims.
"""

from __future__ import annotations

import logging
import json
from sklearn.model_selection import TimeSeriesSplit
import joblib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from modules.indicators import IndicatorEngine

logger = logging.getLogger(__name__)

DEFAULT_TARGET_THRESHOLDS = {"bull": 0.03, "bear": -0.03}  # configurable
DEFAULT_LOOKAHEAD_DAYS = 5
MODEL_FILENAME = "quantedge_rf.joblib"
MAX_TRAIN_SAMPLES = 30000
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


class MarketPredictionEngine:
    """Train and predict with a small RandomForest.

    Targets are configurable thresholds around future returns:
    - bull if future_return > bull_threshold
    - bear if future_return < bear_threshold
    - neutral otherwise
    """

    def __init__(
        self,
        lookback: int = 60,
        target_thresholds: Dict[str, float] = None,
        lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
        max_samples: int = MAX_TRAIN_SAMPLES,
    ) -> None:
        self.lookback = lookback
        self.lookahead = max(1, int(lookahead_days))
        self.thresholds = target_thresholds or dict(DEFAULT_TARGET_THRESHOLDS)
        self.max_samples = max_samples
        self.engine = IndicatorEngine()
        self.model: Optional[RandomForestClassifier] = None
        self.metadata: Dict[str, Any] = {}
        self._feature_names: List[str] = []
        self.model_dir = MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def _future_return(self, close: pd.Series, frame: int) -> pd.Series:
        return close.shift(-frame).div(close).sub(1.0)

    def _make_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        data = df.copy()
        if "volume" in data.columns:
            volume = data["volume"]
        else:
            volume = pd.Series(index=data.index, dtype=float)
        close = data["close"]
        high = data["high"] if "high" in data.columns else close
        low = data["low"] if "low" in data.columns else close
        features = pd.DataFrame(index=data.index)

        features["ret_1"] = close.pct_change(1)
        features["ret_3"] = close.pct_change(3)
        features["vol_change"] = volume.pct_change(5).fillna(0.0)
        features["atr_14"] = self.engine.atr_series(high, low, close, 14)
        features["rsi_14"] = self.engine.rsi_series(close, 14)
        macd = self.engine.macd_series(close)
        features["macd"] = macd["macd"]
        features["ema_diff_9_20"] = (data["close"].ewm(span=9, adjust=False).mean() -
                                     data["close"].ewm(span=20, adjust=False).mean()).fillna(0.0)
        features["sma_diff_20_50"] = (self.engine.sma_series(close, 20) - self.engine.sma_series(close, 50)).fillna(0.0)
        features["price_position_boll"] = ((close - self.engine.bollinger_bands(close)["bb_lower"]) /
                                            (self.engine.bollinger_bands(close)["bb_upper"] - self.engine.bollinger_bands(close)["bb_lower"])).fillna(0.0)
        features["hl_range"] = ((high - low) / close).fillna(0.0)
        features["volume_ma_ratio"] = volume / self.engine.sma_series(volume, 20).replace(0, np.nan)

        features = features.replace([np.inf, -np.inf], np.nan)
        return features.dropna()

    def _make_target(self, df: pd.DataFrame) -> pd.Series:
        returns = self._future_return(df["close"], self.lookahead)
        bull = returns > self.thresholds["bull"]
        bear = returns < self.thresholds["bear"]
        target = pd.Series("NEUTRAL", index=returns.index, dtype="object")
        target[bull] = "BULLISH"
        target[bear] = "BEARISH"
        target[returns.isna()] = pd.NA
        return target

    def build_dataset(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        features = self._make_features(df)
        target = self._make_target(df)
        if features.empty:
            return features, target
        aligned_target = target.reindex(features.index).rename("target")
        combined = features.join(aligned_target).dropna(subset=["target"])
        return combined.drop(columns=["target"]), combined["target"]

    def train(
        self,
        df: pd.DataFrame,
        verbose: bool = False,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        if df is None or df.empty:
            raise ValueError("No market data available to train the model.")

        train = df.copy()
        # Cap samples to keep model lightweight
        if len(train) > self.max_samples:
            train = train.iloc[-self.max_samples:]
        if len(train) < 200:
            raise ValueError("Insufficient historical data for model training.")

        X, y = self.build_dataset(train)
        if X.empty or y.empty:
            raise ValueError("Could not build a training dataset from provided prices.")

        tscv = TimeSeriesSplit(n_splits=min(5, max(2, len(X) // 1000)), gap=self.lookahead)
        validation_targets = []
        validation_predictions = []
        for train_idx, test_idx in tscv.split(X):
            if len(test_idx) < 30:
                continue
            model = RandomForestClassifier(
                n_estimators=120, max_depth=8, min_samples_leaf=5, n_jobs=-1, random_state=42
            )
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            validation_targets.extend(y.iloc[test_idx].tolist())
            validation_predictions.extend(model.predict(X.iloc[test_idx]).tolist())

        if not validation_targets:
            raise ValueError("Not enough chronological samples for walk-forward evaluation.")

        self.model = RandomForestClassifier(
            n_estimators=120, max_depth=8, min_samples_leaf=5, n_jobs=-1, random_state=42
        )
        self.model.fit(X, y)
        self._feature_names = list(X.columns)
        walkforward_f1 = float(f1_score(validation_targets, validation_predictions, average="weighted", zero_division=0))
        labels = ["BEARISH", "BULLISH", "NEUTRAL"]
        metrics = {
            "accuracy": float(accuracy_score(validation_targets, validation_predictions)),
            "precision": float(precision_score(validation_targets, validation_predictions, average="weighted", zero_division=0)),
            "recall": float(recall_score(validation_targets, validation_predictions, average="weighted", zero_division=0)),
            "f1": walkforward_f1,
            "evaluation": "walk-forward out-of-sample",
        }

        self.metadata = {
            "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "model_type": "RandomForestClassifier",
            "features": self._feature_names,
            "target_thresholds": self.thresholds,
            "lookahead_days": self.lookahead,
            "training_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "training_start": str(X.index[0]) if len(X) else None,
            "training_end": str(X.index[-1]) if len(X) else None,
            "rows_used": int(len(X)),
            "walkforward_f1": walkforward_f1,
            "class_counts": {k: int(v) for k, v in y.value_counts().items()},
            "window": {"lookback": self.lookback, "lookahead": self.lookahead},
            "metrics": metrics,
            "confusion_matrix": confusion_matrix(validation_targets, validation_predictions, labels=labels).tolist(),
        }

        model_path = Path(save_path) if save_path else self.model_dir / MODEL_FILENAME
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, model_path)
        self.metadata["model_path"] = str(model_path)
        metadata_path = model_path.with_suffix(model_path.suffix + ".json")
        metadata_path.write_text(json.dumps(self.metadata, indent=2, default=str), encoding="utf-8")
        if verbose:
            logger.info("ML training metric summary: %s", metrics)
        return self.metadata

    def predict(self, df: pd.DataFrame) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        features = self._make_features(df)
        features = features.replace([np.inf, -np.inf], np.nan).dropna()
        if features.empty:
            return {
                "available": False,
                "class": None,
                "probabilities": {},
                "error": "No features available for prediction.",
            }
        # Align feature columns to model's expected names when request differs slightly
        X = features.reindex(columns=self._feature_names, fill_value=0.0)
        proba = self.model.predict_proba(X)
        classes = self.model.classes_
        latest_probabilities = proba[-1]
        probs = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}
        probs.update({str(c): float(p) for c, p in zip(classes, latest_probabilities)})
        prediction = self.model.predict(X)[-1]
        self.metadata["last_prediction_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        self.metadata["last_prediction_class"] = str(prediction)
        return {
            "available": True,
            "class": str(prediction),
            "probabilities": probs,
            "thresholds": self.thresholds,
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "metadata": self.metadata,
        }

    def predict_proba(self, df: pd.DataFrame) -> Dict[str, Any]:
        return self.predict(df)

    def save_model(self, path: Optional[str] = None) -> str:
        if self.model is None:
            raise RuntimeError("No model to save.")
        model_path = Path(path) if path else self.model_dir / MODEL_FILENAME
        joblib.dump(self.model, model_path)
        self.metadata["model_path"] = str(model_path)
        return str(model_path)

    def load_model(self, path: Optional[str] = None) -> "MarketPredictionEngine":
        model_path = Path(path) if path else self.model_dir / MODEL_FILENAME
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        self.model = joblib.load(model_path)
        self._feature_names = list(getattr(self.model, "feature_names_in_", []))
        metadata_path = model_path.with_suffix(model_path.suffix + ".json")
        if metadata_path.exists():
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self._feature_names = list(self.metadata.get("features", self._feature_names))
        return self
