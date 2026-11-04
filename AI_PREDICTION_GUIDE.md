# AI Prediction Guide

## Instrument workflow

Open **AI Predictions** and choose an instrument type:

- **Index:** NIFTY 50 or BANK NIFTY
- **Equity stock:** choose a supported NSE symbol from the searchable selector
- **Options contract:** choose an underlying and use provider-returned or CSV-supplied expiry/strike/CE/PE values

For indices and stocks, the page automatically downloads the latest available OHLCV history, then displays current/previous close, price and percentage change, source, timestamp, and freshness. No historical date entry is required. Technical indicators, the validated ML output, signal panel, and shared interactive chart are based on that history.

For options, upload a chain snapshot and/or exact-contract candle CSV as described in [OPTIONS_ANALYSIS_GUIDE.md](OPTIONS_ANALYSIS_GUIDE.md). The application does not apply the equity/index model to option premiums. Until an options-trained model and valid contract data are available, option ML direction and signal are explicitly withheld.

## Model handling

The page does not train when opened or on ordinary reruns. It loads a model only when a JSON metadata sidecar verifies:

- forward-return target thresholds (`bear < 0 < bull`)
- out-of-sample walk-forward metrics
- feature names needed to construct predictions

The existing `models/quantedge_rf.joblib` is preserved. Its training target/evaluation metadata is unavailable, so it is not treated as validated. To intentionally train a corrected candidate, use **Train corrected model to a new file**. This explicit action writes `models/quantedge_rf_v2.joblib` and its `.json` sidecar, leaving the legacy file intact. The corrected pipeline uses forward returns, a chronological split with a lookahead gap, out-of-sample metrics, and the most recent valid feature row for prediction.

If no validated model exists, the page displays market and technical analysis but does not fabricate probabilities or a signal. In that case the user can choose the explicit corrected-model training action, provided enough valid historical data is available.

## Signal output

BUY/SELL/HOLD is derived in Python from the supplied model probabilities and technical values. Entry, stop, targets, risk/reward, confidence, supporting/contradicting reasons, invalidating conditions, and freshness are shown only when available. Chart markers represent the current generated signal; they are not historical trades. Paper-trading orders are separate, simulated, and require confirmation.

## Qwen explanation

Select **Ask Qwen to explain this analysis** to send structured market, indicator, prediction, option, and signal values to the local Ollama assistant. Python calculates all financial values; Qwen is asked to interpret only the supplied data. If Ollama or the model is unavailable, the page keeps working and reports that state without blocking data or predictions.

The local assistant is configured for `qwen3.5:4b` at `http://localhost:11434`. Install/start Ollama and pull the model using the commands in [README.md](README.md). Live model connectivity has not been verified unless the page reports both Ollama and model ready.

## Important limitations

- yfinance daily bars are delayed/historical data, not guaranteed real-time prices.
- Historical option candles and complete NIFTY/BANK NIFTY chains require an authorized source or exact-contract CSV.
- The saved legacy model is intentionally not accepted without verified metadata; no automatic retraining or overwrite occurs.
- ML and rule-based signals are experimental and are not financial advice or a guarantee of results.