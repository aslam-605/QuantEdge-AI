"""Non-destructive checks for options, chart, signal, and assistant workflows."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from modules.ai_assistant import OllamaAssistant
from modules.charting import interactive_candlestick_figure
from modules.database import SCHEMA
from modules.options_chain import (
    YfinanceOptionsAdapter,
    analyze_contract,
    chain_statistics,
    contract_candles,
    load_csv_options,
    load_option_candles,
    nearest_expiry,
    prepare_chain_table,
)
from modules.paper_trading import book_option_trade
from modules.signal_engine import generate_signal


def _csv_bytes(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


class TestOptionsDataWorkflow(unittest.TestCase):
    def setUp(self):
        self.expiry = (date.today() + timedelta(days=14)).isoformat()
        self.chain_csv = _csv_bytes(
            [
                "symbol,expiry,strike,option_type,ltp,change,open_interest,change_in_open_interest,volume,iv,delta,gamma,theta,vega,timestamp",
                f"NIFTY 50,{self.expiry},24900,CE,160,4,500,40,120,18,0.7,0.01,-0.2,0.1,2026-10-31T12:00:00Z",
                f"NIFTY 50,{self.expiry},24900,PE,80,-3,300,-20,90,19,-0.3,0.01,-0.2,0.1,2026-10-31T12:00:00Z",
                f"NIFTY 50,{self.expiry},25000,CE,110,5,1200,60,400,17,0.5,0.02,-0.3,0.2,2026-10-31T12:00:00Z",
                f"NIFTY 50,{self.expiry},25000,PE,130,-4,900,30,350,18,-0.5,0.02,-0.3,0.2,2026-10-31T12:00:00Z",
                f"NIFTY 50,{self.expiry},25100,CE,60,2,200,10,70,20,0.2,0.01,-0.1,0.1,2026-10-31T12:00:00Z",
                f"NIFTY 50,{self.expiry},25100,PE,180,6,1500,80,500,21,-0.7,0.01,-0.4,0.2,2026-10-31T12:00:00Z",
            ]
        )

    def test_expiry_selection_uses_nearest_upcoming(self):
        today = datetime.now(timezone.utc).date()
        past = (today - timedelta(days=1)).isoformat()
        soon = (today + timedelta(days=2)).isoformat()
        later = (today + timedelta(days=8)).isoformat()
        self.assertEqual(nearest_expiry([later, past, soon]), soon)
        self.assertIsNone(nearest_expiry([past]))
        self.assertEqual(nearest_expiry([past], allow_past=True), past)

    def test_chain_atm_moneyness_pcr_and_max_pain(self):
        loaded = load_csv_options(self.chain_csv)
        self.assertTrue(loaded["available"], loaded)
        table = prepare_chain_table(loaded["data"], "NIFTY 50", self.expiry, 25020.0, strike_range=1)
        self.assertEqual(table["Strike"].tolist(), [24900.0, 25000.0, 25100.0])
        atm = table.loc[table["ATM"]].iloc[0]
        self.assertEqual(atm["CE Status"], "ATM")
        self.assertEqual(atm["PE Status"], "ATM")
        self.assertEqual(table.iloc[0]["CE Status"], "ITM")
        self.assertEqual(table.iloc[-1]["PE Status"], "ITM")
        unknown = prepare_chain_table(loaded["data"], "NIFTY 50", self.expiry, None, strike_range=1)
        self.assertFalse(unknown["ATM"].any())
        self.assertEqual(set(unknown["CE Status"]), {"Unknown"})
        stats = chain_statistics(loaded["data"], "NIFTY 50", self.expiry)
        self.assertGreater(stats["pcr"], 0)
        self.assertIn(stats["max_pain"], (24900.0, 25000.0, 25100.0))
        self.assertEqual(stats["max_ce_oi"]["strike"], 25000.0)
        self.assertEqual(stats["max_pe_oi"]["strike"], 25100.0)

    def test_option_candles_are_filtered_to_exact_contract(self):
        rows = [
            "symbol,expiry,strike,option_type,timestamp,open,high,low,close,volume",
            f"NIFTY 50,{self.expiry},25000,CE,2026-10-30T10:00:00Z,100,110,95,105,1000",
            f"NIFTY 50,{self.expiry},25000,CE,2026-10-31T10:00:00Z,105,115,100,112,1300",
            f"NIFTY 50,{self.expiry},25000,PE,2026-10-31T10:00:00Z,120,125,110,115,800",
            f"NIFTY 50,{self.expiry},25100,CE,2026-10-31T10:00:00Z,70,80,65,75,400",
        ]
        loaded = load_option_candles(_csv_bytes(rows))
        self.assertTrue(loaded["available"], loaded)
        ce = contract_candles(loaded["data"], "NIFTY 50", self.expiry, 25000, "CE")
        self.assertEqual(len(ce), 2)
        self.assertEqual(float(ce["close"].iloc[-1]), 112.0)
        self.assertEqual(contract_candles(loaded["data"], "NIFTY 50", self.expiry, 25000, "PE").shape[0], 1)

    def test_option_analysis_requires_price_and_oi_for_buildup(self):
        loaded = load_csv_options(self.chain_csv)
        data = loaded["data"]
        contract = data[(data["strike"] == 25000) & (data["option_type"] == "CE")].iloc[0]
        index = pd.date_range("2026-09-01", periods=30, freq="D")
        close = pd.Series(np.linspace(80, 110, 30), index=index)
        candles = pd.DataFrame({"open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": range(1000, 1030)}, index=index)
        analysis = analyze_contract(contract, candles, data, 25000)
        self.assertEqual(analysis["moneyness"], "ATM")
        self.assertIn("buildup", analysis["oi_analysis"].lower())
        self.assertIn(analysis["overall"], {"Bullish", "Bearish", "Neutral"})
        missing_oi = contract.copy()
        missing_oi["change_in_open_interest"] = np.nan
        self.assertEqual(analyze_contract(missing_oi, candles, data, 25000)["oi_analysis"], "Insufficient data")

    def test_no_index_provider_data_is_explicitly_unavailable(self):
        adapter = YfinanceOptionsAdapter()
        for symbol in ("NIFTY 50", "BANK NIFTY"):
            with self.subTest(symbol=symbol):
                result = adapter.get_chain(symbol)
                self.assertFalse(result["available"])
                self.assertEqual(result["status"], "UNAVAILABLE")
                self.assertIsNone(result["data"])

    def test_invalid_or_empty_csv_is_unavailable(self):
        result = load_csv_options(_csv_bytes(["symbol,expiry", "NIFTY 50,2026-11-05"]))
        self.assertFalse(result["available"])
        self.assertIn("Missing", result["error"])
        candles = load_option_candles(_csv_bytes(["symbol,expiry", "NIFTY 50,2026-11-05"]))
        self.assertFalse(candles["available"])


class TestIntegratedAnalysisHelpers(unittest.TestCase):
    def test_interactive_chart_has_separate_indicator_panels(self):
        index = pd.date_range("2026-01-01", periods=40, freq="D")
        close = pd.Series(np.linspace(100, 140, len(index)), index=index)
        frame = pd.DataFrame({"open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": 1000}, index=index)
        figure = interactive_candlestick_figure(frame, "Fixture", ["EMA 9", "Volume", "RSI", "MACD"])
        self.assertEqual(len(figure.data), 7)
        self.assertTrue(figure.layout.xaxis.rangeselector)
        self.assertEqual(figure.data[0].type, "candlestick")
        light_figure = interactive_candlestick_figure(frame, "Fixture", ["EMA 9"], theme="Light")
        self.assertEqual(light_figure.layout.paper_bgcolor, "#F2F6F6")

    def test_signal_risk_reward_and_sourced_freshness(self):
        result = generate_signal(
            {"close": 100, "rsi": 55, "ema9": 105, "ema20": 103, "ema50": 101, "trend_direction": "BULLISH"},
            {"BULLISH": 0.8, "BEARISH": 0.1, "NEUTRAL": 0.1},
            support=[90, 95],
            resistance=[110, 115],
            state={"timestamp": "2026-10-31T12:00:00Z", "freshness": "HISTORICAL"},
        )
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["risk_to_reward"], 2.0)
        self.assertEqual(result["data_freshness"], "HISTORICAL")
        self.assertTrue(result["signal_timestamp"])

    def test_neutral_model_probability_does_not_create_bearish_signal_from_ema_alone(self):
        result = generate_signal(
            {"close": 100, "rsi": 55, "ema9": 95, "ema20": 98, "ema50": 101, "trend_direction": "BEARISH"},
            {"BULLISH": 0.02, "BEARISH": 0.03, "NEUTRAL": 0.95},
        )
        self.assertEqual(result["signal"], "HOLD")
        self.assertEqual(result["confidence"], 0.95)

    def test_option_paper_order_uses_in_memory_database(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute(
            """INSERT INTO paper_accounts
               (account_key,start_balance,current_balance,invested_capital,portfolio_value,currency,created_at,updated_at)
               VALUES ('fixture',100000,100000,0,100000,'INR','now','now')"""
        )
        connection.commit()
        expiry = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
        order = book_option_trade(connection, "fixture", "NIFTY 50", expiry, 25000, "CE", 2, 100, 5)
        account = connection.execute("SELECT current_balance, invested_capital FROM paper_accounts WHERE account_key='fixture'").fetchone()
        self.assertEqual(order["status"], "SUCCESS")
        self.assertEqual(account["current_balance"], 99795)
        self.assertEqual(account["invested_capital"], 205)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM options_trade_history").fetchone()[0], 1)
        connection.close()

    def test_qwen_receives_supplied_data_and_returns_explanation(self):
        class FakeResponse:
            ok = True
            text = ""

            def json(self):
                return {"models": [{"name": "qwen3.5:4b"}]} if self.is_tags else {"message": {"content": "The supplied trend is bullish."}}

            is_tags = True

        tags_response = FakeResponse()
        chat_response = FakeResponse()
        chat_response.is_tags = False
        with patch("modules.ai_assistant.requests.get", return_value=tags_response), patch("modules.ai_assistant.requests.post", return_value=chat_response) as post:
            assistant = OllamaAssistant()
            result = assistant.chat("Explain", structured_data={"price": 123.0})
        self.assertTrue(result["success"])
        self.assertIn("bullish", result["assistant_reply"])
        self.assertIn("price", post.call_args.kwargs["json"]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()