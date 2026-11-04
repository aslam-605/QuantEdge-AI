# QuantEdge AI — AI-Powered Indian Stock Market Analysis, Options Intelligence & Paper Trading Platform

## What it is
A locally run Streamlit application for Indian market analysis and simulated trading. It does not submit broker orders.

- Market overview for NIFTY 50, BANK NIFTY, and a stock watchlist
- Historical stock/index charts and technical indicators
- Provider-backed NSE stock option-chain lookup when yfinance actually returns expiries/contracts
- CSV-based option-chain and exact-contract historical candle analysis
- Scikit-learn RandomForest predictions with forward-return labels and walk-forward metrics
- Rule-based BUY / SELL / HOLD signal summaries
- Optional local Ollama + Qwen3.5 4B explanations from supplied structured data
- Equity and option paper trading with SQLite persistence
- Portfolio and trade history

## Technology stack
- Python 3.11
- Streamlit
- Plotly
- pandas, NumPy
- yfinance
- scikit-learn, Joblib
- ta
- SQLite
- requests
- Ollama (local LLM, Qwen3.5 4B)

## Install

```bash
cd D:\spiders\ML\project\QuantEdge-AI-Minimal

# Create a fresh isolated virtual environment
python -m venv .venv

# Activate it
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Launch

```bash
streamlit run app.py
```

Expected local address:

```
http://localhost:8501
```

## Application pages

1. Market Overview
2. Stock Explorer
3. Technical Analysis
4. Options Chain
5. AI Predictions
6. AI Assistant
7. Paper Trading
8. Portfolio
9. Settings

## Interface

The app uses grouped Streamlit navigation with one collapsible sidebar, a shared source/freshness header, a dark charcoal/emerald default palette, and a light-theme toggle. Charts share the same indicator controls and responsive Plotly layout. See [UI_DESIGN_GUIDE.md](UI_DESIGN_GUIDE.md) for the visual system and interaction conventions.

## Directory structure

- `app.py` — Streamlit entry point
- `modules/` — backend modules
- `pages/` — Streamlit pages
- `data/` — SQLite database
- `models/` — saved ML models
- `utils/` — helpers and validators
- `tests/` — automated test suite

## Ollama / Qwen setup

1. Install Ollama: https://ollama.com/download
2. Pull the preferred model:
   ```bash
   ollama pull qwen3.5:4b
   ```
3. Ensure the service is running:
   ```bash
   ollama serve
   ```
4. The assistant uses `qwen3.5:4b` by default. Keep Ollama running while requesting explanations.

If Ollama or the model is unavailable, the assistant page shows clear installation/connection messages and the rest of the application keeps working.

## Market and options data limitations

- `yfinance` provides the configured historical OHLCV/quote source. These bars may be delayed or historical; daily history is never labeled real-time.
- yfinance can expose some listed-stock option chains, but does not guarantee NSE index chains. At this review, it returned no expiries for the tested NIFTY 50, BANK NIFTY, RELIANCE, and HDFCBANK symbols.
- yfinance does not provide reliable historical candles for individual NSE option contracts. The app does not substitute the underlying price chart for an option premium chart.
- Chain and contract-history CSV uploads are supported. Required columns and examples are in [OPTIONS_ANALYSIS_GUIDE.md](OPTIONS_ANALYSIS_GUIDE.md).
- An authorized live NSE options feed and historical option candles require a separately licensed/provider integration. Missing premiums, OI, Greeks, expiries, and timestamps remain unavailable rather than being fabricated.
- Option paper orders use a confirmed observed premium and quantities in option units. Lot size is not assumed unless a source supplies it.

## Predictions and saved models

- AI Predictions fetches the latest available history automatically; it does not ask for a custom date range or retrain on each rerun.
- The existing `models/quantedge_rf.joblib` is preserved. Because it has no verified metadata sidecar for its target definition/evaluation, it is not used as a validated prediction model.
- Training is an explicit action and writes a corrected candidate to `models/quantedge_rf_v2.joblib` plus its `.json` metadata. This does not overwrite the legacy model.
- Options predictions are withheld because the configured equity/index model is not trained on option-contract premiums.
- Prediction workflow details are in [AI_PREDICTION_GUIDE.md](AI_PREDICTION_GUIDE.md).

## Testing

```bash
.\.venv\Scripts\activate
python -m unittest discover -s tests -v
```

The prediction tests write models only to temporary test directories. The test suite also uses in-memory SQLite fixtures for new options-order checks.

## Project progress

See `PROJECT_PROGRESS.md` for the current status of each feature and the implementation order.

## Known limitations

- Current options-feed and option-candle coverage depends on an authorized provider; yfinance returned no NSE expiries during the latest provider probe.
- The local Ollama service/model must be installed and running for a live AI explanation; the rest of the app remains usable when it is unavailable.
- Daily history is not a real-time feed. The UI displays the source and observation timestamp.
- Model probabilities are experimental and not financial advice or a guarantee of future performance.
