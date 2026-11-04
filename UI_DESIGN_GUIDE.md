# QuantEdge AI UI Design Guide

## Visual system

- **Default:** charcoal/deep navy surfaces with an emerald-teal accent.
- **Light mode:** cool white/grey surfaces with a darker teal accent.
- **Market colors:** green for rising/bullish, red for falling/bearish, muted grey for neutral or unavailable.
- **Typography:** restrained, compact heading hierarchy with readable body and data labels; avoid display-sized dashboard typography.
- **Surfaces:** subtle borders, consistent spacing, and small-radius metric/table panels. Avoid nested decorative cards.

Theme tokens are centralized in `utils/ui.py` and the initial dark palette in `.streamlit/config.toml`. Theme selection is in the app header and applies to Streamlit surfaces and the shared Plotly chart renderer.

## Navigation and shell

`app.py` owns one `st.navigation` tree with grouped Markets, Research, Assistant, Trading, and System sections. Page titles and Material icons are defined in the navigation tree; individual pages do not create a competing nav. The sidebar is Streamlit-collapsible and includes the QuantEdge mark.

The shared top bar contains the current page title, last selected instrument, source/freshness/timestamp, one refresh action, and theme toggle. `utils/ui.py` carries session context from market pages to the shell. Refresh clears market and Streamlit data caches but does not touch SQLite or model files.

## Charts

All major market pages use the shared renderer in `modules/charting.py`:

- Green/red candles and labeled axes with readable OHLC hover details
- Default EMA/volume overlays, with selectable EMA 9/20/50, VWAP, Bollinger Bands, RSI, MACD, and Volume
- Volume, RSI, and MACD in separate lower panels where selected
- Range selection, zoom, pan, autoscale/reset tools, and responsive sizing
- Optional current BUY/SELL signal, entry/stop/target levels, and support/resistance overlays
- Theme-aware Plotly backgrounds while preserving bullish/bearish candle colors

Option charts must be exact-contract premium candles. If those candles are unavailable, the UI presents the provider limitation and does not substitute the underlying chart.

## Page layout

- **Market Overview:** index/FINNIFTY/portfolio summary, market summary, available watchlist movers, open paper positions, large chart, and current-session AI/signal summaries.
- **Stock Explorer:** searchable supported stock selector, quote/freshness, indicator summary, chart, and AI-analysis shortcut.
- **Options Chain:** underlying/expiry/strike/CE-PE selector, source labels, chain table, OI/PCR/max-pain, exact-contract candles, and analysis.
- **AI Predictions:** instrument type first, then market and technical facts, validated model output, signal/risk section, chart, and Qwen explanation action.
- **AI Assistant:** session chat with suggested prompts and the most recently selected structured analysis.
- **Paper Trading:** Equity order, Options handoff, Open positions, Closed positions, and Trade history tabs.
- **Portfolio:** summary followed by Overview, Positions, Performance, and Trade history tabs.
- **Settings:** Appearance, Market data, Charts, AI models, and Paper trading sections.

## Interaction rules

- Show source, observation timestamp, and freshness close to financial values. Do not label daily historical data LIVE.
- Use explicit unavailable states for missing prices, expiries, option candles, OI, Greeks, predictions, and model metadata.
- Paper orders use a review/confirm step and remain simulated. Resets require explicit confirmation and do not delete trade-history rows.
- Keep common controls on the page where the decision happens; use links only for deeper analysis.
- Prefer tables for comparable values, metrics for a few headline values, and tabs for separate working modes.

## Responsive behavior

The shell uses Streamlit's responsive columns and collapsible sidebar. The shared CSS reduces metric/card spacing and heading sizes below 720px. Dense tables keep horizontal scrolling rather than shrinking financial values into unreadable text; charts use Plotly responsive mode.