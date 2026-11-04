"""Page 2: Stock Analysis."""

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

from modules.market_data import DEFAULT_FEEDS, market  # noqa: E402
from modules.indicators import IndicatorEngine  # noqa: E402
from modules.charting import render_interactive_chart  # noqa: E402
from utils.ui import set_market_context  # noqa: E402

engine = IndicatorEngine()

DEFAULT_SYMBOLS = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS", "SBIN.NS", "ITC.NS"]


def app():
    st.caption("Search a supported NSE symbol, inspect sourced price history, and open its analysis without changing pages.")

    search = st.text_input("Search NSE stocks", placeholder="Type a name or symbol", key="stock_explorer_search")
    matching_symbols = [
        symbol for symbol in DEFAULT_SYMBOLS
        if not search.strip() or search.strip().lower() in symbol.lower() or search.strip().lower() in DEFAULT_FEEDS.get(symbol, "").lower()
    ]
    if not matching_symbols:
        st.info("No supported NSE stock matches that search.")
        return
    symbol = st.selectbox(
        "Popular NSE stocks",
        options=matching_symbols,
        format_func=lambda x: market.get_symbol_display_name(x),
        key="stock_explorer_symbol",
    )

    start_date = st.date_input("Start date", value=pd.Timestamp("2020-01-01").date())
    end_date = st.date_input("End date", value=pd.Timestamp.today().date())
    intervals = ["1d", "1wk", "1mo"]
    default_interval = st.session_state.get("qe_default_chart_interval", "1d")
    interval = st.selectbox("Interval", intervals, index=intervals.index(default_interval) if default_interval in intervals else 0)

    df = market.download_ohlcv(symbol, str(start_date), str(end_date), interval)
    if df is None or df.empty:
        st.warning(f"No OHLCV data available for {market.get_symbol_display_name(symbol)}.")
        return

    quote = market.get_quotes([symbol]).get(symbol, {})
    timestamp = quote.get("timestamp") or market._timestamp_of(df).isoformat()
    set_market_context(st, market.get_symbol_display_name(symbol), quote.get("source", "yfinance daily history"), quote.get("status", "HISTORICAL"), timestamp)
    st.session_state["qe_selected_instrument"] = symbol
    st.session_state["qe_analysis_payload"] = {"symbol": symbol, "quote": quote}
    summary = st.columns(4)
    summary[0].metric("Latest available", f"{quote.get('last_price'):,.2f}" if quote.get("last_price") is not None else "Unavailable")
    summary[1].metric("Change", f"{quote.get('change_percent'):+.2f}%" if quote.get("change_percent") is not None else "Unavailable")
    summary[2].metric("Freshness", quote.get("status", "UNAVAILABLE"))
    summary[3].metric("Data source", quote.get("source", "yfinance daily history"))
    st.page_link("pages/5_AI_Predictions.py", label="Open AI analysis", icon=":material/insights:")

    eng = engine.describe(df, market.get_symbol_display_name(symbol))
    st.session_state["qe_analysis_payload"] = {
        "instrument": market.get_symbol_display_name(symbol),
        "market": quote,
        "technical": {
            key: eng.get(key)
            for key in ("close", "rsi", "macd", "ema9", "ema20", "ema50", "vwap", "volume", "trend_direction", "support_levels", "resistance_levels", "pattern")
        },
    }

    st.subheader("Indicator Summary")
    summary_keys = [
        "close", "ema9", "ema20", "ema50", "sma20", "sma50", "rsi",
        "rsi_overbought", "rsi_oversold", "macd", "macd_signal", "macd_hist",
        "stoch_rsi", "stoch_rsi_overbought", "stoch_rsi_oversold",
        "bb_upper", "bb_middle", "bb_lower", "atr", "vwap", "volume",
        "volume_change", "trend_direction", "ema_cross_short_long",
        "support_levels", "resistance_levels", "pattern",
    ]
    rows = []
    for key in summary_keys:
        value = eng.get(key)
        if isinstance(value, list):
            rows.append({"Metric": key, "Value": ", ".join(f"{v:.2f}" for v in value[-5:])})
        else:
            rows.append({"Metric": key, "Value": value})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("Price & Indicators")
    render_interactive_chart(
        df,
        title=f"{market.get_symbol_display_name(symbol)} - Daily",
        key="stock_analysis_chart",
        default_indicators=["EMA 9", "EMA 20", "EMA 50", "VWAP", "Bollinger Bands", "Volume"],
        support_levels=eng.get("support_levels"),
        resistance_levels=eng.get("resistance_levels"),
        height=760,
    )

    st.caption(
        "Indicator outputs are deterministic, rule-based computations from the fetched "
        "OHLCV data. They are not verified institutional order flow."
    )


if __name__ == "__main__":
    app()
