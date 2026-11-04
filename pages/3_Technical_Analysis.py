"""Page 3: Technical Analysis."""

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

from modules.market_data import market  # noqa: E402
from modules.indicators import IndicatorEngine  # noqa: E402
from modules.charting import render_interactive_chart  # noqa: E402
from utils.ui import set_market_context  # noqa: E402

engine = IndicatorEngine()

DEFAULT_SYMBOLS = ["RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS"]

EMA_LABELS = {
    "ema9": "EMA 9",
    "ema20": "EMA 20",
    "ema50": "EMA 50",
    "sma20": "SMA 20",
    "sma50": "SMA 50",
}
VOL_LABELS = {
    "volume": "Volume",
    "volume_change": "Volume % Change",
}


def app():
    st.caption("Indicator values, trend direction, momentum, and simple candlestick-pattern screening.")

    symbol = st.selectbox(
        "Symbol",
        options=DEFAULT_SYMBOLS,
        format_func=lambda x: market.get_symbol_display_name(x),
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

    eng = engine.describe(df, market.get_symbol_display_name(symbol))
    st.session_state["qe_analysis_payload"] = {
        "instrument": market.get_symbol_display_name(symbol),
        "market": quote,
        "technical": {
            key: eng.get(key)
            for key in ("close", "rsi", "macd", "ema9", "ema20", "ema50", "vwap", "volume", "trend_direction", "support_levels", "resistance_levels", "pattern")
        },
    }

    st.subheader("Indicator Values & Readings")
    rows = []
    rsi = eng.get("rsi")
    rows.append({"Indicator": "RSI (14)", "Value": rsi, "Interpretation": "Overbought" if eng.get("rsi_overbought") else ("Oversold" if eng.get("rsi_oversold") else "Neutral")})
    stoch = eng.get("stoch_rsi")
    rows.append({"Indicator": "Stochastic RSI", "Value": stoch, "Interpretation": "Overbought" if eng.get("stoch_rsi_overbought") else ("Oversold" if eng.get("stoch_rsi_oversold") else "Neutral")})
    rows.append({"Indicator": "MACD", "Value": eng.get("macd"), "Interpretation": "Bullish" if (eng.get("macd") or 0) > (eng.get("macd_signal") or 0) else "Bearish"})
    rows.append({"Indicator": "EMA 9", "Value": eng.get("ema9")})
    rows.append({"Indicator": "EMA 20", "Value": eng.get("ema20")})
    rows.append({"Indicator": "EMA 50", "Value": eng.get("ema50")})
    rows.append({"Indicator": "SMA 20", "Value": eng.get("sma20")})
    rows.append({"Indicator": "SMA 50", "Value": eng.get("sma50")})
    rows.append({"Indicator": "Bollinger Middle", "Value": eng.get("bb_middle")})
    rows.append({"Indicator": "Bollinger Upper", "Value": eng.get("bb_upper")})
    rows.append({"Indicator": "Bollinger Lower", "Value": eng.get("bb_lower")})
    rows.append({"Indicator": "ATR", "Value": eng.get("atr")})
    rows.append({"Indicator": "VWAP", "Value": eng.get("vwap")})
    rows.append({"Indicator": "Volume", "Value": eng.get("volume")})
    rows.append({"Indicator": "Volume Change", "Value": eng.get("volume_change")})
    rows.append({"Indicator": "Trend Direction", "Value": eng.get("trend_direction")})
    rows.append({"Indicator": "Last Close", "Value": eng.get("close")})
    rows.append({"Indicator": "Candlestick Pattern", "Value": eng.get("pattern")})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    render_interactive_chart(
        df,
        title=f"{market.get_symbol_display_name(symbol)} - Technical Chart",
        key="technical_analysis_chart",
        default_indicators=["EMA 9", "EMA 20", "EMA 50", "VWAP", "Bollinger Bands", "RSI", "MACD", "Volume"],
        support_levels=eng.get("support_levels"),
        resistance_levels=eng.get("resistance_levels"),
        height=820,
    )

    if eng.get("pattern") != "INSUFFICIENT_DATA":
        st.subheader("Candlestick Pattern Screening")
        st.info(f"Detected pattern: {eng.get('pattern')}")

    support = eng.get("support_levels", [])
    resistance = eng.get("resistance_levels", [])
    if support or resistance:
        st.subheader("Support & Resistance")
        st.metric("Last Close", eng.get("close"))
        if support:
            st.metric("Support Levels", ", ".join(f"{v:.2f}" for v in support[-5:]))
        if resistance:
            st.metric("Resistance Levels", ", ".join(f"{v:.2f}" for v in resistance[-5:]))

    st.caption(
        "All indicators are deterministic, rule-based technical interpretations. "
        "They are not verified institutional order flow and should not be taken as trade advice."
    )


if __name__ == "__main__":
    app()
