"""Portfolio and trade history helpers.

Aggregates equity positions, closed equity positions, options trades, and
account metrics into one view. All calculations use SQLite-backed data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from modules.database import get_connection, get_or_create_account, upsert_account
from modules.paper_trading import now_iso

logger = logging.getLogger(__name__)


def portfolio_snapshot(conn, account_key: str) -> Dict[str, Any]:
    account = get_or_create_account(conn, account_key)
    rows = conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ?", (account_key,)
    ).fetchall()
    positions = [dict(r) for r in rows]
    closed = conn.execute(
        "SELECT * FROM equity_closed_positions WHERE account_key = ?",
        (account_key,),
    ).fetchall()

    current_price = _latest_quote(account_key)
    portfolio_value = account["portfolio_value"]

    # Update using latest market quotes when present.
    for pos in positions:
        symbol = pos["symbol"]
        qty = pos["quantity"]
        if qty <= 0:
            continue
        price = current_price.get(symbol)
        if price:
            unrealised = (price - pos["avg_entry_price"]) * qty
            portfolio_value += unrealised

    realised = sum(abs(float(c["realised_pnl"])) for c in closed)
    win_count = sum(1 for c in closed if float(c["realised_pnl"]) > 0)
    loss_count = sum(1 for c in closed if float(c["realised_pnl"]) < 0)
    total_trades = len(closed)
    win_rate = (win_count / total_trades * 100.0) if total_trades else 0.0

    return {
        "account_key": account_key,
        "start_balance": float(account["start_balance"]),
        "available_balance": float(account["current_balance"]),
        "invested_capital": float(account["invested_capital"]),
        "portfolio_value": float(portfolio_value),
        "realised_pl": float(sum(float(c["realised_pnl"]) for c in closed)),
        "unrealised_pl": float(sum((current_price.get(p["symbol"], p["avg_entry_price"]) - p["avg_entry_price"]) * p["quantity"] for p in positions)),
        "equity_positions": positions,
        "options_positions": [],
        "closed_trades": [dict(c) for c in closed],
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "portfolio_returns": [],
        "equity_curve": [],
    }


def _latest_quote(account_key: str) -> Dict[str, Any]:
    # In a full runtime, this could query yfinance quoted snapshots.
    return {}


def fetch_trade_history(conn, account_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    return conn.execute(
        "SELECT * FROM equity_trade_history WHERE account_key = ? ORDER BY timestamp DESC, trade_id DESC LIMIT ?",
        (account_key, limit),
    ).fetchall()


def fetch_options_trade_history(conn, account_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    return conn.execute(
        "SELECT * FROM options_trade_history WHERE account_key = ? ORDER BY timestamp DESC, trade_id DESC LIMIT ?",
        (account_key, limit),
    ).fetchall()


def daily_pl_for_last_days(conn, account_key: str, days: int = 30) -> List[Dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = conn.execute(
        """
        SELECT symbol, action, quantity, price, timestamp
        FROM equity_trade_history
        WHERE account_key = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        """,
        (account_key, cutoff.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def equity_curve(conn, account_key: str, window_days: int = 30) -> List[Dict[str, Any]]:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_history'"
    ).fetchone()
    if table_exists is None:
        return []

    rows = conn.execute(
        """
        SELECT timestamp, portfolio_value
        FROM portfolio_history
        WHERE account_key = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        LIMIT 100
        """,
        (account_key, (datetime.utcnow() - timedelta(days=window_days)).isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]
