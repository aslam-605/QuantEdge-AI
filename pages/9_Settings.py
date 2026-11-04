"""Page 9: Settings and AI configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules.ai_assistant import OllamaAssistant  # noqa: E402
from modules.charting import CHART_INDICATORS  # noqa: E402
from modules.market_data import DEFAULT_FEEDS, market  # noqa: E402


@st.cache_resource(show_spinner=False)
def _assistant_for_model(model_name: str):
    return OllamaAssistant(model=model_name)


def app():
    st.caption("Session preferences for this browser session; trading records remain in SQLite.")
    appearance_tab, data_tab, chart_tab, ai_tab, trading_tab = st.tabs(
        ["Appearance", "Market data", "Charts", "AI models", "Paper trading"]
    )

    with appearance_tab:
        st.subheader("Appearance")
        st.write(f"Current theme: **{st.session_state.get('qe_theme', 'Dark')}**")
        st.caption("Switch Dark / Light in the application header.")
        st.info("The theme toggle changes presentation only; market data and paper-trading records are unchanged.")

    with data_tab:
        st.subheader("Market data")
        refresh_seconds = st.select_slider(
            "Market data cache refresh",
            options=[15, 30, 60, 120, 300],
            value=int(st.session_state.get("qe_refresh_seconds", 30)),
            format_func=lambda value: f"{value} seconds",
        )
        st.session_state["qe_refresh_seconds"] = refresh_seconds
        market.set_cache_ttl(refresh_seconds)
        watchlist = st.multiselect(
            "Default watchlist",
            options=list(DEFAULT_FEEDS),
            default=st.session_state.get("settings", {}).get("watchlist", ["^NSEI", "^NSEBANK", "RELIANCE.NS", "HDFCBANK.NS"]),
            format_func=market.get_symbol_display_name,
        )
        st.session_state.setdefault("settings", {})["watchlist"] = watchlist
        provider_quotes = market.get_quotes(["^NSEI", "^NSEBANK", "NIFTY_FIN_SERVICE.NS"])
        provider_rows = [
            {
                "Instrument": market.get_symbol_display_name(symbol),
                "Status": quote.get("status", "UNAVAILABLE"),
                "Source": quote.get("source", "yfinance daily history"),
                "Timestamp": quote.get("timestamp") or "Unavailable",
            }
            for symbol, quote in provider_quotes.items()
        ]
        st.dataframe(provider_rows, use_container_width=True, hide_index=True)
        st.caption("yfinance daily bars are historical/delayed and are never labeled real-time.")
        st.write(f"Data directory: `{_PROJECT_ROOT / 'data'}`")

    with chart_tab:
        st.subheader("Chart preferences")
        st.session_state["qe_default_chart_indicators"] = st.multiselect(
            "Default visible indicators",
            options=CHART_INDICATORS,
            default=st.session_state.get("qe_default_chart_indicators", ["EMA 9", "EMA 20", "Volume"]),
        )
        st.session_state["qe_default_chart_interval"] = st.selectbox(
            "Default historical timeframe",
            ["1d", "1wk", "1mo"],
            index=["1d", "1wk", "1mo"].index(st.session_state.get("qe_default_chart_interval", "1d")),
        )
        st.caption("Individual charts only offer intervals supported by their selected data source.")

    with ai_tab:
        st.subheader("AI and ML")
        model_name = st.text_input(
            "Ollama model",
            value=st.session_state.get("ollama_model", "qwen3.5:4b"),
            help="Local Ollama model tag.",
        )
        st.session_state["ollama_model"] = model_name
        assistant = _assistant_for_model(model_name)
        status = assistant.status()
        ai_columns = st.columns(2)
        ai_columns[0].metric("Ollama service", "Connected" if status["connected"] else "Unavailable")
        ai_columns[1].metric("Model", "Ready" if status["available"] else "Unavailable")
        ml_settings = st.session_state.setdefault("qe_ml_settings", {"lookahead_days": 5, "bear_threshold": -0.03, "bull_threshold": 0.03})
        ml_columns = st.columns(3)
        ml_settings["lookahead_days"] = ml_columns[0].selectbox("Prediction horizon", [3, 5, 10, 20], index=[3, 5, 10, 20].index(ml_settings.get("lookahead_days", 5)))
        ml_settings["bear_threshold"] = ml_columns[1].number_input("Bear threshold", min_value=-0.20, max_value=-0.005, value=float(ml_settings.get("bear_threshold", -0.03)), step=0.005, format="%.3f")
        ml_settings["bull_threshold"] = ml_columns[2].number_input("Bull threshold", min_value=0.005, max_value=0.20, value=float(ml_settings.get("bull_threshold", 0.03)), step=0.005, format="%.3f")
        st.write(f"Validated model candidate: `{_PROJECT_ROOT / 'models' / 'quantedge_rf_v2.joblib'}`")
        st.caption("The legacy model is preserved. Corrected model training is an explicit action on AI Predictions.")

    with trading_tab:
        st.subheader("Paper-trading defaults")
        st.session_state["qe_brokerage"] = st.number_input(
            "Estimated brokerage per equity order (INR)",
            min_value=0.0,
            value=float(st.session_state.get("qe_brokerage", 20.0)),
            step=1.0,
        )
        st.session_state["qe_option_fees"] = st.number_input(
            "Estimated option-order charges (INR)",
            min_value=0.0,
            value=float(st.session_state.get("qe_option_fees", 0.0)),
            step=1.0,
        )
        st.caption("Defaults affect new simulated orders only; balances and recorded trades are not changed here.")


if __name__ == "__main__":
    app()
