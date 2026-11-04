# QuantEdge AI Project Review

**Review date:** 2026-10-31  
**Scope:** Read-only inspection of Python source, project structure, configuration, docs, existing SQLite files, and the running Streamlit UI. This review did not modify source code, databases, paper-trading records, model artifacts, or the prior Django project.

## Executive Assessment

The repository contains implementations or partial implementations for most planned features, and the primary SQLite file is in the requested project directory and passes SQLite's read-only quick integrity check. However, the application is **not currently ready for demonstration**: most Streamlit routes render blank pages because their page modules define `app()` without invoking it; the Stock Analysis and Technical Analysis routes fail on an import of a nonexistent `modules.indicators.engine`. In addition, the ML labels/predictions and equity paper-trading accounting have correctness defects that make their displayed outputs unreliable.

The prior `D:\spiders\ML\project\data\paper_trading.db` path is not the active path in the current code. The app and trading pages use `D:\spiders\ML\project\QuantEdge-AI-Minimal\data\paper_trading.db`.

## Feature Status

| Feature | Status | Review notes |
|---|---|---|
| Market dashboard | INCOMPLETE / NOT RENDERING | Page source exists, but its `app()` function is not called. The market timestamp/status implementation also mislabels daily quotes as LIVE and can fail on timezone-aware indices. |
| NSE stock and index analysis | INCOMPLETE / BROKEN | Stock Analysis and Technical Analysis both import `engine` from `modules.indicators`, where it is not defined. The chart call is also made on that object although the chart function is in `modules.charting`. |
| Historical market charts | INCOMPLETE | Charting helpers exist, but the analysis pages do not currently render. Chart helper overlays volume on the same price axis rather than a separate volume panel. |
| Technical indicators | PARTIAL | Indicator calculations exist, but several pattern/SMC calculations are placeholder-like or incorrect; duplicated static methods are present. |
| Options-chain analysis | PARTIAL | Native adapter honestly returns UNAVAILABLE. CSV upload is present, but parser validation is weak and the upload is not used when an expiry/strike lookup is requested. |
| ML predictions | PRESENT, NOT RELIABLE | Training code exists, but labels are backward-looking, default thresholds are reversed in the page, predictions return the first row rather than the latest row, and model loading omits feature metadata. |
| BUY / SELL / HOLD signal engine | PRESENT, NOT RELIABLE | Signal objects are produced, but target/stop and risk/reward calculations are incorrect or incomplete; freshness is hard-coded. |
| Ollama AI assistant | PARTIAL / NOT RENDERING | Requests-based wrapper exists, but no current market data is passed by the page, settings do not configure the instantiated assistant, and the route does not call `app()`. Ollama availability was not rechecked during this read-only pass. |
| Equity paper trading | PRESENT, ACCOUNTING DEFECTS | Buy/sell code persists to SQLite, but sell accounting and partial closes are wrong; trade history writes to a different table than the UI reads. |
| Options paper trading | INCOMPLETE | Options tables and low-level database helpers exist, but no options paper-trading UI/flow is implemented and portfolio snapshots omit options positions. |
| Portfolio and trade history | INCOMPLETE / BROKEN | UI page does not render; history entries from `book_trade` are not written to the table it reads; equity-curve query uses an undefined table. |
| Settings | PARTIAL | Settings page renders, but it stores model choice only in session state and the database settings helper schema does not match its queries. |

## Inspection and Test Results

| Check | Result | Evidence / limits |
|---|---|---|
| Python source inventory | PASS | Inspected the project entry point, all listed modules, page scripts, utilities, and existing tests. The `utils/tests` directory is empty. |
| Requirements, README, progress, and folder structure | PASS | Reviewed `requirements.txt`, `README.md`, `PROJECT_PROGRESS.md`, `.gitignore`, `.streamlit/config.toml`, and project folders. |
| Active database path | PASS | Code resolves the database beneath the project root: `data/paper_trading.db`. |
| Expected SQLite file exists | PASS | `data/paper_trading.db` exists, is 73,728 bytes, contains the expected trading tables, and passed `PRAGMA quick_check` (`ok`). Inspection opened it read-only. |
| Existing persistence evidence | PASS, LIMITED | The project DB contains one account and one closed equity-position record. No write/restart persistence cycle was performed. The `equity_trade_history` table is empty, which conflicts with the closed-position record and reveals a write-path mismatch. |
| Old error-path database | PASS | `D:\spiders\ML\project\data\paper_trading.db` does not exist; current code does not target it. No database was moved or deleted. |
| Neighboring `paper_trading_test.db` | PASS, LIMITED | Exists, passes `quick_check`, and has zero account/trade rows. It was inspected read-only and left untouched. |
| Browser route check | FAIL | Streamlit was reachable, but most page routes had empty main content; Stock Analysis and Technical Analysis displayed an ImportError for `modules.indicators.engine`; Settings rendered. |
| Automated test suite | NOT TESTED in this review | Tests were read but not run: prediction tests call `train()`, which writes/overwrites `models/quantedge_rf.joblib`. Existing model artifacts were deliberately preserved. `PROJECT_PROGRESS.md` reports a previous 24-test pass, but that is not a fresh run for this review. |
| Market provider/data freshness runtime | NOT TESTED in this review | Provider code was inspected; live quote behavior was not fetched again. The freshness logic has code-level defects described below. |
| Ollama/model connectivity | NOT TESTED in this review | Assistant source inspected; this review did not send requests to local services. |

## Bugs and Architectural Problems

### Critical: Main page navigation does not execute page functions

Pages 1-8 define `app()` but do not call it under Streamlit execution. `pages/9_Settings.py` is the exception and has an `if __name__ == "__main__": app()` block. The browser check showed empty routes for the other pages, except pages 2 and 3, which fail during imports. This is the first issue to resolve before feature-level demonstration.

### Critical: Stock and technical analysis imports are broken

`pages/2_Stock_Analysis.py` and `pages/3_Technical_Analysis.py` import `engine` from `modules.indicators`, but that module defines `IndicatorEngine` without exporting an `engine` instance. Both pages also call `engine.candlestick_figure`, while `candlestick_figure` is implemented in `modules/charting.py`, not on `IndicatorEngine`.

### Critical: Equity SELL accounting does not return sale proceeds

`modules/paper_trading.py::book_trade` decreases cash by full buy cost on BUY, but on SELL it adds only `(sale_price - average_entry_price) * quantity - fees`. Cash should receive sale proceeds (less fees), not only realized profit. The code also fails to reduce `invested_capital` when selling. This makes available balance and account totals wrong after closing a position.

### Critical: Partial equity and options sells delete the whole position

Both `book_trade` and the lower-level close helpers validate that requested quantity is no greater than held quantity, but then delete the full open-position row even when the close quantity is smaller. Remaining quantity and cost basis are lost.

### High: Equity trade history is written to and read from different tables

`book_trade` inserts into `trades`; the paper-trading and portfolio pages query `equity_trade_history`. The helper `close_equity_position` does insert into `equity_trade_history`, but the UI uses `book_trade`. This explains why persisted closed-position data can coexist with an empty visible equity history.

### High: ML targets are backward-looking, not forward-looking

`MarketPredictionEngine._future_return()` uses `close.pct_change(frame)`, which computes the return ending at each row from earlier prices. The documented target is the return after each row. This means the class labels do not measure the stated look-ahead period and overlap with historical features; reported predictive performance is not meaningful as a forward forecast.

### High: Prediction output is selected from the oldest feature row

`predict()` computes probabilities for all rows, then reads `proba[0]` and `predict(X)[0]`. This reports the earliest valid row in the supplied frame, not the latest market observation. The page labels the result as the current prediction.

### High: Prediction page defaults reverse the bear/bull thresholds

`pages/5_AI_Predictions.py` defaults the input to `"0.03, -0.03"`, then treats the first value as the bear threshold and the second as the bull threshold. That yields bear `+0.03` and bull `-0.03`, contrary to the intended `bear=-0.03`, `bull=+0.03`. The UI also trains by default on reruns, overwriting the default model file.

### High: Loading a saved model does not restore prediction metadata

`load_model()` loads only the classifier. It does not restore `_feature_names`, thresholds, or metadata. A loaded model therefore cannot reliably use `predict()`; the current test only asserts that the model object exists and misses this behavior.

### High: Market freshness classification is incorrect

- `get_quotes()` sets every non-empty daily history result to `status="LIVE"`, regardless of timestamp.
- `symbols_available()` subtracts naive `datetime.utcnow()` from potentially timezone-aware timestamps returned by `_timestamp_of()`, which can raise `TypeError`.
- Its status thresholds classify timestamps younger than two minutes as LIVE, but daily yfinance history is generally not an authenticated real-time quote feed.
- The Streamlit Market Overview says it uses these labels to reflect source freshness, so the current implementation contradicts its UI claim.

### High: Cache storage is internally inconsistent

`StCache.set()` stores `(time.monotonic(), value)`, but `get()` reads the tuple as `(value, expiry)`. A cache hit can compare a float with a DataFrame and raise an exception. The `ttl_seconds` argument is also not used to compute an expiry time. This affects the market-data cache directly.

### High: SQLite schema and settings helpers disagree

The `settings` table created by `SCHEMA` has `setting_key` and `setting_value` only. `get_settings()` filters by `account_key`; `set_setting()` inserts `account_key` and declares a conflict target only on `setting_key`. Those calls fail against the current on-disk schema. The schema also defines `db_schema_version`, but `get_connection()` only runs the full schema when that table is absent, so it does not migrate partial or older schemas.

### High: Portfolio equity-curve query targets a missing table

`portfolio.equity_curve()` queries `portfolio_history`, but the schema does not create that table and no writer was found. The Portfolio page calls this query, so once page execution is fixed this can fail with `no such table`.

### High: Signal risk/target calculations are not valid

- Risk/reward is computed as `abs((target1 - stop_loss) / (stop_loss - target1))`, which is always 1 when the values differ.
- `target2` is taken from a second support level, including for BUY signals, rather than a direction-appropriate target.
- Entry/stop/target checks use truthiness, which mishandles valid zero-like values.
- `signal_timestamp` is always `None`, and `data_freshness` is always `"REFRESHED"`.
- The `trend` argument and stochastic RSI are not used in signal scoring; `state` is unused.
- One RSI reason contains the unrelated text `도매업`.

### Medium: Indicator calculations contain placeholders or logic errors

- `_find_order_blocks()` skips ordinary windows and only proceeds when a shifted window contains NaN; normal input therefore produces no useful detection.
- `_find_fvgs()` computes a midpoint/range over three bars rather than testing an actual gap; `gap_threshold` is unused.
- Candlestick pattern code substitutes prior close for open, so it does not identify standard candle bodies/shadows.
- `describe()`'s VWAP is cumulative across all supplied rows rather than reset by trading session.
- EMA cross output is a truncated percentage difference, not a cross event.
- RSI documentation says early rows remain NaN until a full window, but `_sma(..., min_periods=1)` does not implement that contract.

### Medium: Options CSV validation and routing are incomplete

If a CSV has `symbol`, the parser requires only `symbol` and `timestamp`, even when the file is intended to contain an options chain. Numeric fields, option types, expiry values, and row-level validity are not checked. If expiry and strike are entered, the page returns the native-provider result before displaying an uploaded CSV, making the two paths mutually exclusive.

### Medium: AI assistant is disconnected from the displayed market context

The page calls `ASSISTANT.chat()` without `structured_data`, so the assistant receives no current quote, indicators, prediction, or options data despite prompts that refer to “today's market” and “current instrument.” The Settings page writes a model name to session state, but the assistant instance is created with the module default and does not read that setting. `max_tokens` is accepted but not applied to Ollama's generation options.

### Medium: Portfolio metrics and options coverage are incomplete

The snapshot always returns an empty `options_positions` list, `_latest_quote()` always returns an empty mapping, and no code updates `portfolio_value` after trades. Current unrealized P&L and equity curve therefore do not reflect live holdings. A local `realised` value sums absolute profits/losses but is unused.

## Duplicated Code and Unused Components

- Indicator compatibility methods (`atr_series`, Bollinger bands, RSI, MACD, stochastic RSI, SMA, EMA, VWAP) are duplicated in `IndicatorEngine`.
- Equity-position accounting exists both in `modules/database.py` helpers and separately in `modules/paper_trading.py::book_trade`; these paths already differ in how they record history and include fees.
- Root `app.py` and pages 7/8 independently construct the same database path instead of sharing one path/configuration helper.
- `modules/prediction.py` overlaps with functionality in `modules/ml_model.py` and is not imported by the pages inspected.
- `modules/charting.py` owns chart builders, while stock/technical pages call them through the indicator engine, mixing module responsibilities.
- Unused/likely unused Python imports include `csv` in options chain, `time` in assistant, multiple typing imports and database functions in trading/portfolio modules, and several root imports in `app.py`.
- `requirements.txt` includes `ta`, `pandas-datareader`, and the `ollama` package without corresponding project imports found in the inspected source. The assistant currently calls the Ollama HTTP API through `requests`.
- `pages/5_AI_Predictions.py` defines `CONFIG_KEYS`, a model path field, and a “Train / Refresh” action that do not control training; `model_path` is not used.
- `.streamlit/config.toml` sets `client.socketTimeout`, which Streamlit reported as an invalid configuration option during the previous startup check.

## Database Persistence Review

- Active app path: `Path(__file__).resolve().parent / "data" / "paper_trading.db"`.
- The target file is under this project and passed SQLite's quick integrity check.
- Existing account and closed-position records confirm data has been persisted in this file. No record contents were read for this review.
- The earlier path outside the project (`D:\spiders\ML\project\data\paper_trading.db`) is absent.
- The code uses parameterized SQL for values, but some APIs commit at different points and trade booking is not atomic; partial failures can leave inconsistent trade/account/position records.
- `get_connection()` creates the parent directory and initializes schema when no schema-version table exists. It does not perform versioned migrations when a schema-version table is already present.
- Existing main DB was opened with SQLite read-only mode; no reset, move, deletion, or write was performed.

## Dependency and Import Review

- Core imports broadly align with the declared stack: Streamlit, Plotly, pandas, NumPy, yfinance, scikit-learn, Joblib, requests, and SQLite.
- The broken `modules.indicators.engine` import is confirmed by the running browser error.
- Charting imports belong to `modules.charting`, not `modules.indicators`.
- `ta`, `pandas-datareader`, and the Python `ollama` client appear unused in the inspected source; `requests` is used for Ollama HTTP calls.
- The configured Ollama model in code/docs is `qwen3.5:4b`; installed service/model availability was not tested during this review.

## Existing Automated Tests

The test files cover database table creation/basic account persistence, selected indicator outputs, basic equity buy/sell validation, and ML dataset/model training. Gaps include:

- No market-data cache or timezone/freshness tests
- No Streamlit route/import/render tests
- No settings-helper schema test or portfolio-history test
- No CSV options parser validation tests
- No options trading tests or UI flow
- Paper-trading tests do not assert correct cash after a sell, partial close behavior, fees/cost basis, trade-history persistence, or transaction rollback
- ML tests do not verify forward target alignment, latest-row prediction, threshold order, walk-forward boundaries, or prediction after loading a saved model
- Indicator tests contain weak assertions (for example `... or True`) and do not verify pattern/SMC outputs against known data
- Running the prediction tests writes to the default model path, so the suite was not run during this non-destructive inspection

## Prioritized Development Roadmap

1. **Restore page execution and navigation.** Ensure each page actually invokes its rendering function, then fix the `engine` imports and route chart calls through `modules.charting`. Add a smoke test for each route. Do not change data or model artifacts as part of this step.
2. **Make equity paper trading ledger-correct.** Use one accounting path, make each order atomic, credit full sell proceeds, reduce invested capital and positions proportionally on partial closes, include fees consistently, and write history to the table displayed by the UI. Add isolated temporary-database tests for each invariant.
3. **Correct database schema and migration strategy.** Reconcile `settings` queries with its schema, define/replace the portfolio-history path, and add explicit migrations keyed by schema version. Back up the existing DB before any future migration; do not reset it.
4. **Repair market-data freshness/cache behavior.** Fix cache tuple/expiry logic, normalize timestamps to UTC-aware values, and derive status from actual observation time and provider capability. Never call daily yfinance history real-time.
5. **Correct the ML target and prediction path.** Build a genuinely forward target, fix threshold ordering, return the latest row prediction, persist/restore model metadata and feature names, and report only chronological out-of-sample metrics. Make model output paths explicit and avoid automatic overwrite on every page rerun.
6. **Fix signal and indicator semantics.** Validate support/resistance and risk/reward by trade direction; remove hard-coded freshness; test calculations on known fixtures; either implement or clearly label approximate SMC/pattern methods.
7. **Finish options workflow.** Decide whether the project will support an authorized live provider or CSV-only analysis; validate CSV schema/values, connect uploaded data to lookup/filter controls, and implement or explicitly defer options paper-trading UI and portfolio accounting.
8. **Connect assistant settings and market context.** Pass actual, timestamped market/indicator data into the assistant, use the configured model setting, and test the missing-service and installed-model paths. Keep Ollama claims conditional on a successful connection.
9. **Clean dependencies and duplicated logic.** Consolidate trading/account operations, chart ownership, and indicator methods; remove only imports/dependencies proven unused after the functional work is tested.
10. **Refresh project documentation and verification.** Update `PROJECT_PROGRESS.md` only after route smoke tests, isolated unit tests, persistence tests, and an end-to-end demo pass. Retain the current DB and model files during validation.

## Demonstration Readiness

**Current status: NOT READY.** The Streamlit server can be reached, but most routes are blank and two analysis routes fail at import time. Accounting, ML, and market freshness defects also need correction before relying on their values. The database itself is located correctly and healthy; preserve it while addressing these issues. No major code changes were made in this review; the next implementation steps should follow the roadmap above after your instruction.