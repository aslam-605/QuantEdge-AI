"""Page 7: Equity Paper Trading."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules import market_data  # noqa: E402
from modules.database import get_connection, get_or_create_account, upsert_account  # noqa: E402
from modules.paper_trading import book_trade  # noqa: E402
from utils.ui import set_market_context  # noqa: E402

_DB_PATH = _PROJECT_ROOT / "data" / "paper_trading.db"

EQUITY_SYMBOLS = ["RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS"]


def app():
    st.caption("Simulated orders only. No broker connection or real order execution is used.")

    conn = get_connection(_DB_PATH)
    account_key = st.session_state.get("account_key", "quantedge_user")

    account = get_or_create_account(conn, account_key)
    balance_columns = st.columns(4)
    balance_columns[0].metric("Starting balance", f"{account['start_balance']:,.2f} INR")
    balance_columns[1].metric("Available balance", f"{account['current_balance']:,.2f} INR")
    balance_columns[2].metric("Invested", f"{account['invested_capital']:,.2f} INR")
    balance_columns[3].metric("Currency", account["currency"])

    equity_tab, options_tab, open_tab, closed_tab, history_tab = st.tabs(
        ["Equity order", "Options", "Open positions", "Closed positions", "Trade history"]
    )
    with equity_tab:
        symbol = st.selectbox("Equity instrument", EQUITY_SYMBOLS, key="paper_equity_symbol")
        quote = market_data.market.get_quotes([symbol]).get(symbol, {})
        current_quote = quote.get("last_price") if quote.get("available") else None
        set_market_context(
            st,
            market_data.market.get_symbol_display_name(symbol),
            quote.get("source", "yfinance daily history"),
            quote.get("status", "UNAVAILABLE"),
            quote.get("timestamp"),
        )
        st.session_state["qe_selected_instrument"] = symbol
        st.caption(
            f"Quote: {current_quote:,.2f}" if current_quote is not None else "Quote unavailable; enter a valid observed price manually."
        )
        with st.form("equity_paper_order"):
            action = st.radio("Side", ["BUY", "SELL"], horizontal=True)
            quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
            price = st.number_input(
                "Order price (INR)",
                min_value=0.0,
                value=float(current_quote or 0.0),
                step=1.0,
                key=f"paper_equity_price_{symbol}",
            )
            fees = st.number_input("Estimated charges (INR)", min_value=0.0, value=float(st.session_state.get("qe_brokerage", 20.0)), step=1.0)
            total = int(quantity) * float(price) + float(fees)
            st.write(f"Review: {action} {int(quantity)} {market_data.market.get_symbol_display_name(symbol)} @ {price:,.2f} · estimated total {total:,.2f} INR")
            submitted = st.form_submit_button("Confirm simulated order", type="primary")
        if submitted:
            try:
                result = book_trade(conn, account_key, action, symbol, int(quantity), float(price), fees=float(fees))
                st.success(f"Simulated {result['action']} order recorded.")
            except Exception as exc:
                st.error(f"Order not saved: {exc}")

    with options_tab:
        st.write("Select a sourced option contract in Options Chain or AI Predictions, review its premium, then confirm a simulated order there.")
        st.page_link("pages/4_Options_Chain.py", label="Open Options Chain", icon=":material/candlestick_chart:")
        option_positions = conn.execute(
            "SELECT * FROM options_positions WHERE account_key = ? ORDER BY expiry, underlying, strike",
            (account_key,),
        ).fetchall()
        if option_positions:
            st.dataframe(pd.DataFrame([dict(row) for row in option_positions]), use_container_width=True, hide_index=True)
        else:
            st.info("No open options paper positions.")

    with open_tab:
        positions = conn.execute(
            "SELECT * FROM equity_positions WHERE account_key = ? ORDER BY symbol", (account_key,)
        ).fetchall()
        option_positions = conn.execute(
            "SELECT * FROM options_positions WHERE account_key = ? ORDER BY expiry, underlying, strike", (account_key,)
        ).fetchall()
        st.markdown("#### Equity")
        if positions:
            st.dataframe(pd.DataFrame([dict(row) for row in positions]), use_container_width=True, hide_index=True)
        else:
            st.info("No open equity positions.")
        st.markdown("#### Options")
        if option_positions:
            st.dataframe(pd.DataFrame([dict(row) for row in option_positions]), use_container_width=True, hide_index=True)
        else:
            st.info("No open options positions.")

    with closed_tab:
        closed_equity = conn.execute(
            "SELECT * FROM equity_closed_positions WHERE account_key = ? ORDER BY closed_at DESC LIMIT 200", (account_key,)
        ).fetchall()
        closed_options = conn.execute(
            "SELECT * FROM options_closed_positions WHERE account_key = ? ORDER BY closed_at DESC LIMIT 200", (account_key,)
        ).fetchall()
        st.markdown("#### Closed equity positions")
        st.dataframe(pd.DataFrame([dict(row) for row in closed_equity]) if closed_equity else pd.DataFrame(), use_container_width=True, hide_index=True)
        if not closed_equity:
            st.info("No closed equity positions.")
        st.markdown("#### Closed options positions")
        st.dataframe(pd.DataFrame([dict(row) for row in closed_options]) if closed_options else pd.DataFrame(), use_container_width=True, hide_index=True)
        if not closed_options:
            st.info("No closed options positions.")

    with history_tab:
        equity_trades = conn.execute(
            "SELECT * FROM equity_trade_history WHERE account_key = ? ORDER BY timestamp DESC LIMIT 200", (account_key,)
        ).fetchall()
        option_trades = conn.execute(
            "SELECT * FROM options_trade_history WHERE account_key = ? ORDER BY timestamp DESC LIMIT 200", (account_key,)
        ).fetchall()
        st.markdown("#### Equity orders")
        if equity_trades:
            st.dataframe(pd.DataFrame([dict(row) for row in equity_trades]), use_container_width=True, hide_index=True)
        else:
            st.info("No equity orders recorded.")
        st.markdown("#### Options orders")
        if option_trades:
            st.dataframe(pd.DataFrame([dict(row) for row in option_trades]), use_container_width=True, hide_index=True)
        else:
            st.info("No options orders recorded.")

    with st.expander("Account maintenance"):
        with st.form("reset_paper_account"):
            starting_balance = st.number_input("Reset balance (INR)", min_value=1000.0, value=float(account["start_balance"]), step=1000.0)
            confirm_reset = st.checkbox("I understand this changes virtual balances but does not delete trade records.")
            reset = st.form_submit_button("Reset virtual balance")
        if reset:
            if not confirm_reset:
                st.warning("Confirm the reset before proceeding.")
            else:
                upsert_account(conn, {
                    "account_key": account_key,
                    "start_balance": starting_balance,
                    "current_balance": starting_balance,
                    "invested_capital": 0.0,
                    "portfolio_value": starting_balance,
                    "currency": account["currency"],
                    "created_at": account["created_at"],
                    "updated_at": account["updated_at"],
                })
                st.success("Virtual account balance reset. Trade records were retained.")
                st.rerun()


if __name__ == "__main__":
    app()
