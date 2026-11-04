"""Tests for ML model training and prediction pipeline."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import numpy as np
import pandas as pd
from modules.ml_model import MarketPredictionEngine


class TestMarketPredictionEngine(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        self.df = pd.DataFrame(
            {
                "open": 100 + np.random.randn(300).cumsum() * 0.5,
                "high": 100 + np.random.randn(300).cumsum() * 0.7,
                "low": 100 + np.random.randn(300).cumsum() * 0.3,
                "close": 100 + np.random.randn(300).cumsum() * 0.4,
                "volume": np.random.randint(500000, 2000000, 300),
            }
        )
        self.df.index = pd.date_range("2021-01-01", periods=300, freq="B")
        self.df = self.df.astype(float)
        self.engine = MarketPredictionEngine(
            lookback=30,
            lookahead_days=10,
            target_thresholds={"bear": -0.02, "bull": 0.02},
        )
        self._model_tempdir = tempfile.TemporaryDirectory()
        self.engine.model_dir = Path(self._model_tempdir.name)

    def tearDown(self):
        self._model_tempdir.cleanup()

    def test_build_dataset_returns_columns(self):
        X, y = self.engine.build_dataset(self.df)
        self.assertGreater(len(X), 0)
        self.assertEqual(len(X.columns), len(self.engine._make_features(self.df).columns))
        self.assertEqual(len(X), len(y))
        # The target column is created as a Series with a default integer name;
        # the meaningful values are the class labels.
        self.assertTrue(set(y.unique()).issubset({"BULLISH", "BEARISH", "NEUTRAL"}))

    def test_training_with_few_rows_fails(self):
        small = self.df.iloc[:150].copy()
        engine = MarketPredictionEngine(lookback=30, lookahead_days=10, target_thresholds={"bear": -0.02, "bull": 0.02})
        with self.assertRaises(ValueError):
            engine.train(small)

    def test_future_target_uses_only_future_prices(self):
        close = pd.Series([100.0, 110.0, 121.0, 133.1])
        result = self.engine._future_return(close, 1)
        self.assertAlmostEqual(result.iloc[0], 0.1)
        self.assertTrue(pd.isna(result.iloc[-1]))

    def test_model_save_and_load(self):
        meta = self.engine.train(self.df, verbose=False)
        path = meta["model_path"]
        self.assertTrue(Path(path).exists())
        self.assertEqual(Path(path).parent, Path(self._model_tempdir.name))
        self.engine.model = None
        self.engine.load_model(path)
        self.assertIsNotNone(self.engine.model)

    def test_predictions_during_train_and_after(self):
        meta = self.engine.train(self.df, verbose=True)
        self.assertIsNotNone(meta.get("metrics"))
        result = self.engine.predict(self.df)
        self.assertTrue(result.get("available"))
        self.assertIn(result.get("class"), ("BULLISH", "BEARISH", "NEUTRAL"))
        self.assertIn("probabilities", result)
        self.assertGreaterEqual(result["probabilities"]["NEUTRAL"], 0.0)

    def test_model_metadata_contains_required_fields(self):
        meta = self.engine.train(self.df, verbose=False)
        for key in [
            "trained_at",
            "training_start",
            "training_end",
            "rows_used",
            "target_thresholds",
            "lookahead_days",
            "model_type",
        ]:
            self.assertIn(key, meta)


if __name__ == "__main__":
    unittest.main()
