"""Page 5: AI Predictions pipeline."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules.ai_assistant import OllamaAssistant  # noqa: E402
from modules.charting import render_interactive_chart  # noqa: E402
from modules.database import get_connection  # noqa: E402
from modules.indicators import IndicatorEngine  # noqa: E402
from modules.market_data import market  # noqa: E402
from modules.ml_model import MODEL_FILENAME, MarketPredictionEngine  # noqa: E402
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
)
from modules.paper_trading import book_option_trade, book_trade  # noqa: E402
from modules.signal_engine import generate_signal  # noqa: E402
from utils.ui import set_market_context  # noqa: E402


INDEX_SYMBOLS = {"NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK"}
MODEL_DIR = _PROJECT_ROOT / "models"
VALIDATED_MODEL_PATH = MODEL_DIR / "quantedge_rf_v2.joblib"


@st.cache_data(ttl=60, show_spinner=False)
def _latest_history(symbol: str, interval: str = "1d"):
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=365 * 7)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    return market.download_ohlcv(symbol, start, end, interval)


@st.cache_data(ttl=60, show_spinner=False)
def _provider_expiries(symbol: str):
    from modules.options_chain import adapter

    return adapter.get_expiries(symbol)


@st.cache_data(ttl=60, show_spinner=False)
def _provider_chain(symbol: str, expiry: str):
    from modules.options_chain import get_options_chain_given

    return get_options_chain_given(symbol, expiry)


@st.cache_resource(show_spinner=False)
def _assistant(model_name: str):
    return OllamaAssistant(model=model_name)


def _fmt(value, decimals: int = 2) -> str:
    return "Unavailable" if value is None or pd.isna(value) else f"{float(value):,.{decimals}f}"


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _load_validated_model():
    for path in (VALIDATED_MODEL_PATH, MODEL_DIR / MODEL_FILENAME):
        metadata_path = path.with_suffix(path.suffix + ".json")
        if not path.exists() or not metadata_path.exists():
            continue
        try:
            engine = MarketPredictionEngine()
            engine.load_model(str(path))
            thresholds = engine.metadata.get("target_thresholds", {})
            metrics = engine.metadata.get("metrics", {})
            if thresholds.get("bear", 0) < 0 < thresholds.get("bull", 0) and metrics.get("evaluation") == "walk-forward out-of-sample" and engine._feature_names:
                engine.thresholds = thresholds
                engine.lookahead = int(engine.metadata.get("lookahead_days", engine.lookahead))
                return engine
        except Exception as exc:
            logging.getLogger(__name__).warning("Saved prediction model could not be loaded: %s", exc)
    return None


def _quote_snapshot(symbol: str, history: pd.DataFrame):
    quote = market.get_quotes([symbol]).get(symbol, {})
    if quote.get("available") and quote.get("last_price") is not None:
        return quote
    if history is None or history.empty:
        return quote
    current = float(history["close"].iloc[-1])
    previous = float(history["close"].iloc[-2]) if len(history) > 1 else None
    timestamp = market._timestamp_of(history)
    status, age_seconds = market._freshness_status(timestamp)
    change = current - previous if previous is not None else None
    return {
        "available": True,
        "last_price": current,
        "previous_close": previous,
        "change": change,
        "change_percent": change / previous * 100 if previous else None,
        "volume": int(history["volume"].iloc[-1]) if pd.notna(history["volume"].iloc[-1]) else None,
        "source": "yfinance daily history",
        "timestamp": timestamp.isoformat() if timestamp else None,
        "status": status,
        "age_seconds": age_seconds,
    }


def _show_market_metrics(quote: dict, label: str):
    set_market_context(
        st,
        label,
        quote.get("source", "UNAVAILABLE"),
        quote.get("status", "UNAVAILABLE"),
        quote.get("timestamp"),
    )
    st.session_state["qe_selected_instrument"] = label
    st.subheader("Market Overview")
    columns = st.columns(4)
    columns[0].metric("Current available price", _fmt(quote.get("last_price")))
    columns[1].metric("Previous close", _fmt(quote.get("previous_close")))
    change_percent = quote.get("change_percent")
    columns[2].metric("Price change", _fmt(quote.get("change")), f"{change_percent:+.2f}%" if change_percent is not None else None)
    columns[3].metric("Freshness", quote.get("status", "UNAVAILABLE"))
    st.caption(
        f"{label} · Source: {quote.get('source', 'UNAVAILABLE')} · "
        f"Source timestamp: {quote.get('timestamp') or 'unavailable'}"
    )


def _option_input(underlying: str):
    st.subheader("Option contract")
    upload_columns = st.columns(2)
    with upload_columns[0]:
        chain_file = st.file_uploader("Option chain CSV", type=["csv"], key="prediction_chain_csv")
    with upload_columns[1]:
        candle_file = st.file_uploader("Option contract candles CSV", type=["csv"], key="prediction_candle_csv")

    chain_result = load_csv_options(chain_file.getvalue()) if chain_file else None
    candle_result = load_option_candles(candle_file.getvalue()) if candle_file else None
    chain_data = chain_result["data"] if chain_result and chain_result.get("available") else pd.DataFrame()
    candle_data = candle_result["data"] if candle_result and candle_result.get("available") else pd.DataFrame()
    if chain_result and not chain_result.get("available"):
        st.warning(chain_result.get("error", "Invalid chain CSV."))
    if candle_result and not candle_result.get("available"):
        st.warning(candle_result.get("error", "Invalid candle CSV."))

    provider_expiries = [] if not chain_data.empty else _provider_expiries(underlying)
    expiries = available_expiries(chain_data, underlying) if not chain_data.empty else []
    if not expiries:
        expiries = provider_expiries or available_expiries(candle_data, underlying)
    expiry = nearest_expiry(expiries, allow_past=bool(not chain_data.empty or not candle_data.empty))
    if len(expiries) > 1:
        expiry = st.selectbox("Expiry", expiries, index=expiries.index(expiry) if expiry in expiries else 0)
    elif expiry:
        st.caption(f"Nearest available expiry: **{expiry}**")
    if expiry and chain_data.empty and provider_expiries:
        provider_result = _provider_chain(underlying, expiry)
        if provider_result.get("available"):
            chain_data = provider_result["data"]
    contract_source = chain_data if not chain_data.empty else candle_data
    strikes = sorted(pd.to_numeric(contract_source.get("strike", pd.Series(dtype=float)), errors="coerce").dropna().unique().tolist())
    if not expiry or not strikes:
        st.warning("No valid option expiry/strike data is available. The provider did not return this NSE chain; upload contract-identified CSV data. No expiry or premium is invented.")
        return None

    underlying_symbol = INDEX_SYMBOLS.get(underlying, f"{underlying}.NS")
    underlying_quote = market.get_quotes([underlying_symbol]).get(underlying_symbol, {})
    underlying_price = underlying_quote.get("last_price") if underlying_quote.get("available") else None
    atm = min(strikes, key=lambda value: abs(value - underlying_price)) if underlying_price is not None else strikes[len(strikes) // 2]
    strike = st.selectbox("Strike", strikes, index=strikes.index(atm), format_func=lambda value: f"{value:,.2f}")
    option_type = st.radio("Option type", ["CE", "PE"], horizontal=True)
    row = None
    if not chain_data.empty:
        matches = chain_data[
            chain_data["symbol"].map(normalize_underlying).eq(normalize_underlying(underlying))
            & chain_data["expiry"].astype(str).eq(str(expiry))
            & pd.to_numeric(chain_data["strike"], errors="coerce").eq(float(strike))
            & chain_data["option_type"].eq(option_type)
        ]
        if not matches.empty:
            row = matches.iloc[-1]
    history = contract_candles(candle_data, underlying, expiry, strike, option_type) if not candle_data.empty else pd.DataFrame()
    chain_result = chain_result or ({"source": "yfinance options", "status": "DELAYED", "timestamp": None} if row is not None else None)
    return {
        "underlying": underlying,
        "expiry": expiry,
        "strike": float(strike),
        "option_type": option_type,
        "row": row,
        "history": history,
        "chain": chain_data,
        "chain_result": chain_result,
        "candle_result": candle_result,
        "underlying_price": underlying_price,
    }


def app():
    st.caption("Select an instrument for sourced market context. The saved model is never retrained automatically.")
    instrument_type = st.radio("Instrument type", ["Index", "Equity stock", "Options contract"], horizontal=True)

    option_context = None
    if instrument_type == "Index":
        label = st.selectbox("Index", ["NIFTY 50", "BANK NIFTY"], key="prediction_index")
        symbol = {"NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK"}[label]
        intervals = ["1d", "1wk", "1mo"]
        preferred = st.session_state.get("qe_default_chart_interval", "1d")
        interval = st.selectbox("Chart timeframe", intervals, index=intervals.index(preferred) if preferred in intervals else 0, key="prediction_index_interval")
    elif instrument_type == "Equity stock":
        label = st.selectbox("Search and select NSE stock", SUPPORTED_STOCKS, key="prediction_stock")
        symbol = f"{label}.NS"
        intervals = ["1d", "1wk", "1mo"]
        preferred = st.session_state.get("qe_default_chart_interval", "1d")
        interval = st.selectbox("Chart timeframe", intervals, index=intervals.index(preferred) if preferred in intervals else 0, key="prediction_stock_interval")
    else:
        label = st.selectbox("Options underlying", SUPPORTED_INDICES + SUPPORTED_STOCKS, index=0, key="prediction_option_underlying")
        symbol = None
        interval = None
        option_context = _option_input(label)

    if instrument_type == "Options contract":
        if option_context is None:
            return
        option_row = option_context["row"]
        option_history = option_context["history"]
        premium = option_row.get("ltp") if option_row is not None else None
        if (premium is None or pd.isna(premium)) and not option_history.empty:
            premium = float(option_history["close"].iloc[-1])
        previous = float(option_history["close"].iloc[-2]) if len(option_history) > 1 else None
        current = float(premium) if premium is not None and pd.notna(premium) else None
        change = float(option_row.get("change")) if option_row is not None and pd.notna(option_row.get("change")) else (current - previous if current is not None and previous is not None else None)
        timestamp = (option_context["chain_result"] or {}).get("timestamp") if option_context["chain_result"] else None
        if not timestamp and not option_history.empty:
            timestamp = option_history.index[-1].isoformat()
        csv_source = bool(option_context["chain_result"] or option_context["candle_result"])
        contract = f"{label} {option_context['strike']:g} {option_context['option_type']}"
        quote = {
            "available": current is not None,
            "last_price": current,
            "previous_close": previous,
            "change": change,
            "change_percent": (change / previous * 100) if change is not None and previous else None,
            "source": "CSV UPLOAD" if csv_source else "yfinance options",
            "status": ("CSV UPLOAD" if csv_source else "DELAYED") if current is not None else "UNAVAILABLE",
            "timestamp": timestamp,
        }
        st.markdown(f"### {contract} · Expiry {option_context['expiry']}")
        _show_market_metrics(quote, contract)
        chain_stats = chain_statistics(option_context["chain"], label, option_context["expiry"]) if not option_context["chain"].empty else {}
        oi_columns = st.columns(6)
        oi_columns[0].metric("Volume", _fmt(option_row.get("volume") if option_row is not None else (option_history["volume"].iloc[-1] if not option_history.empty and "volume" in option_history else None), 0))
        oi_columns[1].metric("Open interest", _fmt(option_row.get("open_interest") if option_row is not None else None, 0))
        oi_columns[2].metric("Change in OI", _fmt(option_row.get("change_in_open_interest") if option_row is not None else None, 0))
        iv = option_row.get("iv") if option_row is not None else None
        oi_columns[3].metric("Implied volatility", f"{_fmt(iv)}%" if iv is not None and pd.notna(iv) else "Unavailable")
        greeks = " · ".join(f"{name} {_fmt(option_row.get(name), 4)}" for name in ("delta", "gamma", "theta", "vega") if option_row is not None and option_row.get(name) is not None and pd.notna(option_row.get(name)))
        oi_columns[4].metric("Greeks", greeks or "Unavailable")
        analysis = analyze_contract(option_row, option_history, option_context["chain"], option_context["underlying_price"])
        oi_columns[5].metric("Moneyness", analysis["moneyness"])
        if chain_stats:
            context_cols = st.columns(3)
            context_cols[0].metric("PCR (OI)", _fmt(chain_stats.get("pcr"), 3))
            context_cols[1].metric("Max pain", _fmt(chain_stats.get("max_pain")))
            context_cols[2].metric("Change in OI", _fmt(option_row.get("change_in_open_interest") if option_row is not None else None, 0))
        st.subheader("Option technical analysis")
        st.write(
            f"Premium trend: {analysis['premium_trend']} · EMA: {analysis['ema_trend']} · "
            f"RSI: {analysis['rsi_momentum']} · MACD: {analysis['macd_momentum']} · "
            f"OI: {analysis['oi_analysis']} · IV: {analysis['iv_condition']}"
        )
        if option_history.empty:
            st.info("Historical candles for this exact option contract are unavailable. Upload matching contract candles to chart it; the underlying series is not substituted.")
        else:
            render_interactive_chart(
                option_history,
                f"{contract} · option premium candles",
                key="prediction_option_chart",
                default_indicators=["EMA 9", "EMA 20", "Volume", "RSI", "MACD"],
                height=800,
            )
        st.subheader("ML Prediction")
        st.warning("UNAVAILABLE: the configured RandomForest is trained on equity/index OHLCV, not option-contract premiums. No option prediction is generated from an underlying model.")
        st.subheader("Final Signal")
        st.metric("Signal", "UNAVAILABLE")
        st.info("No validated options-contract model or live NSE options feed is available. Consider waiting for authorized contract data.")
        expiry_date = pd.to_datetime(option_context["expiry"], errors="coerce")
        tradable_expiry = not pd.isna(expiry_date) and expiry_date.date() >= datetime.now(timezone.utc).date()
        if current is not None and current > 0 and tradable_expiry:
            st.subheader("Open option paper trade")
            st.caption("Simulated order only; quantity is in option units because no lot size was supplied by this source.")
            with st.form("prediction_option_paper_trade"):
                quantity = st.number_input("Option units", min_value=1, value=1, step=1)
                fees = st.number_input("Fees (INR)", min_value=0.0, value=float(st.session_state.get("qe_option_fees", 0.0)), step=1.0)
                submitted = st.form_submit_button("Review and confirm simulated order")
            if submitted:
                connection = get_connection(_PROJECT_ROOT / "data" / "paper_trading.db")
                try:
                    result = book_option_trade(connection, st.session_state.get("account_key", "quantedge_user"), label, option_context["expiry"], option_context["strike"], option_context["option_type"], int(quantity), current, float(fees))
                    st.success(f"Simulated option order recorded: {result['trade_id']}")
                except Exception as exc:
                    st.error(f"Option paper order was not saved: {exc}")
                finally:
                    connection.close()
        elif current is not None and current > 0 and not tradable_expiry:
            st.info("This is historical option data for an expired contract; a new paper trade is disabled.")
        analysis_payload = {
            "instrument": contract,
            "expiry": option_context["expiry"],
            "market": quote,
            "option": option_row.to_dict() if option_row is not None else None,
            "chain_context": chain_stats,
        }
        st.session_state["qe_analysis_payload"] = _json_safe(analysis_payload)
        ask_assistant = st.button("Ask Qwen to explain this option context", key="prediction_option_qwen")
    else:
        with st.spinner(f"Fetching latest available {label} data..."):
            history = _latest_history(symbol, interval)
        if history is None or history.empty:
            st.warning(f"No usable historical market data is available for {label}. No prediction or signal was generated.")
            return
        quote = _quote_snapshot(symbol, history)
        _show_market_metrics(quote, label)
        indicator_engine = IndicatorEngine()
        technical = indicator_engine.describe(history, label)
        st.subheader("Technical Analysis")
        tech_columns = st.columns(5)
        tech_columns[0].metric("RSI", _fmt(technical.get("rsi")))
        tech_columns[1].metric("MACD", _fmt(technical.get("macd")))
        tech_columns[2].metric("EMA 9 / 20", f"{_fmt(technical.get('ema9'))} / {_fmt(technical.get('ema20'))}")
        tech_columns[3].metric("VWAP", _fmt(technical.get("vwap")))
        tech_columns[4].metric("Trend", technical.get("trend_direction", "UNAVAILABLE"))
        st.write(
            f"Volume: {_fmt(technical.get('volume'), 0)} · Support: "
            f"{', '.join(_fmt(v) for v in technical.get('support_levels', [])) or 'Unavailable'} · "
            f"Resistance: {', '.join(_fmt(v) for v in technical.get('resistance_levels', [])) or 'Unavailable'}"
        )

        model = _load_validated_model()
        train_requested = st.button("Train corrected model to a new file", key="train_corrected_model")
        if train_requested:
            try:
                ml_settings = st.session_state.get("qe_ml_settings", {})
                with st.spinner("Training and evaluating a corrected model; the existing model file will not be overwritten..."):
                    model = MarketPredictionEngine(
                        lookahead_days=int(ml_settings.get("lookahead_days", 5)),
                        target_thresholds={
                            "bear": float(ml_settings.get("bear_threshold", -0.03)),
                            "bull": float(ml_settings.get("bull_threshold", 0.03)),
                        },
                    )
                    metadata = model.train(history, save_path=str(VALIDATED_MODEL_PATH))
                st.success(f"New validated model saved to {VALIDATED_MODEL_PATH.name}")
                st.json(metadata.get("metrics", {}))
            except Exception as exc:
                st.error(f"Model training failed: {exc}")
                model = None
        if model is None:
            st.warning("No validated model with saved training metadata is available. The legacy model is preserved but not used because its target metadata cannot be verified.")
            st.caption("Use the explicit training action to create a corrected model at a separate path; page reruns never retrain automatically.")

        prediction = None
        signal = None
        if model is not None:
            try:
                prediction = model.predict(history)
            except Exception as exc:
                st.warning(f"Prediction unavailable: {exc}")
            if prediction and prediction.get("available"):
                signal = generate_signal(
                    technical,
                    prediction["probabilities"],
                    trend=technical.get("trend_direction", "NEUTRAL"),
                    support=technical.get("support_levels"),
                    resistance=technical.get("resistance_levels"),
                    state={"timestamp": quote.get("timestamp"), "freshness": quote.get("status", "UNAVAILABLE")},
                )

        st.subheader("ML Prediction")
        if prediction and prediction.get("available"):
            probabilities = prediction["probabilities"]
            probability_columns = st.columns(3)
            for column, name in zip(probability_columns, ("BULLISH", "BEARISH", "NEUTRAL")):
                column.metric(f"{name.title()} probability", f"{probabilities.get(name, 0.0) * 100:.1f}%")
            st.metric("Predicted direction", prediction["class"])
            metadata = prediction.get("metadata", {})
            st.caption(
                f"Model: {metadata.get('model_type', 'Unavailable')} · "
                f"Evaluation: {metadata.get('metrics', {}).get('evaluation', 'Unavailable')} · "
                f"Walk-forward F1: {_fmt(metadata.get('walkforward_f1'), 3)} · "
                f"Training timestamp: {metadata.get('training_timestamp', 'Unavailable')} · "
                f"Data period: {metadata.get('training_start', 'Unavailable')} to {metadata.get('training_end', 'Unavailable')}"
            )
        else:
            st.info("No ML prediction was generated because a validated model is not available.")

        st.subheader("Final Signal")
        if signal:
            st.session_state["qe_last_signal"] = f"{signal['signal']} · {label} · confidence {signal['confidence'] * 100:.1f}%"
            signal_columns = st.columns(4)
            signal_columns[0].metric("Signal", signal["signal"])
            signal_columns[1].metric("Confidence", f"{signal['confidence'] * 100:.1f}%")
            signal_columns[2].metric("Entry", _fmt(signal["suggested_entry"]))
            signal_columns[3].metric("Risk / reward", _fmt(signal["risk_to_reward"]))
            st.write(
                f"Stop-loss: {_fmt(signal['stop_loss'])} · Target 1: {_fmt(signal['target1'])} · "
                f"Target 2: {_fmt(signal['target2'])}"
            )
            st.write("Supporting: " + ("; ".join(signal["supporting_reasons"]) or "No independent supporting evidence."))
            st.write("Against: " + ("; ".join(signal["contradicting_reasons"]) or "No contradicting reason identified by the configured rules."))
            st.write("Invalidating conditions: " + " ".join(signal["invalidating_conditions"]))
        else:
            st.session_state["qe_last_signal"] = "No validated signal is available."
            st.metric("Signal", "UNAVAILABLE")
            st.info("A signal is withheld until a validated prediction is available.")

        render_interactive_chart(
            history,
            f"{label} · {interval} · sourced market history",
            key="prediction_market_chart",
            default_indicators=["EMA 9", "EMA 20", "EMA 50", "VWAP", "Volume"],
            support_levels=technical.get("support_levels"),
            resistance_levels=technical.get("resistance_levels"),
            signal=signal,
            height=800,
        )
        if instrument_type == "Equity stock" and quote.get("last_price") is not None:
            st.subheader("Open equity paper trade")
            with st.form("prediction_equity_paper_trade"):
                action = st.radio("Order side", ["BUY", "SELL"], horizontal=True)
                quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
                fees = st.number_input("Fees (INR)", min_value=0.0, value=float(st.session_state.get("qe_brokerage", 20.0)), step=1.0)
                st.write(f"Review: {action} {int(quantity)} {symbol} @ {_fmt(quote['last_price'])} + fees {_fmt(fees)}")
                submitted = st.form_submit_button("Review and confirm simulated order")
            if submitted:
                connection = get_connection(_PROJECT_ROOT / "data" / "paper_trading.db")
                try:
                    result = book_trade(connection, st.session_state.get("account_key", "quantedge_user"), action, symbol, int(quantity), float(quote["last_price"]), fees=float(fees))
                    if isinstance(result, tuple):
                        st.error(result[1])
                    else:
                        st.success(f"Simulated equity order recorded: {result['trade_id']}")
                except Exception as exc:
                    st.error(f"Equity paper order was not saved: {exc}")
                finally:
                    connection.close()
        analysis_payload = {
            "instrument": label,
            "market": quote,
            "technical": {key: technical.get(key) for key in ("rsi", "macd", "ema9", "ema20", "ema50", "vwap", "volume", "trend_direction", "support_levels", "resistance_levels")},
            "ml_prediction": prediction,
            "signal": signal,
        }
        st.session_state["qe_analysis_payload"] = _json_safe(analysis_payload)
        ask_assistant = st.button("Ask Qwen to explain this analysis", key="prediction_equity_qwen")

    if ask_assistant:
        assistant = _assistant(st.session_state.get("ollama_model", "qwen3.5:4b"))
        question = (
            "Explain the current condition, trend, supporting and contradicting evidence, levels, risks, "
            "invalidation conditions, and whether waiting or a paper trade is more prudent. "
            "Use only supplied values; explicitly say when information is unavailable."
        )
        with st.spinner("Requesting an explanation from local Ollama..."):
            answer = assistant.chat(question, context="trading_signals", structured_data=_json_safe(analysis_payload))
        if answer.get("success"):
            st.session_state["qe_last_ai_insight"] = answer.get("assistant_reply", "")
            st.subheader("Qwen explanation")
            st.write(answer.get("assistant_reply", ""))
        else:
            st.info(f"Local Ollama is unavailable: {answer.get('message', 'No response was returned.')}")


if __name__ == "__main__":
    app()
