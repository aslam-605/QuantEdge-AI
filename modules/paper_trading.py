"""Equity paper trading engine.

Simulates buying and selling with SQLite persistence. No real broker is used.
Validates balance, quantity, price, and position size.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.database import get_connection, get_or_create_account, upsert_account
from utils.validators import is_float, is_int

logger = logging.getLogger(__name__)


def validate_order(
    action: str,
    quantity: float,
    price: float,
    virtual_balance: float,
    balance: float,
    fees: float = 0.0,
    min_quantity: int = 1,
    max_quantity: int = 1000000,
    max_price: float = 1000000.0,
) -> tuple[bool, str, Dict[str, Any]]:
    """Validate a paper trade order."""
    if action.upper() not in ("BUY", "SELL"):
        return False, "Invalid action: choose BUY or SELL", {}

    if not is_int(quantity, min_quantity):
        return False, f"Quantity must be an integer >= {min_quantity}", {}
    qty = int(quantity)
    if qty <= 0:
        return False, "Quantity must be positive", {}

    if not is_float(price, 0.0):
        return False, "Price must be a positive number", {}
    price = float(price)
    if price <= 0 or price > max_price:
        return False, "Price is out of allowed range", {}

    if action.upper() == "SELL" and qty > balance:
        return False, "Sell quantity exceeds current holdings", {}

    if action.upper() == "BUY" and qty > 0:
        cost = qty * price + fees
        if cost > balance:
            return False, "Insufficient virtual balance for this buy order", {}

    return True, "OK", {
        "quantity": qty,
        "price": price,
        "fees": float(fees),
        "total_cost": (qty * price) + float(fees),
        "remaining_balance": balance - ((qty * price) + float(fees)),
    }


def book_trade(
    conn,
    account_key: str,
    action: str,
    symbol: str,
    quantity: int,
    price: float,
    fees: float = 0.0,
    order_type: str = "MARKET",
) -> Dict[str, Any]:
    normalized_action = str(action).upper()
    if normalized_action not in {"BUY", "SELL"}:
        raise ValueError("Invalid action: choose BUY or SELL.")
    if not is_float(fees, 0.0):
        raise ValueError("Fees must be a non-negative number.")
    qty = int(quantity) if is_int(quantity, 1) else 0
    unit_price = float(price) if is_float(price, 0.0) else 0.0
    fee_amount = float(fees)
    if not symbol.strip():
        raise ValueError("A symbol is required.")

    account = get_or_create_account(conn, account_key)
    balance = float(account["current_balance"])
    position = conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ? AND symbol = ?",
        (account_key, symbol),
    ).fetchone()
    held_quantity = int(position["quantity"]) if position is not None else 0
    valid, message, result = validate_order(
        normalized_action,
        quantity,
        price,
        balance,
        held_quantity if normalized_action == "SELL" else balance,
        fee_amount,
    )
    if not valid:
        raise ValueError(message)

    nested_transaction = conn.in_transaction
    savepoint = "paper_trade_order"
    if nested_transaction:
        conn.execute(f"SAVEPOINT {savepoint}")
    else:
        conn.execute("BEGIN IMMEDIATE")
    timestamp = now_iso()
    try:
        if normalized_action == "BUY":
            purchase_cost = qty * unit_price + fee_amount
            existing = position
            if existing is None:
                conn.execute(
                    "INSERT INTO equity_positions (account_key, symbol, quantity, avg_entry_price, cost_basis, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (account_key, symbol, qty, purchase_cost / qty, purchase_cost, timestamp, timestamp),
                )
            else:
                total_qty = existing["quantity"] + qty
                total_cost = existing["cost_basis"] + purchase_cost
                avg = total_cost / total_qty if total_qty else 0.0
                conn.execute(
                    "UPDATE equity_positions SET quantity = ?, avg_entry_price = ?, cost_basis = ?, updated_at = ? WHERE account_key = ? AND symbol = ?",
                    (total_qty, avg, total_cost, timestamp, account_key, symbol),
                )
            conn.execute(
                "UPDATE paper_accounts SET current_balance = current_balance - ?, invested_capital = invested_capital + ?, updated_at = ? WHERE account_key = ?",
                (purchase_cost, purchase_cost, timestamp, account_key),
            )
            realised = None
        else:
            held_cost = float(position["cost_basis"])
            allocated_cost = held_cost * qty / held_quantity
            remaining_qty = held_quantity - qty
            remaining_cost = held_cost - allocated_cost
            realised = qty * unit_price - fee_amount - allocated_cost
            conn.execute(
                "INSERT INTO equity_closed_positions (account_key, symbol, quantity, avg_entry_price, exit_price, realised_pnl, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_key, symbol, qty, allocated_cost / qty, unit_price, round(realised, 2), timestamp),
            )
            if remaining_qty == 0:
                conn.execute(
                    "DELETE FROM equity_positions WHERE account_key = ? AND symbol = ?",
                    (account_key, symbol),
                )
            else:
                conn.execute(
                    "UPDATE equity_positions SET quantity = ?, cost_basis = ?, updated_at = ? WHERE account_key = ? AND symbol = ?",
                    (remaining_qty, remaining_cost, timestamp, account_key, symbol),
                )
            conn.execute(
                "UPDATE paper_accounts SET current_balance = current_balance + ?, invested_capital = MAX(0, invested_capital - ?), updated_at = ? WHERE account_key = ?",
                (qty * unit_price - fee_amount, allocated_cost, timestamp, account_key),
            )

        trade_cursor = conn.execute(
            """INSERT INTO equity_trade_history
               (account_key, symbol, action, quantity, price, fees, order_type, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_key, symbol, normalized_action, qty, unit_price, fee_amount, order_type, timestamp),
        )
        conn.execute(
            """INSERT INTO trades
               (account_key, symbol, action, quantity, price, fees, order_type, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_key, symbol, normalized_action, qty, unit_price, fee_amount, order_type, timestamp),
        )
        if nested_transaction:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            conn.commit()

        return {
            "trade_id": trade_cursor.lastrowid,
            "account_key": account_key,
            "action": normalized_action,
            "symbol": symbol,
            "quantity": qty,
            "price": unit_price,
            "fees": fee_amount,
            "order_type": order_type,
            "timestamp": timestamp,
            "status": "SUCCESS",
            "realised_pnl": round(realised, 2) if realised is not None else None,
        }
    except Exception:
        if nested_transaction:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            conn.rollback()
        raise


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def book_option_trade(
    conn,
    account_key: str,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
    quantity: int,
    premium: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    """Open a confirmed simulated option position using an observed premium."""
    option_type = str(option_type).upper()
    if option_type not in {"CE", "PE"}:
        raise ValueError("Option type must be CE or PE.")
    if not is_int(quantity, 1):
        raise ValueError("Quantity must be a positive whole number of option units.")
    qty = int(quantity)
    if not is_float(premium, 0.0) or float(premium) <= 0:
        raise ValueError("A positive observed option premium is required.")
    premium = float(premium)
    fees = float(fees)
    expiry_date = datetime.strptime(str(expiry), "%Y-%m-%d").date()
    if expiry_date < datetime.now(timezone.utc).date():
        raise ValueError("Cannot open a paper position in an expired option contract.")

    account = get_or_create_account(conn, account_key)
    required_balance = qty * premium + fees
    if required_balance > float(account["current_balance"]):
        raise ValueError("Insufficient virtual balance for this option order.")

    conn.execute("BEGIN")
    try:
        existing = conn.execute(
            """SELECT * FROM options_positions
               WHERE account_key = ? AND underlying = ? AND expiry = ?
                 AND strike = ? AND option_type = ?""",
            (account_key, underlying, expiry, float(strike), option_type),
        ).fetchone()
        timestamp = now_iso()
        if existing is None:
            conn.execute(
                """INSERT INTO options_positions
                   (account_key, underlying, expiry, strike, option_type, quantity,
                    entry_premium, open_premium, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_key, underlying, expiry, float(strike), option_type, qty, premium, premium, timestamp, timestamp),
            )
        else:
            total_quantity = int(existing["quantity"]) + qty
            average_premium = (
                float(existing["entry_premium"]) * int(existing["quantity"]) + premium * qty
            ) / total_quantity
            conn.execute(
                """UPDATE options_positions
                   SET quantity = ?, entry_premium = ?, open_premium = ?, updated_at = ?
                   WHERE position_id = ?""",
                (total_quantity, average_premium, average_premium, timestamp, existing["position_id"]),
            )
        cursor = conn.execute(
            """INSERT INTO options_trade_history
               (account_key, underlying, expiry, strike, option_type, action,
                quantity, premium, fees, timestamp)
               VALUES (?, ?, ?, ?, ?, 'BUY', ?, ?, ?, ?)""",
            (account_key, underlying, expiry, float(strike), option_type, qty, premium, fees, timestamp),
        )
        conn.execute(
            """UPDATE paper_accounts
               SET current_balance = current_balance - ?,
                   invested_capital = invested_capital + ?, updated_at = ?
               WHERE account_key = ?""",
            (required_balance, required_balance, timestamp, account_key),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "trade_id": cursor.lastrowid,
        "account_key": account_key,
        "underlying": underlying,
        "expiry": expiry,
        "strike": float(strike),
        "option_type": option_type,
        "action": "BUY",
        "quantity": qty,
        "premium": premium,
        "fees": fees,
        "timestamp": timestamp,
        "status": "SUCCESS",
    }
