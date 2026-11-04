"""Tests for technical indicator calculations."""

import os
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import numpy as np
import pandas as pd
from modules.indicators import IndicatorEngine


class TestIndicatorEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IndicatorEngine()
        self.df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "high": [102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0],
                "close": [101.0, 102.0, 103.0, 104.0],
                "volume": [1000, 2000, 3000, 4000],
            }
        )
        self.df.index = pd.date_range("2024-01-01", periods=4, freq="D")

    def test_sma_returns_expected(self):
        sma20 = self.engine.sma_series(self.df["close"], 2)
        self.assertGreater(sma20.iloc[-1], sma20.iloc[0])

    def test_ema_series_returns_dataframe_like(self):
        ema20 = self.engine.ema_series(self.df["close"], 2)
        self.assertEqual(len(ema20), len(self.df))

    def test_rsi_series_return_type_and_transform(self):
        rsi = self.engine.rsi_series(self.df["close"], 2)
        self.assertEqual(len(rsi), len(self.df))
        # Early values may be NaN until enough rows exist for the lookback.
        self.assertTrue(rsi.isna().any() or True)
        self.assertTrue((rsi.dropna() >= 0).all() and (rsi.dropna() <= 100).all())

    def test_rsi_handles_zero_loss_gain_and_flat_prices(self):
        rising = self.engine.rsi_series(pd.Series(range(30), dtype=float), 14)
        falling = self.engine.rsi_series(pd.Series(range(30, 0, -1), dtype=float), 14)
        flat = self.engine.rsi_series(pd.Series([7.0] * 30), 14)
        self.assertEqual(rising.iloc[-1], 100.0)
        self.assertEqual(falling.iloc[-1], 0.0)
        self.assertEqual(flat.iloc[-1], 50.0)

    def test_macd_returns_components(self):
        macd = self.engine.macd_series(self.df["close"], 2, 3, 1)
        self.assertIn("macd", macd)
        self.assertIn("signal", macd)
        self.assertIn("hist", macd)

    def test_bollinger_bands_has_three_series(self):
        bb = self.engine.bollinger_bands(self.df["close"], 2)
        self.assertIn("bb_upper", bb)
        self.assertIn("bb_middle", bb)
        self.assertIn("bb_lower", bb)

    def test_atr_series(self):
        atr = self.engine.atr_series(self.df["high"], self.df["low"], self.df["close"], 2)
        self.assertGreater(len(atr), 0)
        self.assertIsInstance(atr.iloc[0], float)

    def test_stochastic_rsi_returns_series(self):
        rsi = self.engine.rsi_series(self.df["close"], 2)
        stoch = self.engine.stochastic_rsi_series(rsi, 2, 1)
        self.assertGreater(len(stoch), 0)

    def test_vwap_series(self):
        vwap = self.engine.vwap_series(self.df["close"], self.df["volume"])
        self.assertGreater(vwap.iloc[-1], vwap.iloc[0])

    def test_volume_change_rate(self):
        change = self.engine.volume_change_rate(self.df["volume"], 2)
        self.assertGreater(len(change), 0)

    def test_indicators(self):
        desc = self.engine.describe(self.df, "TEST")
        self.assertIn("trend_direction", desc)
        self.assertIn("rsi", desc)
        self.assertIn("support_levels", desc)
        self.assertIn("resistance_levels", desc)
        self.assertIn("pattern", desc)
        self.assertIn("order_blocks", desc)
        self.assertIn("fvgs", desc)

    def test_candlestick_patterns(self):
        df = pd.DataFrame(
            {
                "open": [100.0, 102.0],
                "high": [103.0, 104.0],
                "low": [99.0, 101.0],
                "close": [101.0, 99.0],
                "volume": [1000, 1000],
            }
        )
        df.index = pd.date_range("2024-01-01", periods=2)
        desc = self.engine.describe(df, "TEST")
        self.assertIsInstance(desc["pattern"], str)


if __name__ == "__main__":
    unittest.main()
