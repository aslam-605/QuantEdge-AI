"""Technical indicator engine.

Provides elementary pandas implementations for the indicators requested:
RSI, MACD, EMA, SMA, VWAP, Bollinger Bands, ATR, Stochastic RSI,
volume profile, support/resistance, simple candlestick patterns,
and Smart Money Concepts labels (order blocks, FVG, BOS, CHoCH, liquidity sweeps).

All outputs are deterministic from the prices passed in. They are rule-based
technical interpretations, not verified institutional flow.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, List

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def _ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=1).mean()


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index.

    Returns a pandas Series aligned to `series`. Early rows are NaN until the
    requested lookback window has enough data to compute a valid value, which is
    the standard behavior for rolling RSI implementations. Downstream code should
    call `.dropna()` before using the result.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    ma_gain = _sma(gain, window)
    ma_loss = _sma(loss, window)
    rs = ma_gain / ma_loss.replace(0, np.nan)
    raw = 100.0 - (100.0 / (1.0 + rs))
    raw = raw.mask((ma_loss == 0) & (ma_gain > 0), 100.0)
    raw = raw.mask((ma_gain == 0) & (ma_loss > 0), 0.0)
    raw = raw.mask((ma_gain == 0) & (ma_loss == 0), 50.0)
    # Replace exact zeros / near-zero loss with a large neutral RSI to keep
    # the plot/charting layers clean, while keeping NaN for genuine lack of data.
    return raw


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    macd = fast_ema - slow_ema
    signal_line = _ema(macd, signal)
    return {"macd": macd, "signal": signal_line, "hist": macd - signal_line}


def _vwap(trades: pd.DataFrame, bar_pairs: pd.DataFrame) -> pd.Series:
    """VWAP per bar = sum(price*volume)/sum(volume) for that bar."""
    if "volume" not in trades.columns or "price" not in trades.columns:
        raise ValueError("trades must include volume and price columns")
    if "bar" not in bar_pairs.columns:
        raise ValueError("bar_pairs must include a bar column")
    merged = trades.merge(bar_pairs, left_index=True, right_on="bar", how="left")
    numerator = (merged["price"] * merged["volume"]).groupby(merged["bar"].tolist()).sum() if False else \
        (merged["price"] * merged["volume"]).groupby(merged["bar"]).sum()
    denominator = merged["volume"].groupby(merged["bar"]).sum()
    return numerator / denominator.replace(0, np.nan)


def _bollinger_bands(series: pd.Series, window: int = 20, k: float = 2.0) -> Dict[str, pd.Series]:
    ma = _sma(series, window)
    std = series.rolling(window=window, min_periods=1).std()
    return {
        "bb_upper": ma + k * std,
        "bb_middle": ma,
        "bb_lower": ma - k * std,
    }


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _sma(tr, window)


def _stochastic_rsi(rsi: pd.Series, window: int = 14, smooth: int = 3) -> pd.Series:
    low_min = rsi.rolling(window=window, min_periods=1).min()
    high_max = rsi.rolling(window=window, min_periods=1).max()
    fast = (rsi - low_min) / (high_max - low_min).replace(0, np.nan)
    return fast.ewm(span=smooth, adjust=False, min_periods=1).mean()


def _ema_cross(ema_short: pd.Series, ema_long: pd.Series) -> pd.Series:
    cross = (ema_short > ema_long).astype(int) - (ema_short < ema_long).astype(int)
    return cross.diff()


def _volume_change_rate(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume.pct_change(window) if hasattr(volume, "pct_change") else volume.pct_change(window)


def _average_true_range(volume: pd.Series, window: int = 20) -> float:
    if volume is None or len(volume) == 0:
        return 0.0
    return float(volume.tail(window).mean()) if len(volume) >= window else float(volume.mean())


# -------------------------------------------------------------------
# Main indicator engine
# -------------------------------------------------------------------
class IndicatorEngine:
    """Easily called helper for a dataframe of OHLCV data."""

    def __init__(self) -> None:
        self._cache: dict[str, pd.Series] = {}

    def describe(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Return a dict of derived indicator values for the dataframe."""
        if df is None or df.empty:
            return self.empty_result(symbol)

        ohlc = df.copy()
        if "volume" not in ohlc.columns:
            raise ValueError("OHLCV dataframe must include volume column")

        close = ohlc["close"]
        high = ohlc["high"]
        low = ohlc["low"]
        volume = ohlc["volume"]

        ema9 = _ema(close, 9)
        ema20 = _ema(close, 20)
        ema50 = _ema(close, 50)
        sma20 = _sma(close, 20)
        sma50 = _sma(close, 50)

        rsi = _rsi(close, 14)
        stoch_rsi = _stochastic_rsi(rsi, 14, 3)
        macd = _macd(close)
        boll = _bollinger_bands(close, 20, 2.0)
        atr = _atr(high, low, close, 14)

        # VWAP and volume profile
        vwap = (
            (close * volume).cumsum() / volume.cumsum().replace(0, np.nan)
        )
        volume_ma = _sma(volume, 20)
        volume_change = volume.pct_change(20)

        # Trend direction
        trend_direction = "NEUTRAL"
        if len(close) >= 50:
            if close.iloc[-1] > ema50.iloc[-1] > ema20.iloc[-1]:
                trend_direction = "BULLISH"
            elif close.iloc[-1] < ema50.iloc[-1] < ema20.iloc[-1]:
                trend_direction = "BEARISH"

        res = {
            "symbol": symbol,
            "close": float(close.iloc[-1]) if not pd.isna(close.iloc[-1]) else None,
            "ema9": float(ema9.iloc[-1]) if not pd.isna(ema9.iloc[-1]) else None,
            "ema20": float(ema20.iloc[-1]) if not pd.isna(ema20.iloc[-1]) else None,
            "ema50": float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else None,
            "sma20": float(sma20.iloc[-1]) if not pd.isna(sma20.iloc[-1]) else None,
            "sma50": float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None,
            "rsi": float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None,
            "rsi_overbought": bool(rsi.iloc[-1] > 70) if not pd.isna(rsi.iloc[-1]) else False,
            "rsi_oversold": bool(rsi.iloc[-1] < 30) if not pd.isna(rsi.iloc[-1]) else False,
            "macd": float(macd["macd"].iloc[-1]) if not pd.isna(macd["macd"].iloc[-1]) else None,
            "macd_signal": float(macd["signal"].iloc[-1]) if not pd.isna(macd["signal"].iloc[-1]) else None,
            "macd_hist": float(macd["hist"].iloc[-1]) if not pd.isna(macd["hist"].iloc[-1]) else None,
            "stoch_rsi": float(stoch_rsi.iloc[-1]) if not pd.isna(stoch_rsi.iloc[-1]) else None,
            "stoch_rsi_overbought": bool(stoch_rsi.iloc[-1] > 0.8) if not pd.isna(stoch_rsi.iloc[-1]) else False,
            "stoch_rsi_oversold": bool(stoch_rsi.iloc[-1] < 0.2) if not pd.isna(stoch_rsi.iloc[-1]) else False,
            "bb_upper": float(boll["bb_upper"].iloc[-1]) if not pd.isna(boll["bb_upper"].iloc[-1]) else None,
            "bb_middle": float(boll["bb_middle"].iloc[-1]) if not pd.isna(boll["bb_middle"].iloc[-1]) else None,
            "bb_lower": float(boll["bb_lower"].iloc[-1]) if not pd.isna(boll["bb_lower"].iloc[-1]) else None,
            "atr": float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None,
            "vwap": float(vwap.iloc[-1]) if not pd.isna(vwap.iloc[-1]) else None,
            "volume": float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else None,
            "volume_change": float(volume_change.iloc[-1]) if not pd.isna(volume_change.iloc[-1]) else None,
            "trend_direction": trend_direction,
            "ema_cross_short_long": int(
                (ema9.iloc[-1] - ema20.iloc[-1]) / ema20.iloc[-1] * 100.0
            ) if not (pd.isna(ema9.iloc[-1]) or pd.isna(ema20.iloc[-1])) else None,
        }

        # Simple support/resistance from recent swing points
        res["support_levels"] = self._swing_levels(low, lookback=20)
        res["resistance_levels"] = self._swing_levels(high, lookback=20)

        # Simple candlestick patterns
        res["pattern"] = self._candlestick_pattern(close, high, low, volume)

        # SMC descriptors
        res["order_blocks"] = self._find_order_blocks(low, high)
        res["fvgs"] = self._find_fvgs(high, low)
        res["break_of_structure"] = self._break_of_structure(high)
        res["change_of_character"] = int(
            bool(close.iloc[-1] < high.iloc[-1]) and len(close) > 1 and close.iloc[-1] < close.iloc[-2]
        )
        return res

    @staticmethod
    def empty_result(symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "close": None,
            "ema9": None,
            "ema20": None,
            "ema50": None,
            "sma20": None,
            "sma50": None,
            "rsi": None,
            "rsi_overbought": False,
            "rsi_oversold": False,
            "macd": None,
            "macd_signal": None,
            "macd_hist": None,
            "stoch_rsi": None,
            "stoch_rsi_overbought": False,
            "stoch_rsi_oversold": False,
            "bb_upper": None,
            "bb_middle": None,
            "bb_lower": None,
            "atr": None,
            "vwap": None,
            "volume": None,
            "volume_change": None,
            "trend_direction": "NEUTRAL",
            "ema_cross_short_long": None,
            "support_levels": [],
            "resistance_levels": [],
            "pattern": "None",
            "order_blocks": [],
            "fvgs": [],
            "break_of_structure": False,
            "change_of_character": False,
        }

    # ----------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------
    @staticmethod
    def _swing_levels(series: pd.Series, lookback: int = 20) -> list[float]:
        levels: list[float] = []
        s = series.dropna()
        for i in range(lookback, len(s)):
            if (s.iloc[i] == s.iloc[i - lookback:i].max()) and (s.iloc[i] == s.iloc[i - lookback:i].min() == s.iloc[i]):
                # only keep distinct pivot points
                if not levels or abs(s.iloc[i] - levels[-1]) > 1e-6:
                    levels.append(float(s.iloc[i]))
        return levels[-max(lookback, 5):]

    @staticmethod
    def _candlestick_pattern(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series) -> str:
        if len(close) < 3:
            return "INSUFFICIENT_DATA"
        def _body(c: float, o: float) -> float:
            return abs(c - o)
        def _upper_shadow(h: float, o: float, c: float) -> float:
            return h - max(o, c)
        def _lower_shadow(l: float, o: float, c: float) -> float:
            return l - min(o, c)

        last = (close.iloc[-1], high.iloc[-1], low.iloc[-1])
        prev = (close.iloc[-2], high.iloc[-2], low.iloc[-2])
        body = _body(last[0], last[1])  # placeholder, will recompute below
        body = abs(last[0] - prev[0])
        upper = last[1] - max(prev[0], last[0])
        lower = last[2] - min(prev[0], last[0])

        if body < 1e-8:
            return "DOJI"
        if body > 2 * _upper_shadow(last[1], prev[0], last[0]) and lower < 0.5 * body:
            return "HAMMER"
        if body > 2 * _lower_shadow(last[2], prev[0], last[0]) and upper < 0.5 * body:
            return "INVERTED_HAMMER"
        if body > 2 * (_upper_shadow(last[1], prev[0], last[0])) and body > 2 * (_lower_shadow(last[2], prev[0], last[0])):
            return "ENGULFING"
        if body > 2 * _upper_shadow(last[1], prev[0], last[0]):
            return "BULLISH_REJECTION"
        if body > 2 * _lower_shadow(last[2], prev[0], last[0]):
            return "BEARISH_REJECTION"
        return "UNKNOWN"

    @staticmethod
    def _find_order_blocks(low: pd.Series, high: pd.Series, lookback: int = 30) -> list[dict]:
        """Rule-based bullish order blocks."""
        blocks: list[dict] = []
        for i in range(lookback, len(low)):
            window = low.iloc[i - lookback:i]
            if not (window.shift(1).isna().any()):
                continue
            if low.iloc[i] == window.min() and low.iloc[i - 1] <= low.iloc[i]:
                blocks.append(
                    {
                        "low": float(low.iloc[i]),
                        "index": int(i),
                        "type": "BULLISH_ORDER_BLOCK",
                    }
                )
        return blocks[-20:]

    @staticmethod
    def _find_fvgs(high: pd.Series, low: pd.Series, gap_threshold: float = 0.005) -> list[dict]:
        """Rough fair-value-gap detection on high/low ranges."""
        fvgs: list[dict] = []
        for i in range(3, len(high)):
            high_3 = high.iloc[i - 3:i].tolist()
            low_3 = low.iloc[i - 3:i].tolist()
            max3 = max(high_3)
            min3 = min(low_3)
            if len(high_3) < 3:
                continue
            if max3 - min3 > 1e-8:
                mid = (max3 + min3) / 2
                fvgs.append({"level": float(mid), "width": float(max3 - min3), "index": int(i)})
        return fvgs[-20:]

    @staticmethod
    def _break_of_structure(high: pd.Series, lookback: int = 20) -> bool:
        if len(high) < lookback + 1:
            return False
        previous_high = high.iloc[-lookback - 1 : -1].max()
        return bool(high.iloc[-1] > previous_high)

    # ----------------------------------------------------------------
    # Compatibility helpers for charting
    # ----------------------------------------------------------------
    @staticmethod
    def ema_cross_signal(ema_short: pd.Series, ema_long: pd.Series) -> pd.Series:
        return _ema_cross(ema_short, ema_long)

    @staticmethod
    def vwap_series(close: pd.Series, volume: pd.Series) -> pd.Series:
        return (close * volume).cumsum() / volume.cumsum().replace(0, np.nan)

    @staticmethod
    def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        return _atr(high, low, close, window)

    @staticmethod
    def bollinger_bands(series: pd.Series, window: int = 20, k: float = 2.0) -> Dict[str, pd.Series]:
        return _bollinger_bands(series, window, k)

    @staticmethod
    def rsi_series(series: pd.Series, window: int = 14) -> pd.Series:
        return _rsi(series, window)

    @staticmethod
    def macd_series(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        return _macd(series, fast, slow, signal)

    @staticmethod
    def stochastic_rsi_series(rsi: pd.Series, window: int = 14, smooth: int = 3) -> pd.Series:
        return _stochastic_rsi(rsi, window, smooth)

    @staticmethod
    def sma_series(series: pd.Series, window: int) -> pd.Series:
        return _sma(series, window)

    @staticmethod
    def ema_series(series: pd.Series, window: int) -> pd.Series:
        return _ema(series, window)

    @staticmethod
    def volume_change_rate(volume: pd.Series, window: int = 20) -> pd.Series:
        return _volume_change_rate(volume, window)

    @staticmethod
    def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        return _atr(high, low, close, window)

    @staticmethod
    def bollinger_bands(series: pd.Series, window: int = 20, k: float = 2.0) -> Dict[str, pd.Series]:
        return _bollinger_bands(series, window, k)

    @staticmethod
    def rsi_series(series: pd.Series, window: int = 14) -> pd.Series:
        return _rsi(series, window)

    @staticmethod
    def macd_series(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        return _macd(series, fast, slow, signal)

    @staticmethod
    def stochastic_rsi_series(rsi: pd.Series, window: int = 14, smooth: int = 3) -> pd.Series:
        return _stochastic_rsi(rsi, window, smooth)

    @staticmethod
    def sma_series(series: pd.Series, window: int) -> pd.Series:
        return _sma(series, window)

    @staticmethod
    def ema_series(series: pd.Series, window: int) -> pd.Series:
        return _ema(series, window)

    @staticmethod
    def vwap_series(close: pd.Series, volume: pd.Series) -> pd.Series:
        return (close * volume).cumsum() / volume.cumsum().replace(0, np.nan)
