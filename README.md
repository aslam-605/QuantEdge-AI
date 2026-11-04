# 📈 QuantEdge AI – Intelligent Stock Market Analysis & Paper Trading Platform

**QuantEdge AI** is an AI-powered Indian stock market analysis platform designed to help traders analyse NSE stocks and indices using technical indicators, machine learning predictions, options analysis and simulated trading.

The application combines financial data analysis, machine learning and AI-powered explanations in an interactive Streamlit dashboard.

> **Note:** QuantEdge AI is an educational and research project. It does not execute real trades or provide guaranteed financial predictions.

---

## 🚀 Features

### 1. Market Overview
- Monitor major Indian market indices.
- View market price movements and historical trends.
- Interactive market charts.
- Market data freshness indicators.

### 2. Stock Analysis
- Analyse individual NSE stocks.
- Historical price and volume analysis.
- Interactive candlestick charts.
- Technical market insights.

### 3. Technical Analysis
- RSI (Relative Strength Index).
- MACD.
- EMA 9, EMA 20 and EMA 50.
- SMA.
- VWAP.
- Bollinger Bands.
- ATR.
- Support and resistance analysis.

### 4. Options Chain Analysis
- NSE options chain exploration.
- Call and Put contract analysis.
- Open Interest (OI).
- Change in Open Interest.
- Implied Volatility (IV), where available.
- Options contract analysis and expiry selection.

### 5. AI Predictions
- Machine learning-based market predictions.
- Random Forest classification model.
- Bullish, Bearish and Neutral classifications.
- Model evaluation and prediction confidence.
- Historical feature-based analysis.

### 6. AI Assistant
- AI-powered market analysis explanations.
- Integration with locally running Ollama models.
- Natural language explanations of technical indicators and market scenarios.

### 7. Paper Trading
- Simulated equity and options trading.
- Virtual trading balance.
- Position tracking.
- Profit and loss calculations.
- Trade history.

### 8. Portfolio Management
- Monitor simulated positions.
- Track portfolio performance.
- View trading history and P&L.

---

## 🛠️ Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Frontend / Dashboard | Streamlit |
| Data Analysis | Pandas, NumPy |
| Data Visualization | Plotly |
| Machine Learning | Scikit-learn |
| Model Persistence | Joblib |
| Market Data | yfinance and supported data sources |
| Database | SQLite |
| AI Integration | Ollama |
| Testing | Pytest |

---

## 📂 Project Structure

```text
QuantEdge-AI/
│
├── app.py
├── requirements.txt
├── README.md
│
├── assets/
│   └── quantedge_logo.svg
│
├── models/
│   └── Model metadata and documentation
│
├── modules/
│   ├── ai_assistant.py
│   ├── charting.py
│   ├── database.py
│   ├── indicators.py
│   ├── market_data.py
│   ├── ml_model.py
│   ├── options_chain.py
│   ├── paper_trading.py
│   ├── portfolio.py
│   ├── prediction.py
│   └── signal_engine.py
│
├── pages/
│   ├── 1_Market_Overview.py
│   ├── 2_Stock_Analysis.py
│   ├── 3_Technical_Analysis.py
│   ├── 4_Options_Chain.py
│   ├── 5_AI_Predictions.py
│   ├── 6_AI_Assistant.py
│   ├── 7_Paper_Trading.py
│   ├── 8_Portfolio.py
│   └── 9_Settings.py
│
├── tests/
│   ├── test_database.py
│   ├── test_indicators.py
│   ├── test_options_prediction_workflows.py
│   ├── test_paper_trading.py
│   └── test_predictions.py
│
└── utils/
    ├── helpers.py
    ├── ui.py
    └── validators.py
```

---

## ⚙️ Installation and Setup

### Prerequisites

- Python 3.11
- Git
- VS Code (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/QuantEdge-AI.git
```

### 2. Navigate to the project

```bash
cd QuantEdge-AI
```

### 3. Create a virtual environment

```bash
python -m venv .venv
```

### 4. Activate the environment

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 5. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Run the application

```bash
streamlit run app.py
```

The application will normally open at:

```text
http://localhost:8501
```

---

## 🤖 Machine Learning

QuantEdge AI uses a Random Forest classification approach for market direction analysis.

The feature engineering pipeline includes:

- Price returns.
- Volume changes.
- RSI.
- MACD.
- ATR.
- EMA differences.
- SMA differences.
- Bollinger Band position.
- High-low price range.

The model uses historical market data and chronological validation to evaluate predictive performance.

Trained model files are excluded from this GitHub repository. Follow the project's training workflow to generate the model locally.

---

## 🧠 Local AI Integration

The AI Assistant supports integration with Ollama for locally running language models.

Install Ollama from:

https://ollama.com/

Configure and download a compatible model according to your local hardware.

The AI assistant is intended to explain supplied market information. Numerical indicators and trading calculations should come from the application's data and analysis modules.

---

## 📊 Data Sources and Limitations

- Market data availability depends on the configured provider.
- Historical and intraday data availability varies by instrument and provider.
- Real-time data must be verified using provider timestamps.
- Options-chain availability may vary.
- Missing market data must not be treated as real-time data.
- Machine learning predictions are estimates, not guaranteed outcomes.

---

## 🧪 Testing

Run the project tests using:

```bash
pytest -v
```

---

## 🔒 Disclaimer

QuantEdge AI is developed for educational, research and experimental purposes.

- It is not a registered investment advisory service.
- It does not guarantee market predictions or profitability.
- Paper trading is simulated and does not represent actual broker execution.
- Always independently verify market information before making financial decisions.

---

## 👨‍💻 Developer

**QuantEdge AI**

An independent Python-based project exploring the integration of:

- Financial market analysis.
- Machine learning.
- Artificial intelligence.
- Options analysis.
- Simulated trading systems.

---

⭐ If you find this project interesting, consider giving the repository a star!

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


