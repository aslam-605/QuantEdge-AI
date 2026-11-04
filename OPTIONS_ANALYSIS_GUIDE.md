# Options Analysis Guide

## Data behavior

The Options Chain page defaults to NIFTY 50 and supports BANK NIFTY plus the stock symbols configured in the app. It asks the provider for actual expiries and selects the nearest returned upcoming expiry. An expiry is never synthesized. If no valid expiry is returned, the page asks for an options-chain CSV instead.

The current provider adapter uses yfinance. It may return stock options for some symbols, but it does not guarantee a complete NSE index chain. During the latest check, yfinance returned no expiries for NIFTY 50, BANK NIFTY, RELIANCE, or HDFCBANK. An authorized NSE options provider is required for reliable live chains.

## Chain CSV format

Upload one row per contract. Required fields are `symbol`, `expiry`, `strike`, `option_type`, and `ltp`. The contract side must be `CE` or `PE` (or `CALL`/`PUT`). Optional fields include `change`, `volume`, `open_interest`, `change_in_open_interest`, `iv`, `delta`, `gamma`, `theta`, `vega`, and `timestamp`.

Example:

```csv
symbol,expiry,strike,option_type,ltp,change,volume,open_interest,change_in_open_interest,iv,delta,gamma,theta,vega,timestamp
NIFTY 50,2026-11-05,25000,CE,120.5,4.2,410,1200,80,18.4,0.52,0.02,-0.3,0.2,2026-10-31T12:00:00Z
NIFTY 50,2026-11-05,25000,PE,130.0,-2.1,350,900,-35,19.1,-0.48,0.02,-0.3,0.2,2026-10-31T12:00:00Z
```

Missing optional fields remain unavailable in the table; they are not filled with estimates. The page shows ATM/ITM/OTM only when an underlying price is available. If not, moneyness is shown as unknown.

PCR is calculated only when call and put OI totals are valid. Max pain is shown only when there are at least three strikes with valid call and put OI. Highlighted OI/change-in-OI/volume values are derived from supplied rows.

## Exact-contract candle CSV

Historical premium charts require candles for the selected option contract. Required identity and price fields are `symbol`, `expiry`, `strike`, `option_type`, `timestamp`, `open`, `high`, `low`, `close`, and `volume`. An optional `interval` column can identify actual candle cadence; the timeframe selector only appears when the uploaded data includes interval values.

```csv
symbol,expiry,strike,option_type,timestamp,open,high,low,close,volume,interval
NIFTY 50,2026-11-05,25000,CE,2026-10-31T10:00:00Z,118,123,116,121,850,5m
NIFTY 50,2026-11-05,25000,CE,2026-10-31T10:05:00Z,121,125,120,124,920,5m
```

The chart filters by all four contract fields before plotting. If matching history is unavailable, the page says so and does not plot the underlying index as an option premium. EMA, VWAP (where volume is valid), Bollinger Bands, RSI, MACD, and volume use the supplied premium candles.

## Analysis and paper trading

The analysis panel distinguishes observed values from unavailable values. Long buildup, short buildup, short covering, and long unwinding require both premium price change and OI change. IV condition uses a chain-relative quartile only when enough IV observations exist. Greeks are displayed only when supplied by the provider/CSV.

The paper-trading form is shown only when an observed chain premium or exact-contract candle close is available and the contract has not expired. It asks for confirmation, checks available cash, and stores a simulated options position/trade. Quantity is in option units: no lot size is assumed unless a source verifies it. No broker API is called.

## Source labels and limits

- `DELAYED`: provider-returned option chain; yfinance is not treated as an authenticated real-time NSE feed.
- `CSV UPLOAD`: chain or premium candles supplied by the user; the source timestamp is shown when present.
- `UNAVAILABLE`: provider did not return valid expiries, contracts, premiums, or exact-contract candles.

For reliable live NIFTY/BANK NIFTY chains and historical per-contract candles, integrate an authorized provider that implements `OptionsDataProvider`. Preserve the same normalized fields and return source timestamps; do not generate missing values.