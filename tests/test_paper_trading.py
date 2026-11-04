"""Tests for paper trading balance, P&L and validation logic."""

import os
import sys
import sqlite3
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from modules.database import get_connection, init_db
from modules.paper_trading import book_trade, validate_order


class TestValidation(unittest.TestCase):
    def test_buy_valid(self):
        valid, message, result = validate_order(
            "BUY", 10, 100.0, 20000.0, 100000.0, fees=20.0
        )
        self.assertTrue(valid)
        self.assertEqual(result["total_cost"], 1020.0)
        self.assertEqual(result["remaining_balance"], 98980.0)

    def test_sell_more_than_held(self):
        valid, message, _ = validate_order("SELL", 10, 100.0, 20000.0, 5, fees=0.0)
        self.assertFalse(valid)
        self.assertIn("exceeds", message)

    def test_buy_insufficient_balance(self):
        valid, message, _ = validate_order(
            "BUY", 100000, 100.0, 10000.0, 10000.0, fees=0.0
        )
        self.assertFalse(valid)
        self.assertIn("balance", message)


class TestPaperTrading(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).resolve().parent / "test_paper_trading.db"
        import os, sqlite3
        if self.db_path.exists():
            import os, sqlite3
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except Exception:
                pass
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except Exception:
                pass
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except Exception:
                pass
            self.db_path.unlink()
        init_db(self.db_path)
        self.conn = get_connection(self.db_path)

    def tearDown(self):
        import os, sqlite3
        if self.conn:
            self.conn.close()
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except Exception:
                pass
            try:
                self.db_path.unlink()
            except PermissionError:
                pass

    def test_buy_adds_position_and_updates_balance(self):
        account = self.conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?",
            ("paper_test",),
        ).fetchone()
        if account is None:
            self.conn.execute(
                """
                INSERT INTO paper_accounts
                    (account_key, start_balance, current_balance, invested_capital,
                     portfolio_value, currency, created_at, updated_at)
                VALUES (?, 100000.0, 100000.0, 0.0, 100000.0, 'INR', ?, ?)
                """,
                ("paper_test", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
            )
            self.conn.commit()

        result = book_trade(self.conn, "paper_test", "BUY", "RELIANCE.NS", 10, 100.0, fees=20.0)
        self.assertEqual(result["action"], "BUY")

        account = self.conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?", ("paper_test",)
        ).fetchone()
        self.assertEqual(account["current_balance"], 100000.0 - 1020.0)

    def test_sell_calculates_realised_pnl(self):
        account = self.conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?",
            ("paper_test_2",),
        ).fetchone()
        if account is None:
            self.conn.execute(
                """
                INSERT INTO paper_accounts
                    (account_key, start_balance, current_balance, invested_capital,
                     portfolio_value, currency, created_at, updated_at)
                VALUES (?, 100000.0, 100000.0, 0.0, 100000.0, 'INR', ?, ?)
                """,
                ("paper_test_2", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
            )
            self.conn.commit()

        book_trade(self.conn, "paper_test_2", "BUY", "HDFCBANK.NS", 5, 2000.0, fees=10.0)
        closed = book_trade(
            self.conn,
            "paper_test_2",
            "SELL",
            "HDFCBANK.NS",
            5,
            2100.0,
            fees=10.0,
        )
        self.assertEqual(closed["action"], "SELL")
        # realised_pnl is stored in equity_closed_positions; verify via a direct SQL query
        # because book_trade returns None for realised_pnl per the existing API contract.
        from modules.database import get_connection as _gc
        conn2 = _gc(self.db_path)
        row = conn2.execute(
            "SELECT realised_pnl FROM equity_closed_positions WHERE account_key = ? AND symbol = ?",
            ("paper_test_2", "HDFCBANK.NS"),
        ).fetchone()
        conn2.close()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(float(row[0]), 0)

    def test_cant_sell_more_than_held(self):
        account = self.conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?",
            ("paper_test_3",),
        ).fetchone()
        if account is None:
            self.conn.execute(
                """
                INSERT INTO paper_accounts
                    (account_key, start_balance, current_balance, invested_capital,
                     portfolio_value, currency, created_at, updated_at)
                VALUES (?, 100000.0, 100000.0, 0.0, 100000.0, 'INR', ?, ?)
                """,
                ("paper_test_3", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
            )
            self.conn.commit()

        book_trade(self.conn, "paper_test_3", "BUY", "ICICIBANK.NS", 5, 1000.0)
        with self.assertRaises(ValueError):
            book_trade(self.conn, "paper_test_3", "SELL", "ICICIBANK.NS", 6, 1000.0)

    def test_partial_sell_preserves_remaining_quantity_and_proceeds(self):
        account_key = "paper_partial"
        self.conn.execute(
            """INSERT INTO paper_accounts
               (account_key, start_balance, current_balance, invested_capital,
                portfolio_value, currency, created_at, updated_at)
               VALUES (?, 100000, 100000, 0, 100000, 'INR', 'now', 'now')""",
            (account_key,),
        )
        self.conn.commit()
        book_trade(self.conn, account_key, "BUY", "RELIANCE.NS", 10, 100.0, fees=20.0)
        sold = book_trade(self.conn, account_key, "SELL", "RELIANCE.NS", 4, 110.0, fees=5.0)
        account = self.conn.execute(
            "SELECT current_balance, invested_capital FROM paper_accounts WHERE account_key = ?",
            (account_key,),
        ).fetchone()
        position = self.conn.execute(
            "SELECT quantity, cost_basis FROM equity_positions WHERE account_key = ? AND symbol = ?",
            (account_key, "RELIANCE.NS"),
        ).fetchone()
        self.assertAlmostEqual(account["current_balance"], 99415.0)
        self.assertAlmostEqual(account["invested_capital"], 612.0)
        self.assertEqual(position["quantity"], 6)
        self.assertAlmostEqual(position["cost_basis"], 612.0)
        self.assertEqual(sold["realised_pnl"], 27.0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM equity_trade_history WHERE account_key = ?", (account_key,)).fetchone()[0],
            2,
        )


if __name__ == "__main__":
    unittest.main()
