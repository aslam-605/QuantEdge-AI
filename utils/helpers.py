"""Utility helpers for QuantEdge AI."""

import time
from typing import Any, Callable, Dict, Optional


def get_utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def utc_now_iso() -> str:
    return get_utc_now_iso()


def sanitize_symbol(symbol: Optional[str]) -> str:
    """Normalise a user-entered symbol to a safe NSE-style string."""
    if not symbol:
        return ""
    cleaned = str(symbol).strip().upper()
    cleaned = cleaned.replace("NSE:", "").replace(".NS", "").replace(".BO", "")
    return cleaned.strip()


def is_valid_symbol_name(symbol: str) -> bool:
    """Very small validator for NSE-style symbols."""
    if not symbol:
        return False
    if any(ch.isspace() for ch in symbol):
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789^.-_")
    return all(ch in allowed for ch in symbol)


class StCache:
    """Tiny in-memory Streamlit-friendly cache that evicts by time."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[str, tuple[float, Any]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        record = self._store.get(key)
        if record is None:
            return default
        value, expiry = record
        if time.monotonic() > expiry:
            self._store.pop(key, None)
            return default
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        self._store[key] = (value, time.monotonic() + max(0.0, ttl))

    def set_ttl(self, ttl_seconds: float) -> None:
        self._ttl = max(0.0, float(ttl_seconds))
        self.clear()

    def clear(self) -> None:
        self._store.clear()
