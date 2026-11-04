"""Tests for SQLite database initialisation and persistence."""

import os
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from modules.database import get_connection, init_db


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).resolve().parent / "test_paper.db"
        import os, sqlite3
        if self.db_path.exists():
            import os, sqlite3
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except Exception:
                pass
            self.db_path.unlink()
        init_db(self.db_path)

    def tearDown(self):
        try:
            self.db_path.unlink()
        except PermissionError:
            pass

    def test_database_initialised_with_required_tables(self):
        conn = get_connection(self.db_path)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        }
        required = {
            "paper_accounts",
            "equity_positions",
            "equity_closed_positions",
            "equity_trade_history",
            "options_positions",
            "options_closed_positions",
            "options_trade_history",
            "settings",
            "db_schema_version",
        }
        self.assertTrue(required.issubset(tables))
        conn.close()

    def test_account_crud(self):
        conn = get_connection(self.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO paper_accounts (account_key, start_balance, current_balance, invested_capital, portfolio_value, currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("test_sequence", 100000.0, 100000.0, 0.0, 100000.0, "INR", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
        conn.commit()
        account = conn.execute(
            "SELECT * FROM paper_accounts WHERE account_key = ?",
            ("test_sequence",),
        ).fetchone()
        self.assertIsNotNone(account)
        self.assertEqual(account["current_balance"], 100000.0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
