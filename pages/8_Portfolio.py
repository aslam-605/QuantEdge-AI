"""Page 8: Portfolio and Trade History."""

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

from modules.database import get_connection, get_or_create_account, upsert_account  # noqa: E402
from modules.portfolio import portfolio_snapshot, daily_pl_for_last_days, equity_curve  # noqa: E402
from modules.market_data import market  # noqa: E402

_DB_PATH = _PROJECT_ROOT / "data" / "paper_trading.db"


def app():
    st.caption("Paper account performance from persisted SQLite records; unpriced holdings remain unavailable.")

    conn = get_connection(_DB_PATH)
    account_key = st.session_state.get("account_key", "quantedge_user")

    account = get_or_create_account(conn, account_key)
    snap = portfolio_snapshot(conn, account_key)
    equity_positions = [dict(row) for row in conn.execute(
        "SELECT * FROM equity_positions WHERE account_key = ? ORDER BY symbol", (account_key,)
    ).fetchall()]
    option_positions = [dict(row) for row in conn.execute(
        "SELECT * FROM options_positions WHERE account_key = ? ORDER BY expiry, underlying, strike", (account_key,)
    ).fetchall()]
    equity_quotes = market.get_quotes([row["symbol"] for row in equity_positions]) if equity_positions else {}
    unrealized_equity = 0.0
    market_value = 0.0
    all_equity_prices = True
    for position in equity_positions:
        quote = equity_quotes.get(position["symbol"], {})
        price = quote.get("last_price")
        if price is None:
            all_equity_prices = False
            continue
        market_value += float(price) * int(position["quantity"])
        unrealized_equity += (float(price) - float(position["avg_entry_price"])) * int(position["quantity"])
    total_unrealized = None if option_positions or not all_equity_prices else unrealized_equity
    portfolio_value = None if option_positions or not all_equity_prices else float(snap["available_balance"]) + market_value

    summary = st.columns(5)
    summary[0].metric("Starting balance", f"{snap['start_balance']:,.2f} INR")
    summary[1].metric("Available balance", f"{snap['available_balance']:,.2f} INR")
    summary[2].metric("Invested capital", f"{snap['invested_capital']:,.2f} INR")
    summary[3].metric("Portfolio value", f"{portfolio_value:,.2f} INR" if portfolio_value is not None else "Unavailable")
    summary[4].metric("Total P&L", f"{snap['realised_pl'] + total_unrealized:+,.2f} INR" if total_unrealized is not None else "Unavailable")

    details = st.columns(4)
    details[0].metric("Realized P&L", f"{snap['realised_pl']:+,.2f} INR")
    details[1].metric("Unrealized P&L", f"{total_unrealized:+,.2f} INR" if total_unrealized is not None else "Unavailable")
    details[2].metric("Winning closes", str(snap["winning_trades"]))
    details[3].metric("Win rate", f"{snap['win_rate']:.1f}%")

    if option_positions:
        st.info("Total portfolio value and unrealized P&L are unavailable while option positions lack a current authorized premium source.")
    elif not all_equity_prices:
        st.info("At least one open equity position has no current provider quote; total portfolio valuation is withheld.")

    overview_tab, positions_tab, performance_tab, history_tab = st.tabs(
        ["Overview", "Positions", "Performance", "Trade history"]
    )
    with overview_tab:
        st.markdown("#### Open positions")
        if equity_positions or option_positions:
            st.write(f"Equity positions: {len(equity_positions)} · Option positions: {len(option_positions)}")
        else:
            st.info("No open paper positions.")
        st.markdown("#### Recent closes")
        recent = conn.execute(
            "SELECT symbol, quantity, realised_pnl, closed_at FROM equity_closed_positions WHERE account_key = ? ORDER BY closed_at DESC LIMIT 5",
            (account_key,),
        ).fetchall()
        if recent:
            st.dataframe(pd.DataFrame([dict(row) for row in recent]), use_container_width=True, hide_index=True)
        else:
            st.info("No closed positions yet.")

    with positions_tab:
        st.markdown("#### Equity")
        if equity_positions:
            position_rows = []
            for position in equity_positions:
                quote = equity_quotes.get(position["symbol"], {})
                position_rows.append({
                    **position,
                    "last_price": quote.get("last_price"),
                    "freshness": quote.get("status", "UNAVAILABLE"),
                    "market_value": float(quote["last_price"]) * int(position["quantity"]) if quote.get("last_price") is not None else None,
                })
            st.dataframe(pd.DataFrame(position_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No open equity positions.")
        st.markdown("#### Options")
        if option_positions:
            st.dataframe(pd.DataFrame(option_positions), use_container_width=True, hide_index=True)
        else:
            st.info("No open options positions.")

    with performance_tab:
        closed = conn.execute(
            "SELECT closed_at, realised_pnl FROM equity_closed_positions WHERE account_key = ? ORDER BY closed_at",
            (account_key,),
        ).fetchall()
        if closed:
            performance = pd.DataFrame([dict(row) for row in closed])
            performance["closed_at"] = pd.to_datetime(performance["closed_at"], errors="coerce")
            performance = performance.dropna(subset=["closed_at"]).set_index("closed_at")
            if not performance.empty:
                performance["Cumulative realized P&L"] = performance["realised_pnl"].cumsum()
                st.line_chart(performance["Cumulative realized P&L"], use_container_width=True)
                st.dataframe(performance.reset_index(), use_container_width=True, hide_index=True)
        else:
            st.info("Performance charts appear after positions are closed; no sample series is shown.")
        curve = equity_curve(conn, account_key, 30)
        if curve:
            st.markdown("#### Recorded equity curve")
            st.line_chart(curve, use_container_width=True)

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
        with st.form("portfolio_reset_account"):
            start_balance = st.number_input("Starting virtual balance", value=float(account["start_balance"]), min_value=1000.0, step=1000.0)
            confirm_reset = st.checkbox("Reset virtual balances only; keep all trade records.")
            reset = st.form_submit_button("Reset balance")
        if reset:
            if not confirm_reset:
                st.warning("Confirm the balance reset before proceeding.")
            else:
                upsert_account(conn, {
                    "account_key": account_key,
                    "start_balance": start_balance,
                    "current_balance": start_balance,
                    "invested_capital": 0.0,
                    "portfolio_value": start_balance,
                    "currency": account["currency"],
                    "created_at": account["created_at"],
                    "updated_at": account["updated_at"],
                })
                st.success("Virtual balance reset. Trade records were retained.")
                st.rerun()


if __name__ == "__main__":
    app()
