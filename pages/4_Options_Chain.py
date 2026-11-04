"""Page 4: Options Chain analysis."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules import options_chain as options_module  # noqa: E402
from modules.options_chain import (  # noqa: E402
    SUPPORTED_INDICES,
    SUPPORTED_STOCKS,
    analyze_contract,
    available_expiries,
    chain_statistics,
    contract_candles,
    load_csv_options,
    load_option_candles,
    nearest_expiry,
    normalize_underlying,
    prepare_chain_table,
)
from modules.charting import render_interactive_chart  # noqa: E402
from modules.market_data import market  # noqa: E402
from modules.database import get_connection  # noqa: E402
from modules.paper_trading import book_option_trade  # noqa: E402
from utils.ui import set_market_context  # noqa: E402

SUPPORTED_ALL = SUPPORTED_INDICES + SUPPORTED_STOCKS
OPTION_TYPES = ["CE", "PE"]


@st.cache_data(ttl=60, show_spinner=False)
def _provider_expiries(symbol: str):
    return options_module.adapter.get_expiries(symbol)


@st.cache_data(ttl=60, show_spinner=False)
def _provider_chain(symbol: str, expiry: str):
    return options_module.get_options_chain_given(symbol, expiry)


def _market_symbol(underlying: str) -> str:
    if underlying == "NIFTY 50":
        return "^NSEI"
    if underlying == "BANK NIFTY":
        return "^NSEBANK"
    return f"{underlying}.NS"


def _number(value, digits: int = 2) -> str:
    return "Unavailable" if value is None or pd.isna(value) else f"{float(value):,.{digits}f}"


def _optional_number(value):
    try:
        return float(value) if value is not None and pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _highlight_chain(table: pd.DataFrame, stats: dict):
    def styles(row):
        result = []
        for column in table.columns:
            color = "background-color: #123b45;" if row.get("ATM") else ""
            highlight = None
            if column == "CE OI":
                highlight = stats.get("max_ce_oi")
            elif column == "PE OI":
                highlight = stats.get("max_pe_oi")
            elif column in {"CE Change in OI", "PE Change in OI", "CE Volume", "PE Volume"}:
                key = "max_change_oi" if "Change in OI" in column else "max_volume"
                highlight = stats.get(key)
            if highlight and row.get("Strike") == highlight.get("strike") and (
                "option_type" not in highlight or column.startswith(highlight["option_type"])
            ):
                color = "background-color: #5b3a12; color: #fff3cd;"
            result.append(color)
        return result

    return table.style.apply(styles, axis=1)


def app():
    st.caption(
        "Option values and history are shown only when returned by the configured provider "
        "or supplied in a contract-identified CSV. No underlying candles are used as option premiums."
    )

    underlying = st.selectbox("Underlying", options=SUPPORTED_ALL, index=0, key="option_underlying")
    uploads = st.columns(2)
    with uploads[0]:
        chain_file = st.file_uploader(
            "Options chain CSV",
            type=["csv"],
            key="option_chain_csv",
            help="Requires symbol, expiry, strike, option_type, and ltp; other fields may be absent.",
        )
    with uploads[1]:
        candle_file = st.file_uploader(
            "Historical option candles CSV",
            type=["csv"],
            key="option_candles_csv",
            help="Requires exact contract identity plus timestamp, OHLC, and volume columns.",
        )

    chain_data = pd.DataFrame()
    chain_status = "UNAVAILABLE"
    chain_source = "yfinance"
    chain_timestamp = None
    chain_error = None
    if chain_file is not None:
        chain_result = load_csv_options(chain_file.getvalue())
        if chain_result.get("available"):
            chain_data = chain_result["data"]
            chain_status = chain_result["status"]
            chain_source = chain_result["source"]
            chain_timestamp = chain_result.get("timestamp")
        else:
            chain_error = chain_result.get("error")

    candle_data = pd.DataFrame()
    candle_result = None
    if candle_file is not None:
        candle_result = load_option_candles(candle_file.getvalue())
        if candle_result.get("available"):
            candle_data = candle_result["data"]
        else:
            st.warning(candle_result.get("error", "Invalid option candle CSV."))

    if chain_error:
        st.warning(f"Chain CSV unavailable: {chain_error}")

    market_symbol = _market_symbol(underlying)
    quote = market.get_quotes([market_symbol]).get(market_symbol, {})
    underlying_price = quote.get("last_price") if quote.get("available") else None
    set_market_context(
        st,
        underlying,
        quote.get("source", "yfinance daily history"),
        quote.get("status", "UNAVAILABLE"),
        quote.get("timestamp"),
    )
    st.session_state["qe_selected_instrument"] = underlying
    quote_columns = st.columns(3)
    quote_columns[0].metric("Underlying", underlying)
    quote_columns[1].metric("Underlying price", _number(underlying_price))
    quote_columns[2].metric("Underlying data", quote.get("status", "UNAVAILABLE"))
    st.caption(
        f"Underlying source: {quote.get('source', 'yfinance daily history')} · "
        f"As of: {quote.get('timestamp') or 'timestamp unavailable'}"
    )

    provider_expiries = []
    provider_data = pd.DataFrame()
    if chain_data.empty:
        provider_expiries = _provider_expiries(underlying)
    csv_expiries = available_expiries(chain_data, underlying) if not chain_data.empty else []
    candle_expiries = available_expiries(candle_data, underlying) if not candle_data.empty else []
    expiry_values = csv_expiries or provider_expiries or candle_expiries
    selected_expiry = nearest_expiry(expiry_values, allow_past=bool(csv_expiries or candle_expiries))

    if not csv_expiries and selected_expiry:
        provider_result = _provider_chain(underlying, selected_expiry)
        if provider_result.get("available"):
            provider_data = provider_result["data"]
            chain_status = provider_result.get("status", "DELAYED")
            chain_source = provider_result.get("source", "yfinance options")
            chain_timestamp = provider_result.get("timestamp")
        else:
            provider_expiries = []

    if len(expiry_values) > 1:
        selected_expiry = st.selectbox(
            "Expiry",
            options=expiry_values,
            index=expiry_values.index(selected_expiry) if selected_expiry in expiry_values else 0,
            key=f"expiry_{normalize_underlying(underlying)}",
        )
        if not csv_expiries:
            provider_result = _provider_chain(underlying, selected_expiry)
            provider_data = provider_result.get("data", pd.DataFrame()) if provider_result.get("available") else pd.DataFrame()
            chain_status = provider_result.get("status", "UNAVAILABLE")
            chain_source = provider_result.get("source", "yfinance")
            chain_timestamp = provider_result.get("timestamp")
    elif selected_expiry:
        st.caption(f"Nearest available expiry: **{selected_expiry}**")

    if csv_expiries:
        chain_data = chain_data[chain_data["expiry"].astype(str).eq(str(selected_expiry))]
        source_data = chain_data
        chain_status = "CSV UPLOAD"
    else:
        source_data = provider_data
        if not source_data.empty:
            chain_status = "DELAYED"
    if source_data.empty and not candle_data.empty and not csv_expiries and not provider_data.empty:
        source_data = provider_data

    if not expiry_values:
        st.warning(
            "No upcoming expiry was returned by the configured provider. For NIFTY/BANK NIFTY, "
            "yfinance does not currently expose a reliable NSE option chain. Upload a permitted "
            "chain CSV to select a sourced expiry; no expiry is generated here."
        )
        if not candle_expiries:
            st.info("No contract-identified option history is available. The underlying index chart will not be substituted.")

    if selected_expiry:
        status_text = f"{chain_status} · {chain_source} · {chain_timestamp or 'source timestamp unavailable'}"
        st.caption(f"Selected expiry: {selected_expiry} · Chain source: {status_text}")

    combined_contract_data = source_data if not source_data.empty else candle_data
    strikes_frame = combined_contract_data
    if selected_expiry and not strikes_frame.empty:
        strikes_frame = strikes_frame[strikes_frame["expiry"].astype(str).eq(str(selected_expiry))]
    strikes = sorted(pd.to_numeric(strikes_frame.get("strike", pd.Series(dtype=float)), errors="coerce").dropna().unique().tolist())
    if not strikes:
        st.info("Strike selection becomes available when the provider or an uploaded CSV supplies valid contract strikes.")
        return

    atm_strike = min(strikes, key=lambda value: abs(value - underlying_price)) if underlying_price is not None else strikes[len(strikes) // 2]
    if underlying_price is None:
        st.caption("ATM classification unavailable because the underlying price could not be fetched; the central strike is selected for convenience only.")
    contract_columns = st.columns([1.2, 1, 1])
    with contract_columns[0]:
        option_type = st.radio("Option type", OPTION_TYPES, horizontal=True, key="selected_option_type")
    with contract_columns[1]:
        if len(strikes) > 2:
            max_strike_range = min(15, len(strikes) - 1)
            strike_range = st.slider(
                "Strikes around ATM",
                min_value=1,
                max_value=max_strike_range,
                value=min(5, max_strike_range),
                key="option_strike_range",
            )
        else:
            strike_range = 0
            st.caption("Showing all available strikes; a range control needs at least three strikes.")
    with contract_columns[2]:
        strike = st.selectbox("Strike", options=strikes, index=strikes.index(atm_strike), format_func=lambda value: f"{value:,.2f}", key="selected_option_strike")

    if not source_data.empty:
        table = prepare_chain_table(source_data, underlying, selected_expiry, underlying_price, strike_range)
        stats = chain_statistics(source_data, underlying, selected_expiry)
        st.subheader("Options chain")
        metric_columns = st.columns(5)
        metric_columns[0].metric("PCR (OI)", _number(stats.get("pcr"), 3))
        metric_columns[1].metric("Max pain", _number(stats.get("max_pain")))
        max_ce = stats.get("max_ce_oi")
        max_pe = stats.get("max_pe_oi")
        metric_columns[2].metric("Highest CE OI", f"{max_ce['strike']:,.0f}" if max_ce else "Unavailable")
        metric_columns[3].metric("Highest PE OI", f"{max_pe['strike']:,.0f}" if max_pe else "Unavailable")
        max_change = stats.get("max_change_oi")
        max_volume = stats.get("max_volume")
        metric_columns[4].metric("Highest change OI / volume", "Unavailable" if not max_change and not max_volume else "See highlighted strikes")
        if not table.empty:
            st.dataframe(_highlight_chain(table, stats), use_container_width=True, hide_index=True)
        else:
            st.info("No valid chain rows were returned for this expiry.")

    contract_row = None
    if not source_data.empty:
        matches = source_data[
            source_data["strike"].eq(float(strike))
            & source_data["option_type"].eq(option_type)
            & source_data["expiry"].astype(str).eq(str(selected_expiry))
        ]
        if not matches.empty:
            contract_row = matches.iloc[-1]

    history = contract_candles(candle_data, underlying, selected_expiry, strike, option_type) if not candle_data.empty else pd.DataFrame()
    candle_source = candle_result.get("source", "CSV UPLOAD") if candle_result else "UNAVAILABLE"
    candle_timestamp = candle_result.get("timestamp") if candle_result else None
    provider_interval = None
    if history.empty:
        provider_intervals = options_module.adapter.get_available_candle_intervals(
            underlying, selected_expiry, float(strike), option_type
        )
        if provider_intervals:
            provider_interval = st.selectbox("Available option-candle interval", provider_intervals, key="provider_option_interval")
            provider_candles = options_module.adapter.get_contract_candles(
                underlying, selected_expiry, float(strike), option_type, provider_interval
            )
            if provider_candles.get("available"):
                candle_source = provider_candles.get("source", "provider")
                candle_timestamp = provider_candles.get("timestamp")
                history = contract_candles(
                    provider_candles["data"], underlying, selected_expiry, strike, option_type
                )
    contract_symbol = f"{underlying} {float(strike):g} {option_type}"
    st.session_state["qe_selected_instrument"] = contract_symbol
    if contract_row is not None and contract_row.get("contractSymbol"):
        contract_symbol = str(contract_row["contractSymbol"])
    st.subheader("Selected option contract")
    st.markdown(f"**{contract_symbol}** · Expiry {selected_expiry} · Strike {_number(strike, 2)} · {option_type}")
    st.caption(
        f"Contract data: {chain_source} · Status: {chain_status} · "
        f"Source timestamp: {chain_timestamp or 'unavailable'}"
    )
    latest_close = float(history["close"].iloc[-1]) if not history.empty else None
    observed_ltp = contract_row.get("ltp") if contract_row is not None else latest_close
    if observed_ltp is None or pd.isna(observed_ltp):
        observed_ltp = latest_close
    contract_metrics = st.columns(7)
    contract_metrics[0].metric("LTP / Close", _number(observed_ltp))
    contract_metrics[1].metric("Change", _number(contract_row.get("change") if contract_row is not None else None))
    contract_metrics[2].metric("Volume", _number(contract_row.get("volume") if contract_row is not None else (history["volume"].iloc[-1] if not history.empty and "volume" in history else None), 0))
    contract_metrics[3].metric("OI", _number(contract_row.get("open_interest") if contract_row is not None else None, 0))
    contract_metrics[4].metric("Change in OI", _number(contract_row.get("change_in_open_interest") if contract_row is not None else None, 0))
    contract_metrics[5].metric("IV", f"{_number(contract_row.get('iv'))}%" if contract_row is not None and pd.notna(contract_row.get("iv")) else "Unavailable")
    greek_values = " · ".join(f"{key} {_number(contract_row.get(key), 4)}" for key in ("delta", "gamma", "theta", "vega") if contract_row is not None and pd.notna(contract_row.get(key)))
    contract_metrics[6].metric("Greeks", greek_values or "Unavailable")

    st.subheader("Option premium history")
    if history.empty:
        st.info(
            "Historical candles for this exact option contract are unavailable. Upload a CSV with "
            "symbol, expiry, strike, option_type, timestamp, open, high, low, close, and volume. "
            "No underlying candles are substituted."
        )
    else:
        st.caption(
            f"Option candle source: {candle_source} · "
            f"Source timestamp: {candle_timestamp or 'unavailable'}"
        )
        interval_options = sorted(history["interval"].dropna().astype(str).unique().tolist()) if "interval" in history else []
        if interval_options:
            selected_interval = st.selectbox("Available candle interval", interval_options, key="option_candle_interval")
            history = history[history["interval"].astype(str).eq(selected_interval)]
        elif provider_interval is None:
            st.caption("Showing the uploaded candle cadence; the CSV did not declare an interval.")
        close = pd.to_numeric(history["close"], errors="coerce").dropna()
        if len(close) >= 2:
            absolute_change = float(close.iloc[-1] - close.iloc[-2])
            percent_change = absolute_change / float(close.iloc[-2]) * 100 if close.iloc[-2] else None
            price_columns = st.columns(6)
            price_columns[0].metric("Open", _number(history["open"].iloc[-1]))
            price_columns[1].metric("High", _number(history["high"].iloc[-1]))
            price_columns[2].metric("Low", _number(history["low"].iloc[-1]))
            price_columns[3].metric("Close", _number(close.iloc[-1]))
            price_columns[4].metric("Price change", _number(absolute_change))
            price_columns[5].metric("Change %", f"{percent_change:+.2f}%" if percent_change is not None else "Unavailable")
        render_interactive_chart(
            history,
            f"{contract_symbol} · Premium candles · {candle_source}",
            key="option_premium_chart",
            default_indicators=["EMA 9", "EMA 20", "Volume", "RSI", "MACD"],
            height=820,
        )

    analysis_row = contract_row
    if analysis_row is None and not history.empty:
        candle_change = float(history["close"].iloc[-1] - history["close"].iloc[-2]) if len(history) > 1 else None
        analysis_row = pd.Series({
            "symbol": underlying,
            "expiry": selected_expiry,
            "strike": float(strike),
            "option_type": option_type,
            "ltp": latest_close,
            "change": candle_change,
        })
    analysis = analyze_contract(analysis_row, history, source_data, underlying_price)
    st.session_state["qe_selected_instrument"] = contract_symbol
    st.session_state["qe_analysis_payload"] = {
        "instrument": contract_symbol,
        "expiry": selected_expiry,
        "market": {
            "premium": _optional_number(observed_ltp),
            "change": _optional_number(contract_row.get("change") if contract_row is not None else None),
            "volume": _optional_number(contract_row.get("volume") if contract_row is not None else None),
            "open_interest": _optional_number(contract_row.get("open_interest") if contract_row is not None else None),
            "change_in_open_interest": _optional_number(contract_row.get("change_in_open_interest") if contract_row is not None else None),
            "iv": _optional_number(contract_row.get("iv") if contract_row is not None else None),
            "source": chain_source,
            "freshness": chain_status,
            "timestamp": chain_timestamp,
        },
        "analysis": {key: analysis[key] for key in ("premium_trend", "ema_trend", "rsi_momentum", "macd_momentum", "volume_behavior", "oi_analysis", "iv_condition", "moneyness", "overall", "supporting", "contradicting")},
        "chain_context": stats if not source_data.empty else {},
    }
    st.subheader("Option Analysis")
    st.caption("Rule-based interpretation of supplied contract and candle data; not a trade recommendation.")
    analysis_columns = st.columns(3)
    analysis_columns[0].metric("Premium trend", analysis["premium_trend"])
    analysis_columns[1].metric("EMA trend", analysis["ema_trend"])
    analysis_columns[2].metric("Overall assessment", analysis["overall"])
    st.write(
        f"Momentum: RSI {analysis['rsi_momentum']} · MACD {analysis['macd_momentum']} · "
        f"Volume {analysis['volume_behavior']} · OI {analysis['oi_analysis']} · "
        f"IV {analysis['iv_condition']} · Moneyness {analysis['moneyness']}"
    )
    evidence = analysis["supporting"] + analysis["contradicting"]
    if evidence:
        st.write("Evidence: " + " ".join(evidence))
    else:
        st.info("Insufficient supplied values to form an evidence-based option assessment.")

    expiry_date = pd.to_datetime(selected_expiry, errors="coerce")
    tradable_expiry = not pd.isna(expiry_date) and expiry_date.date() >= datetime.now(timezone.utc).date()
    if selected_expiry and tradable_expiry and observed_ltp is not None and pd.notna(observed_ltp) and float(observed_ltp) > 0:
        st.subheader("Open option paper trade")
        st.caption("Simulated order only. Quantity is in option units; lot size is not assumed unless the source verifies it.")
        with st.form("open_option_paper_trade"):
            quantity = st.number_input("Option units", min_value=1, value=1, step=1)
            fees = st.number_input("Fees (INR)", min_value=0.0, value=float(st.session_state.get("qe_option_fees", 0.0)), step=1.0)
            st.write(f"Review: BUY {int(quantity)} {contract_symbol} @ {_number(observed_ltp)} + fees {_number(fees)}")
            submitted = st.form_submit_button("Confirm simulated option order")
        if submitted:
            database = get_connection(_PROJECT_ROOT / "data" / "paper_trading.db")
            try:
                result = book_option_trade(
                    database,
                    st.session_state.get("account_key", "quantedge_user"),
                    underlying,
                    selected_expiry,
                    float(strike),
                    option_type,
                    int(quantity),
                    float(observed_ltp),
                    float(fees),
                )
                st.success(f"Simulated option order recorded: {result['trade_id']}")
            except Exception as exc:
                st.error(f"Option paper order was not saved: {exc}")
            finally:
                database.close()
    elif selected_expiry and observed_ltp is not None and pd.notna(observed_ltp) and not tradable_expiry:
        st.info("Historical premium data is available, but this contract is expired and cannot be opened as a new paper trade.")


if __name__ == "__main__":
    app()
