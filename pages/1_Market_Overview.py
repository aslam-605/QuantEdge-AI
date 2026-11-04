"""Page 1: Market Overview."""

from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules.market_data import DEFAULT_FEEDS, market  # noqa: E402
from modules.charting import render_interactive_chart  # noqa: E402
from utils.ui import set_market_context  # noqa: E402

DEFAULT_WATCHLIST = [
    "^NSEI",
    "^NSEBANK",
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "TCS.NS",
]


def _read_paper_overview(quotes: dict):
    db_path = _PROJECT_ROOT / "data" / "paper_trading.db"
    if not db_path.exists():
        return None, []
    account_key = st.session_state.get("account_key", "quantedge_user")
    connection = None
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        account = connection.execute(
            "SELECT account_key FROM paper_accounts WHERE account_key = ?", (account_key,)
        ).fetchone()
        if account is None:
            return None, []
        realized = float(connection.execute(
            "SELECT COALESCE(SUM(realised_pnl), 0) FROM equity_closed_positions WHERE account_key = ?",
            (account_key,),
        ).fetchone()[0])
        positions = [dict(row) for row in connection.execute(
            "SELECT symbol, quantity, avg_entry_price FROM equity_positions WHERE account_key = ? ORDER BY symbol",
            (account_key,),
        ).fetchall()]
    except sqlite3.Error:
        return None, []
    finally:
        if connection is not None:
            connection.close()

    unrealized = 0.0
    for position in positions:
        quote = quotes.get(position["symbol"], {})
        price = quote.get("last_price")
        if price is None:
            return None, positions
        unrealized += (float(price) - float(position["avg_entry_price"])) * int(position["quantity"])
    return realized + unrealized, positions


def app():
    st.caption("Indian market overview from yfinance daily history. Data is not represented as a real-time feed.")

    config = st.session_state.setdefault("settings", {})
    watchlist = config.get("watchlist", DEFAULT_WATCHLIST)
    if isinstance(watchlist, str):
        watchlist = [x.strip() for x in watchlist.split(",") if x.strip()]
    symbols = list(DEFAULT_FEEDS)
    watchlist = [symbol for symbol in watchlist if symbol in symbols]
    watchlist = list(dict.fromkeys(watchlist + DEFAULT_WATCHLIST))

    st.subheader("Watchlist")
    added = st.multiselect(
        "Symbols to monitor",
        options=symbols,
        default=watchlist,
        format_func=lambda x: market.get_symbol_display_name(x),
        key="qe_market_watchlist",
    )
    config["watchlist"] = added
    selected_symbols = list(dict.fromkeys(["^NSEI", "^NSEBANK", "NIFTY_FIN_SERVICE.NS"] + added))

    with st.spinner("Checking symbol availability..."):
        quotes = market.get_quotes(selected_symbols)

    _, open_positions = _read_paper_overview(quotes)
    held_symbols = [position["symbol"] for position in open_positions if position["symbol"] not in quotes]
    if held_symbols:
        quotes.update(market.get_quotes(held_symbols))
    portfolio_pnl, open_positions = _read_paper_overview(quotes)
    nifty_quote = quotes.get("^NSEI", {})
    set_market_context(
        st,
        "NIFTY 50 · BANK NIFTY",
        "yfinance daily history",
        nifty_quote.get("status", "UNAVAILABLE"),
        nifty_quote.get("timestamp"),
    )
    st.session_state["qe_market_snapshot"] = quotes

    st.subheader("Market at a glance")
    card_columns = st.columns(4)
    index_cards = [
        ("^NSEI", "NIFTY 50"),
        ("^NSEBANK", "BANK NIFTY"),
        ("NIFTY_FIN_SERVICE.NS", "FINNIFTY"),
    ]
    for column, (symbol, label) in zip(card_columns[:3], index_cards):
        quote = quotes.get(symbol, {})
        with column:
            if label == "FINNIFTY" and not quote.get("available"):
                st.metric(label, "Unavailable")
                st.caption("No recent provider data")
                continue
            value = quote.get("last_price")
            delta = quote.get("change")
            delta_percent = quote.get("change_percent")
            value_text = f"{value:,.2f}" if value is not None else "Unavailable"
            delta_text = None
            if delta is not None:
                delta_text = f"{delta:+,.2f}"
                if delta_percent is not None:
                    delta_text += f" ({delta_percent:+.2f}%)"
            st.metric(label, value_text, delta=delta_text)
            if quote.get("available"):
                st.caption(
                    f"Source: {quote.get('source', 'Unknown')} · Freshness: {quote.get('status', 'UNKNOWN')} · "
                    f"As of {quote.get('timestamp') or 'timestamp unavailable'}"
                )
            else:
                st.caption("Source: yfinance · Freshness: UNAVAILABLE")

    with card_columns[3]:
        st.metric("Portfolio P&L", f"{portfolio_pnl:+,.2f} INR" if portfolio_pnl is not None else "Unavailable")
        st.caption("Realized + quoted unrealized · paper account")

    movers = [
        {
            "Symbol": market.get_symbol_display_name(symbol),
            "Change %": quote.get("change_percent"),
            "Last": quote.get("last_price"),
            "Freshness": quote.get("status", "UNAVAILABLE"),
        }
        for symbol, quote in quotes.items()
        if quote.get("available") and quote.get("change_percent") is not None
    ]
    if movers:
        movers.sort(key=lambda row: row["Change %"])
        mover_columns = st.columns(2)
        with mover_columns[0]:
            st.markdown("#### Top decliners · selected watchlist")
            st.dataframe(movers[:3], use_container_width=True, hide_index=True)
        with mover_columns[1]:
            st.markdown("#### Top gainers · selected watchlist")
            st.dataframe(list(reversed(movers[-3:])), use_container_width=True, hide_index=True)

    st.subheader("Market Summary")
    available_indices = [quotes.get(symbol, {}) for symbol in ("^NSEI", "^NSEBANK")]
    available_indices = [quote for quote in available_indices if quote.get("available")]
    if not available_indices:
        st.info("Market summary is unavailable because neither index returned usable market data.")
    else:
        rising = sum(1 for quote in available_indices if (quote.get("change") or 0) > 0)
        falling = sum(1 for quote in available_indices if (quote.get("change") or 0) < 0)
        if rising == len(available_indices):
            summary = "Both available major indices are higher than their previous daily close." if len(available_indices) == 2 else "The available major index is higher than its previous daily close."
        elif falling == len(available_indices):
            summary = "Both available major indices are lower than their previous daily close." if len(available_indices) == 2 else "The available major index is lower than its previous daily close."
        else:
            summary = "Major indices are mixed or unchanged versus their previous daily closes."
        st.write(summary)
        st.caption("Summary reflects only the latest returned daily bars; it is not an intraday market assessment.")

    st.subheader("Watchlist")
    watchlist_rows = []
    for symbol in added:
        quote = quotes.get(symbol, {})
        watchlist_rows.append(
            {
                "Symbol": market.get_symbol_display_name(symbol),
                "Last Price": quote.get("last_price"),
                "Change": quote.get("change"),
                "% Change": quote.get("change_percent"),
                "Freshness": quote.get("status", "UNAVAILABLE"),
                "Source": quote.get("source", "yfinance daily history"),
                "As Of": quote.get("timestamp") or "-",
            }
        )
    if watchlist_rows:
        st.dataframe(watchlist_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Your watchlist is empty. Select symbols in the sidebar to monitor them.")

    st.subheader("Open paper positions")
    if open_positions:
        position_rows = []
        for position in open_positions:
            quote = quotes.get(position["symbol"], {})
            position_rows.append({
                "Symbol": market.get_symbol_display_name(position["symbol"]),
                "Quantity": position["quantity"],
                "Average entry": position["avg_entry_price"],
                "Latest available": quote.get("last_price"),
                "Freshness": quote.get("status", "UNAVAILABLE"),
            })
        st.dataframe(position_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No open equity paper positions.")

    st.subheader("Historical Candlestick Chart")
    chart_options = list(dict.fromkeys(selected_symbols))
    chart_symbol = st.selectbox(
        "Chart symbol",
        options=chart_options,
        format_func=market.get_symbol_display_name,
    )
    chart_period = st.selectbox("Chart period", ["1M", "3M", "6M", "1Y", "5Y"], index=3)
    chart_intervals = ["1d", "1wk", "1mo"]
    default_interval = st.session_state.get("qe_default_chart_interval", "1d")
    chart_interval = st.selectbox(
        "Chart timeframe",
        chart_intervals,
        index=chart_intervals.index(default_interval) if default_interval in chart_intervals else 0,
    )
    today = datetime.now(timezone.utc).date()
    period_days = {"1M": 31, "3M": 92, "6M": 183, "1Y": 365, "5Y": 365 * 5}
    start_date = (today - timedelta(days=period_days[chart_period])).isoformat()
    end_date = (today + timedelta(days=1)).isoformat()
    with st.spinner(f"Loading historical chart for {market.get_symbol_display_name(chart_symbol)}..."):
        chart_data = market.download_ohlcv(chart_symbol, start_date, end_date, chart_interval)
    if chart_data is None or chart_data.empty:
        st.info(f"No historical candlestick data is available for {market.get_symbol_display_name(chart_symbol)} right now.")
    else:
        render_interactive_chart(
            chart_data,
            title=f"{market.get_symbol_display_name(chart_symbol)} · {chart_interval}",
            key="market_overview_chart",
            default_indicators=["EMA 9", "EMA 20", "Volume"],
            height=720,
        )

    insight_columns = st.columns(2)
    with insight_columns[0]:
        st.subheader("Latest AI insight")
        st.write(st.session_state.get("qe_last_ai_insight", "No AI analysis has been requested in this session."))
    with insight_columns[1]:
        st.subheader("Latest trading signal")
        st.write(st.session_state.get("qe_last_signal", "No validated signal is available in this session."))


if __name__ == "__main__":
    app()
