"""Validation helpers for QuantEdge AI."""

import re
from typing import Iterable, Set

NSE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,10}$")


def is_nse_symbol(value: str) -> bool:
    """Return True if value looks like a valid NSE symbol."""
    return bool(value) and bool(NSE_PATTERN.fullmatch(value))


def is_int(value: object, minimum: int = 1) -> bool:
    """Return True if value is an integer >= minimum."""
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return False
    return ivalue >= minimum


def is_float(value: object, minimum: float = 0.0) -> bool:
    """Return True if value is a non-negative number."""
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        return False
    return fvalue >= minimum


def in_range(value: object, low: float, high: float) -> bool:
    """Return True if a number is within [low, high]."""
    try:
        ivalue = float(value)
    except (TypeError, ValueError):
        return False
    return low <= ivalue <= high


def non_empty_string(value: object) -> bool:
    return bool(isinstance(value, str) and value.strip())


def list_special_characters(items: Iterable[str]) -> Set[str]:
    """Return a set of problematic characters found in a list of strings."""
    bad = set()
    for item in items:
        if not isinstance(item, str):
            bad.add(repr(item))
            continue
        for ch in item:
            if ch in ";\"'\\":
                bad.add(ch)
    return bad
