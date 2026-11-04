"""SQLite persistence layer for QuantEdge AI.

Tables:
- paper_accounts
- equity_positions
- equity_closed_positions
- equity_trade_history
- options_positions
- options_closed_positions
- options_trade_history
- db_schema_version
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT UNIQUE NOT NULL,
    start_balance REAL NOT NULL DEFAULT 100000.0,
    current_balance REAL NOT NULL DEFAULT 100000.0,
    invested_capital REAL NOT NULL DEFAULT 0.0,
    portfolio_value REAL NOT NULL DEFAULT 100000.0,
    currency TEXT NOT NULL DEFAULT 'INR',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_positions (
    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price REAL NOT NULL DEFAULT 0.0,
    cost_basis REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_key, symbol)
);

CREATE TABLE IF NOT EXISTS equity_closed_positions (
    closed_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price REAL NOT NULL DEFAULT 0.0,
    exit_price REAL NOT NULL DEFAULT 0.0,
    realised_pnl REAL NOT NULL DEFAULT 0.0,
    closed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_trade_history (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0.0,
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0.0,
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_positions (
    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK(option_type IN ('CE','PE')),
    quantity INTEGER NOT NULL,
    entry_premium REAL NOT NULL DEFAULT 0.0,
    close_premium REAL NOT NULL DEFAULT 0.0,
    exit_price REAL NOT NULL DEFAULT 0.0,
    open_premium REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_key, underlying, expiry, strike, option_type)
);

CREATE TABLE IF NOT EXISTS options_closed_positions (
    closed_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK(option_type IN ('CE','PE')),
    quantity INTEGER NOT NULL,
    entry_premium REAL NOT NULL DEFAULT 0.0,
    exit_premium REAL NOT NULL DEFAULT 0.0,
    realised_pnl REAL NOT NULL DEFAULT 0.0,
    closed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_trade_history (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK(option_type IN ('CE','PE')),
    action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
    quantity INTEGER NOT NULL,
    premium REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0.0,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS db_schema_version (
    version INTEGER PRIMARY KEY NOT NULL
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='db_schema_version'"
    ).fetchone()
    if table_exists is None:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO db_schema_version (version) VALUES (1)"
        )
        conn.commit()

    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO db_schema_version (version) VALUES (1)"
        )
        conn.commit()
    finally:
        conn.close()


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def get_or_create_account(conn: sqlite3.Connection, account_key: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM paper_accounts WHERE account_key = ?", (account_key,)
    ).fetchone()
    if row is not None:
        return dict(row)

    utc = _utc_now()
    conn.execute(
        """
        INSERT INTO paper_accounts
            (account_key, start_balance, current_balance, invested_capital,
             portfolio_value, currency, created_at, updated_at)
        VALUES (?, 100000.0, 100000.0, 0.0, 100000.0, 'INR', ?, ?)
        """,
        (account_key, utc, utc),
    )
    conn.commit()
    row2 = conn.execute(
        "SELECT * FROM paper_accounts WHERE account_key = ?", (account_key,)
    ).fetchone()
    if row2 is None:
        raise RuntimeError("get_or_create_account: inserted account row not found")
    return dict(row2)


def upsert_account(conn: sqlite3.Connection, account: Dict[str, Any]) -> Dict[str, Any]:
    utc = _utc_now()
    existing = dict(
        conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?", (account["account_key"],)
        ).fetchone()
    )

    balance_changed = existing is None or (
        existing["current_balance"] != account.get("current_balance")
        or existing["invested_capital"] != account.get("invested_capital")
        or existing["portfolio_value"] != account.get("portfolio_value")
        or existing["start_balance"] != account.get("start_balance")
    )

    if existing is None:
        conn.execute(
            """
            INSERT INTO paper_accounts
                (id, account_key, start_balance, current_balance, invested_capital,
                 portfolio_value, currency, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account.get("id"),
                account["account_key"],
                account.get("start_balance", 100000.0),
                account.get("current_balance", 100000.0),
                account.get("invested_capital", 0.0),
                account.get("portfolio_value", 100000.0),
                account.get("currency", "INR"),
                account.get("created_at", utc),
                utc,
            ),
        )
    elif balance_changed:
        conn.execute(
            """
            UPDATE paper_accounts
            SET current_balance = ?,
                invested_capital = ?,
                portfolio_value = ?,
                updated_at = ?
            WHERE account_key = ?
            """,
            (
                account.get("current_balance", existing["current_balance"]),
                account.get("invested_capital", existing["invested_capital"]),
                account.get("portfolio_value", existing["portfolio_value"]),
                utc,
                account["account_key"],
            ),
        )
    else:
        conn.execute(
            """
            UPDATE paper_accounts
            SET current_balance = ?,
                invested_capital = ?,
                portfolio_value = ?,
                updated_at = ?
            WHERE account_key = ?
            """,
            (
                existing["current_balance"],
                existing["invested_capital"],
                existing["portfolio_value"],
                utc,
                account["account_key"],
            ),
        )
    conn.commit()
    return _fetch_account(conn, account["account_key"])


def _fetch_account(conn: sqlite3.Connection, account_key: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM paper_accounts WHERE account_key = ?", (account_key,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Account not found: {account_key}")
    return dict(row)


def _fetch_equity_position(conn: sqlite3.Connection, account_key: str, symbol: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ? AND symbol = ?",
        (account_key, symbol),
    ).fetchone()
    return dict(row) if row is not None else None


def add_equity_position(
    conn: sqlite3.Connection,
    account_key: str,
    symbol: str,
    quantity: int,
    price: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    existing = _fetch_equity_position(conn, account_key, symbol)
    utc = _utc_now()
    if existing is None:
        conn.execute(
            """
            INSERT INTO equity_positions
                (account_key, symbol, quantity, avg_entry_price, cost_basis,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account_key, symbol, quantity, price, quantity * price, utc, utc),
        )
    else:
        total_qty = existing["quantity"] + quantity
        total_cost = existing["cost_basis"] + quantity * price + fees
        avg_price = total_cost / total_qty if total_qty else 0.0
        conn.execute(
            """
            UPDATE equity_positions
            SET quantity = ?,
                avg_entry_price = ?,
                cost_basis = ?,
                updated_at = ?
            WHERE account_key = ? AND symbol = ?
            """,
            (total_qty, avg_price, total_cost, utc, account_key, symbol),
        )
    conn.commit()
    return _load_equity_position(conn, account_key, symbol)


def _load_equity_position(conn: sqlite3.Connection, account_key: str, symbol: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ? AND symbol = ?",
        (account_key, symbol),
    ).fetchone()
    if row is None:
        raise KeyError(f"Position not found: {account_key}:{symbol}")
    return dict(row)


def remove_equity_position(conn: sqlite3.Connection, account_key: str, symbol: str) -> Optional[Dict[str, Any]]:
    row = _fetch_equity_position(conn, account_key, symbol)
    if row is None:
        return None
    conn.execute("DELETE FROM equity_positions WHERE account_key = ? AND symbol = ?", (account_key, symbol))
    conn.commit()
    return row


def get_equity_positions(conn: sqlite3.Connection, account_key: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ? ORDER BY symbol", (account_key,)
    ).fetchall()
    return [dict(r) for r in rows]


def close_equity_position(
    conn: sqlite3.Connection,
    account_key: str,
    symbol: str,
    quantity: int,
    exit_price: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    row = _fetch_equity_position(conn, account_key, symbol)
    if row is None:
        raise KeyError(f"Position not found: {account_key}:{symbol}")

    qty = int(quantity)
    if qty > row["quantity"]:
        raise ValueError("Sell quantity exceeds position quantity.")

    realised = (exit_price - row["avg_entry_price"]) * qty - fees
    utc = _utc_now()

    conn.execute(
        """
        INSERT INTO equity_closed_positions
            (account_key, symbol, quantity, avg_entry_price, exit_price,
             realised_pnl, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_key, symbol, qty, row["avg_entry_price"], exit_price, realised, utc),
    )
    conn.execute(
        "DELETE FROM equity_positions WHERE account_key = ? AND symbol = ?",
        (account_key, symbol),
    )

    conn.execute(
        "INSERT INTO equity_trade_history (account_key, symbol, action, quantity, price, fees, order_type, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account_key, symbol, "SELL", qty, exit_price, fees, "MARKET", utc),
    )
    conn.commit()

    closed = dict(conn.execute(
        "SELECT * FROM equity_closed_positions WHERE closed_id = last_insert_rowid()"
    ).fetchone())
    return closed


def record_equity_trade(
    conn: sqlite3.Connection,
    account_key: str,
    symbol: str,
    action: str,
    quantity: int,
    price: float,
    fees: float = 0.0,
    order_type: str = "MARKET",
) -> Dict[str, Any]:
    utc = _utc_now()
    conn.execute(
        """
        INSERT INTO equity_trade_history
            (account_key, symbol, action, quantity, price, fees, order_type, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_key, symbol, action.upper(), quantity, price, fees, order_type, utc),
    )
    conn.commit()
    return {
        "trade_id": conn.execute("SELECT last_insert_rowid()").fetchone()[0],
        "account_key": account_key,
        "symbol": symbol,
        "action": action.upper(),
        "quantity": quantity,
        "price": price,
        "fees": fees,
        "order_type": order_type,
        "timestamp": utc,
    }


def get_equity_trade_history(conn: sqlite3.Connection, account_key: str, limit: int = 500) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM equity_trade_history WHERE account_key = ? ORDER BY timestamp DESC, trade_id DESC LIMIT ?",
        (account_key, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def add_options_position(
    conn: sqlite3.Connection,
    account_key: str,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
    quantity: int,
    premium: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    existing = conn.execute(
        "SELECT * FROM options_positions WHERE account_key = ? AND underlying = ? AND expiry = ? AND strike = ? AND option_type = ?",
        (account_key, underlying, expiry, strike, option_type),
    ).fetchone()

    utc = _utc_now()
    if existing is None:
        conn.execute(
            """
            INSERT INTO options_positions
                (account_key, underlying, expiry, strike, option_type, quantity,
                 entry_premium, open_premium, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_key, underlying, expiry, strike, option_type, quantity, premium, premium, utc, utc),
        )
    else:
        total_qty = existing["quantity"] + quantity
        total_cost = existing["entry_premium"] * existing["quantity"] + premium * quantity + fees
        new_premium = total_cost / total_qty if total_qty else 0.0
        conn.execute(
            """
            UPDATE options_positions
            SET quantity = ?,
                entry_premium = ?,
                open_premium = ?,
                updated_at = ?
            WHERE account_key = ? AND underlying = ? AND expiry = ? AND strike = ? AND option_type = ?
            """,
            (total_qty, new_premium, new_premium, utc, account_key, underlying, expiry, strike, option_type),
        )
    conn.commit()
    return _load_options_position(conn, account_key, underlying, expiry, strike, option_type)


def _load_options_position(conn: sqlite3.Connection, account_key: str, underlying: str, expiry: str, strike: float, option_type: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM options_positions WHERE account_key = ? AND underlying = ? AND expiry = ? AND strike = ? AND option_type = ?",
        (account_key, underlying, expiry, strike, option_type),
    ).fetchone()
    if row is None:
        raise KeyError(f"Options position not found: {account_key}:{underlying}:{expiry}:{strike}:{option_type}")
    return dict(row)


def remove_options_position(
    conn: sqlite3.Connection,
    account_key: str,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
) -> Optional[Dict[str, Any]]:
    row = _load_options_position(conn, account_key, underlying, expiry, strike, option_type)
    conn.execute(
        "DELETE FROM options_positions WHERE account_key = ? AND underlying = ? AND expiry = ? AND strike = ? AND option_type = ?",
        (account_key, underlying, expiry, strike, option_type),
    )
    conn.commit()
    return row


def close_options_position(
    conn: sqlite3.Connection,
    account_key: str,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
    quantity: int,
    exit_premium: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    row = _load_options_position(conn, account_key, underlying, expiry, strike, option_type)
    qty = int(quantity)
    if qty > row["quantity"]:
        raise ValueError("Sell quantity exceeds options position quantity.")

    realised = (exit_premium - row["entry_premium"]) * qty - fees
    utc = _utc_now()

    conn.execute(
        """
        INSERT INTO options_closed_positions
            (account_key, underlying, expiry, strike, option_type, quantity,
             entry_premium, exit_premium, realised_pnl, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_key, underlying, expiry, strike, option_type, qty, row["entry_premium"], exit_premium, realised, utc),
    )
    conn.execute(
        "DELETE FROM options_positions WHERE account_key = ? AND underlying = ? AND expiry = ? AND strike = ? AND option_type = ?",
        (account_key, underlying, expiry, strike, option_type),
    )
    conn.execute(
        "INSERT INTO options_trade_history (account_key, underlying, expiry, strike, option_type, action, quantity, premium, fees, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (account_key, underlying, expiry, strike, option_type, "SELL", qty, exit_premium, fees, utc),
    )
    conn.commit()

    closed = dict(conn.execute(
        "SELECT * FROM options_closed_positions WHERE closed_id = last_insert_rowid()"
    ).fetchone())
    return closed


def record_options_trade(
    conn: sqlite3.Connection,
    account_key: str,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
    action: str,
    quantity: int,
    premium: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    utc = _utc_now()
    conn.execute(
        """
        INSERT INTO options_trade_history
            (account_key, underlying, expiry, strike, option_type, action,
             quantity, premium, fees, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_key, underlying, expiry, strike, option_type, action.upper(), quantity, premium, fees, utc),
    )
    conn.commit()
    return {
        "trade_id": conn.execute("SELECT last_insert_rowid()").fetchone()[0],
        "account_key": account_key,
        "underlying": underlying,
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type.upper(),
        "action": action.upper(),
        "quantity": quantity,
        "premium": premium,
        "fees": fees,
        "timestamp": utc,
    }


def get_options_trade_history(conn: sqlite3.Connection, account_key: str, limit: int = 500) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM options_trade_history WHERE account_key = ? ORDER BY timestamp DESC, trade_id DESC LIMIT ?",
        (account_key, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_settings(conn: sqlite3.Connection, account_key: str) -> Dict[str, Any]:
    rows = conn.execute("SELECT setting_key, setting_value FROM settings WHERE account_key = ?", (account_key,)).fetchall()
    return {r["setting_key"]: r["setting_value"] for r in rows}


def set_setting(conn: sqlite3.Connection, account_key: str, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (account_key, setting_key, setting_value)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
        """,
        (account_key, key, value),
    )
    conn.commit()
