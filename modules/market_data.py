"""Market data engine for QuantEdge AI.

Provides normalised OHLCV plus quote utilities, yfinance-backed.
All sources fallback gracefully when a provider or symbol is unavailable.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from utils.helpers import StCache

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "NIFTY_FIN_SERVICE.NS": "FINNIFTY",
    "NIFTY_FIN_SERVICE.NS": "FINNIFTY",
    "RELIANCE.NS": "RELIANCE",
    "HDFCBANK.NS": "HDFC BANK",
    "ICICIBANK.NS": "ICICI BANK",
    "INFY.NS": "INFOSYS",
    "TCS.NS": "TCS",
    "SBIN.NS": "STATE BANK OF INDIA",
    "ITC.NS": "ITC",
}

# yfinance intraday intervals commonly supported.
INTRADAY_INTERVALS = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "7d", "1wk"]

# Columns a downstream page expects.
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Symbols required by the original project.
REQUIRED_INDICES = ["^NSEI", "^NSEBANK"]
REQUIRED_STOCKS = [
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "TCS.NS",
    "SBIN.NS",
    "ITC.NS",
]

# Cache TTL for market data frames.
CACHE_TTL_SECONDS = 30.0


class MarketDataEngine:
    """Re-usable market data module."""

    def __init__(self, cache_ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        self._cache = StCache(ttl_seconds=cache_ttl_seconds)
        self._load_failures: Dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                        #
    # ------------------------------------------------------------------ #
    def get_symbol_display_name(self, symbol: str) -> str:
        return DEFAULT_FEEDS.get(symbol, symbol.upper())

    def clear_cache(self) -> None:
        self._cache.clear()

    def set_cache_ttl(self, ttl_seconds: float) -> None:
        self._cache.set_ttl(ttl_seconds)

    def symbols_available(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Check which symbols can be fetched and how fresh the data is."""
        if symbols is None:
            symbols = list(DEFAULT_FEEDS)

        results = {}
        for symbol in symbols:
            df = self.download_ohlcv(
                symbol,
                start_date="2020-01-01",
                end_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                interval="1d",
            )
            if df is None or df.empty:
                results[symbol] = {"available": False, "status": "UNAVAILABLE"}
                continue

            latest_timestamp = self._timestamp_of(df)
            if latest_timestamp is None:
                results[symbol] = {"available": True, "status": "HISTORICAL"}
                continue

            status, age_seconds = self._freshness_status(latest_timestamp)

            results[symbol] = {
                "available": True,
                "status": status,
                "latest_timestamp": latest_timestamp.isoformat(),
                "age_seconds": age_seconds,
                "rows": int(len(df)),
            }
        return results

    def get_quotes(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Return the latest quote-ish information for a list of symbols."""
        if symbols is None:
            symbols = list(DEFAULT_FEEDS)

        quotes: Dict[str, Dict[str, Any]] = {}
        for symbol in symbols:
            df = self.download_ohlcv(
                symbol,
                start_date="2020-01-01",
                end_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                interval="1d",
            )
            if df is None or df.empty:
                quotes[symbol] = {
                    "available": False,
                    "status": "UNAVAILABLE",
                    "last_price": None,
                    "previous_close": None,
                    "change": None,
                    "change_percent": None,
                    "volume": None,
                    "source": "yfinance",
                    "timestamp": None,
                }
                continue

            latest = df.iloc[-1]
            previous_close = df.iloc[-2]["close"] if len(df) >= 2 else None

            current_price = None
            if pd.notna(latest["close"]):
                current_price = float(latest["close"])
            previous_close_value = None
            if pd.notna(previous_close):
                previous_close_value = float(previous_close)

            change = None
            change_percent = None
            if current_price is not None and previous_close_value is not None:
                change = current_price - previous_close_value
                if previous_close_value != 0:
                    change_percent = (change / previous_close_value) * 100.0

            timestamp = self._timestamp_of(df)
            status, age_seconds = self._freshness_status(timestamp)

            quotes[symbol] = {
                "available": True,
                "status": status,
                "last_price": current_price,
                "previous_close": previous_close_value,
                "change": change,
                "change_percent": change_percent,
                "volume": int(latest["volume"]) if pd.notna(latest["volume"]) else None,
                "source": "yfinance daily history",
                "timestamp": timestamp.isoformat() if timestamp is not None else None,
                "age_seconds": age_seconds,
            }
        return quotes

    def download_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> Optional[pd.DataFrame]:
        """Download OHLCV and normalise it."""
        symbol = symbol.strip().upper()
        cache_key = f"ohlcv:{symbol}:{interval}:{start_date}:{end_date}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        for attempt in range(max_retries):
            try:
                df = self._download_yfinance(symbol, start_date, end_date, interval)
                if df is None or df.empty:
                    self._remember_failure(symbol)
                    return None

                df = self._normalise(df)
                if df.empty:
                    self._remember_failure(symbol)
                    return None

                self._cache.set(cache_key, df)
                return df
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("yfinance fetch failed for %s (attempt %d/%d): %s", symbol, attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (attempt + 1))
        return None

    def download_intraday(
        self,
        symbol: str,
        interval: str = "5m",
        hours: int = 24,
    ) -> Optional[pd.DataFrame]:
        now = datetime.now(timezone.utc)
        end_date = now.strftime("%Y-%m-%d")
        start_date = (now - timedelta(hours=hours)).strftime("%Y-%m-%d")
        return self.download_ohlcv(symbol, start_date, end_date, interval)

    # ------------------------------------------------------------------ #
    # Internals                                                         #
    # ------------------------------------------------------------------ #
    def _download_yfinance(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
    ) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
        except Exception as exc:  # pragma: no cover - rare
            logger.warning("yfinance import failed: %s", exc)
            return None

        try:
            ticker = yf.Ticker(symbol)
            # history returns an empty frame when the symbol is not available.
            data = ticker.history(start=start_date, end=end_date, interval=interval)
            if data is None or data.empty:
                return None
            data.index.name = "date"
            df = data.copy()
            return df
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("yfinance ticker error: %s", exc)
            return None

    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        data = df.copy()
        cols = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        data = data.rename(columns=cols)
        for column in OHLCV_COLUMNS:
            if column not in data.columns:
                data[column] = None

        # Ensure numeric types.
        for column in OHLCV_COLUMNS:
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors="coerce")

        # Keep only relevant columns and drop rows without a usable close.
        data = data[[c for c in OHLCV_COLUMNS if c in data.columns]].copy()
        if "date" in data.index.names:
            data = data.reset_index()[["date"] + OHLCV_COLUMNS]
        if "date" in data.columns:
            data["date"] = pd.to_datetime(data["date"], errors="coerce", utc=True)
        data = data.dropna(subset=["date"])
        data = data.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        data = data.set_index("date").sort_index()
        return data

    @staticmethod
    def _timestamp_of(df: pd.DataFrame) -> Optional[datetime]:
        if df is None or df.empty:
            return None
        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            return idx.max().astimezone(timezone.utc).to_pydatetime()
        return idx.max().to_pydatetime()

    @staticmethod
    def _freshness_status(timestamp: Optional[datetime]) -> tuple[str, Optional[float]]:
        if timestamp is None:
            return "UNAVAILABLE", None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        if age_seconds < 0:
            return "UNKNOWN", age_seconds
        if age_seconds < 3600:
            return "DELAYED", age_seconds
        return "HISTORICAL", age_seconds

    def _remember_failure(self, symbol: str) -> None:
        self._load_failures[symbol] = time.monotonic() + 300.0


# Module level convenience instance.
market = MarketDataEngine()
