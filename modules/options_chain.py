"""Options chain module for QuantEdge AI.

Responsibilities:
- Describe what is available (yfinance historical/quote data for indices is limited)
- Validate uploadable CSV files for permitted historical options datasets
- Provide adapters so an authorised provider can be added later
- Never fabricate option premiums, OI, expiry dates, or Greeks
- Return UNAVAILABLE when the current chain cannot be obtained
"""

from __future__ import annotations

from io import BytesIO
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

SUPPORTED_INDICES = ["NIFTY 50", "BANK NIFTY"]
SUPPORTED_STOCKS = [
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "INFY",
    "TCS",
    "SBIN",
    "ITC",
]

VALID_OTYPES = {"CE", "PE"}
CHAIN_REQUIRED_COLUMNS = {"symbol", "expiry", "strike", "option_type", "ltp"}
CANDLE_REQUIRED_COLUMNS = {
    "symbol", "expiry", "strike", "option_type", "timestamp",
    "open", "high", "low", "close", "volume",
}
OPTION_NUMERIC_COLUMNS = (
    "strike", "ltp", "change", "volume", "open_interest",
    "change_in_open_interest", "iv", "delta", "gamma", "theta", "vega",
)
YFINANCE_STOCK_SYMBOLS = {
    "RELIANCE": "RELIANCE.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "INFY": "INFY.NS",
    "TCS": "TCS.NS",
    "SBIN": "SBIN.NS",
    "ITC": "ITC.NS",
}


def normalize_underlying(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    aliases = {"NIFTY": "NIFTY 50", "^NSEI": "NIFTY 50", "^NSEBANK": "BANK NIFTY"}
    return aliases.get(value, value.removesuffix(".NS"))


def _expiry_date(value: Any) -> Optional[date]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


class OptionsDataProvider:
    """Adapter interface. A supported provider implements this."""
    name: str = "base"

    def get_chain(self, symbol: str, expiry: Optional[str] = None, strike: Optional[float] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def get_expiries(self, symbol: str) -> List[str]:
        return []

    def get_strikes(self, symbol: str, expiry: str) -> List[float]:
        return []

    def get_contract_candles(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
        interval: str,
    ) -> Dict[str, Any]:
        return _unavailable_result(normalize_underlying(symbol), "Historical option-contract candles are not available from this provider.")

    def get_available_candle_intervals(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
    ) -> List[str]:
        return []

    def label(self) -> str:
        return f"{self.name} provider"


class YfinanceOptionsAdapter(OptionsDataProvider):
    """yfinance adapter that reports only the option data actually returned."""
    name = "yfinance"

    def get_chain(self, symbol: str, expiry: Optional[str] = None, strike: Optional[float] = None) -> Dict[str, Any]:
        normalized = normalize_underlying(symbol)
        provider_symbol = YFINANCE_STOCK_SYMBOLS.get(normalized)
        if provider_symbol is None:
            return _unavailable_result(normalized, "yfinance does not expose a configured option chain for this underlying.")

        expiries = self.get_expiries(normalized)
        selected_expiry = expiry or nearest_expiry(expiries)
        if not selected_expiry or selected_expiry not in expiries:
            return _unavailable_result(normalized, "No valid upcoming expiry was returned by yfinance.")

        try:
            import yfinance as yf

            raw = yf.Ticker(provider_symbol).option_chain(selected_expiry)
            calls = _normalise_yfinance_side(raw.calls, normalized, selected_expiry, "CE")
            puts = _normalise_yfinance_side(raw.puts, normalized, selected_expiry, "PE")
            data = pd.concat([calls, puts], ignore_index=True)
            if strike is not None:
                data = data[pd.to_numeric(data["strike"], errors="coerce").sub(float(strike)).abs() < 1e-8]
            if data.empty:
                return _unavailable_result(normalized, "The provider returned no contracts for the selected expiry/strike.")
            return {
                "available": True,
                "status": "DELAYED",
                "source": "yfinance options",
                "timestamp": _latest_source_timestamp(data),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "symbol": normalized,
                "expiry": selected_expiry,
                "expiries": expiries,
                "data": data,
            }
        except Exception as exc:
            logger.warning("yfinance options lookup failed for %s: %s", normalized, exc)
            return _unavailable_result(normalized, "The yfinance options endpoint did not return a usable chain.")

    def get_expiries(self, symbol: str) -> List[str]:
        normalized = normalize_underlying(symbol)
        provider_symbol = YFINANCE_STOCK_SYMBOLS.get(normalized)
        if provider_symbol is None:
            return []
        try:
            import yfinance as yf

            raw_expiries = yf.Ticker(provider_symbol).options or []
            today = datetime.now(timezone.utc).date()
            return sorted(
                {
                    expiry.isoformat()
                    for value in raw_expiries
                    if (expiry := _expiry_date(value)) is not None and expiry >= today
                }
            )
        except Exception as exc:
            logger.warning("yfinance expiry lookup failed for %s: %s", normalized, exc)
            return []

    def get_strikes(self, symbol: str, expiry: str) -> List[float]:
        result = self.get_chain(symbol, expiry)
        if not result.get("available"):
            return []
        return sorted(pd.to_numeric(result["data"]["strike"], errors="coerce").dropna().unique().tolist())

    def get_contract_candles(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
        interval: str,
    ) -> Dict[str, Any]:
        return _unavailable_result(
            normalize_underlying(symbol),
            "yfinance does not expose reliable historical candles for individual NSE option contracts.",
        )

    def get_available_candle_intervals(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
    ) -> List[str]:
        return []

    def label(self) -> str:
        return "yfinance options adapter"


# Single global adapter instance
adapter = YfinanceOptionsAdapter()


def _unavailable_result(symbol: str, message: str) -> Dict[str, Any]:
    return {
        "available": False,
        "status": "UNAVAILABLE",
        "source": "yfinance",
        "timestamp": None,
        "symbol": symbol,
        "data": None,
        "message": message,
    }


def _normalise_yfinance_side(data: pd.DataFrame, symbol: str, expiry: str, option_type: str) -> pd.DataFrame:
    frame = data.copy()
    frame = frame.rename(
        columns={
            "lastPrice": "ltp",
            "percentChange": "percent_change",
            "openInterest": "open_interest",
            "impliedVolatility": "iv",
            "lastTradeDate": "timestamp",
        }
    )
    for column in ("strike", "ltp", "change", "volume", "open_interest", "iv", "delta", "gamma", "theta", "vega", "timestamp"):
        if column not in frame:
            frame[column] = pd.NA
    frame["iv"] = pd.to_numeric(frame["iv"], errors="coerce") * 100.0
    frame["symbol"] = symbol
    frame["expiry"] = expiry
    frame["option_type"] = option_type
    frame["source"] = "yfinance options"
    return frame


def _latest_source_timestamp(data: pd.DataFrame) -> Optional[str]:
    if "timestamp" not in data:
        return None
    parsed = pd.to_datetime(data["timestamp"], errors="coerce", utc=True).dropna()
    return parsed.max().isoformat() if not parsed.empty else None


def _read_csv(source: Any) -> pd.DataFrame:
    if isinstance(source, (bytes, bytearray)):
        return pd.read_csv(BytesIO(source))
    if isinstance(source, Path):
        return pd.read_csv(source)
    if hasattr(source, "getvalue"):
        return pd.read_csv(BytesIO(source.getvalue()))
    return pd.read_csv(source)


def _normalise_columns(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    aliases = {
        "underlying": "symbol",
        "instrument": "symbol",
        "optiontype": "option_type",
        "type": "option_type",
        "last_price": "ltp",
        "lastprice": "ltp",
        "premium": "ltp",
        "oi": "open_interest",
        "openinterest": "open_interest",
        "change_in_oi": "change_in_open_interest",
        "changeinopeninterest": "change_in_open_interest",
        "implied_volatility": "iv",
        "impliedvolatility": "iv",
        "date": "timestamp",
        "datetime": "timestamp",
        "time": "timestamp",
    }
    return frame.rename(columns={key: value for key, value in aliases.items() if key in frame.columns})


def _normalise_contract_identity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].map(normalize_underlying)
    result["strike"] = pd.to_numeric(result["strike"], errors="coerce")
    result["expiry"] = pd.to_datetime(result["expiry"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    result["option_type"] = result["option_type"].astype(str).str.strip().str.upper().replace({"CALL": "CE", "PUT": "PE"})
    return result[
        result["symbol"].ne("")
        & result["expiry"].notna()
        & result["strike"].gt(0)
        & result["option_type"].isin(VALID_OTYPES)
    ].copy()


def load_csv_options(source: Any) -> Dict[str, Any]:
    """Parse a chain snapshot without filling or inventing missing market values."""
    try:
        frame = _normalise_columns(_read_csv(source))
    except Exception as exc:
        logger.warning("Options CSV read failed: %s", exc)
        return {"available": False, "error": "Could not parse file as CSV."}

    missing = CHAIN_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        return {"available": False, "error": f"Missing required chain columns: {', '.join(sorted(missing))}"}
    frame = _normalise_contract_identity(frame)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    for column in OPTION_NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ltp"])
    if frame.empty:
        return {"available": False, "error": "CSV contains no valid option contracts with a premium."}

    timestamp = _latest_source_timestamp(frame)
    return {
        "available": True,
        "status": "CSV UPLOAD",
        "data": frame,
        "source": "CSV UPLOAD",
        "timestamp": timestamp,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def load_option_candles(source: Any) -> Dict[str, Any]:
    """Load OHLCV history tied to an exact option contract identity."""
    try:
        frame = _normalise_columns(_read_csv(source))
    except Exception as exc:
        logger.warning("Option candle CSV read failed: %s", exc)
        return {"available": False, "error": "Could not parse option candle file as CSV."}

    missing = CANDLE_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        return {"available": False, "error": f"Missing option candle columns: {', '.join(sorted(missing))}"}

    frame = _normalise_contract_identity(frame)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    for column in ("open", "high", "low", "close", "volume", "strike"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    frame = frame[(frame["high"] >= frame["low"]) & (frame["volume"] >= 0)]
    if frame.empty:
        return {"available": False, "error": "CSV contains no valid option candles."}
    frame = frame.sort_values("timestamp").drop_duplicates(
        ["symbol", "expiry", "strike", "option_type", "timestamp"], keep="last"
    )
    return {
        "available": True,
        "status": "CSV UPLOAD",
        "data": frame,
        "source": "CSV UPLOAD",
        "timestamp": _latest_source_timestamp(frame),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def nearest_expiry(expiries: List[str], allow_past: bool = False) -> Optional[str]:
    valid = sorted({value for item in expiries if (value := _expiry_date(item)) is not None})
    today = datetime.now(timezone.utc).date()
    future = [value for value in valid if value >= today]
    if future:
        return future[0].isoformat()
    if allow_past and valid:
        return valid[-1].isoformat()
    return None


def available_expiries(data: pd.DataFrame, symbol: str) -> List[str]:
    if data is None or data.empty or "expiry" not in data or "symbol" not in data:
        return []
    normalized = normalize_underlying(symbol)
    rows = data[data["symbol"].map(normalize_underlying).eq(normalized)]
    return sorted(rows["expiry"].dropna().astype(str).unique().tolist())


def prepare_chain_table(
    data: pd.DataFrame,
    symbol: str,
    expiry: str,
    underlying_price: Optional[float],
    strike_range: int = 5,
) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    frame = data[
        data["symbol"].map(normalize_underlying).eq(normalize_underlying(symbol))
        & data["expiry"].astype(str).eq(str(expiry))
    ].copy()
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    strikes = sorted(frame["strike"].dropna().unique().tolist())
    if not strikes:
        return pd.DataFrame()
    atm_strike = min(strikes, key=lambda value: abs(value - underlying_price)) if underlying_price is not None else None
    atm_index = strikes.index(atm_strike) if atm_strike is not None else len(strikes) // 2
    if strike_range > 0:
        strikes = strikes[max(0, atm_index - strike_range): atm_index + strike_range + 1]
    fields = {
        "ltp": "LTP",
        "change": "Change",
        "volume": "Volume",
        "open_interest": "OI",
        "change_in_open_interest": "Change in OI",
        "iv": "IV",
        "delta": "Delta",
        "gamma": "Gamma",
        "theta": "Theta",
        "vega": "Vega",
    }
    records = []
    filtered = frame[frame["strike"].isin(strikes)]
    for strike_value in strikes:
        strike_rows = filtered[filtered["strike"].eq(strike_value)]
        row: Dict[str, Any] = {"Strike": float(strike_value), "ATM": atm_strike is not None and strike_value == atm_strike}
        for option_type in ("CE", "PE"):
            side = strike_rows[strike_rows["option_type"].eq(option_type)]
            contract = side.iloc[-1] if not side.empty else None
            if option_type == "CE":
                moneyness = "Unknown" if underlying_price is None else ("ATM" if strike_value == atm_strike else ("ITM" if strike_value < underlying_price else "OTM"))
            else:
                moneyness = "Unknown" if underlying_price is None else ("ATM" if strike_value == atm_strike else ("ITM" if strike_value > underlying_price else "OTM"))
            row[f"{option_type} Status"] = moneyness
            for source_column, label in fields.items():
                row[f"{option_type} {label}"] = contract.get(source_column) if contract is not None and source_column in contract else None
        records.append(row)
    return pd.DataFrame(records)


def chain_statistics(data: pd.DataFrame, symbol: str, expiry: str) -> Dict[str, Any]:
    frame = data[
        data["symbol"].map(normalize_underlying).eq(normalize_underlying(symbol))
        & data["expiry"].astype(str).eq(str(expiry))
    ].copy()
    frame["open_interest"] = pd.to_numeric(frame.get("open_interest"), errors="coerce")
    frame["change_in_open_interest"] = pd.to_numeric(frame.get("change_in_open_interest"), errors="coerce")
    frame["volume"] = pd.to_numeric(frame.get("volume"), errors="coerce")
    call_oi = frame.loc[frame["option_type"].eq("CE"), "open_interest"].sum(min_count=1)
    put_oi = frame.loc[frame["option_type"].eq("PE"), "open_interest"].sum(min_count=1)
    pcr = float(put_oi / call_oi) if pd.notna(call_oi) and call_oi > 0 and pd.notna(put_oi) else None
    result: Dict[str, Any] = {"pcr": pcr, "max_pain": None, "max_ce_oi": None, "max_pe_oi": None, "max_change_oi": None, "max_volume": None}
    for option_type, output_key in (("CE", "max_ce_oi"), ("PE", "max_pe_oi")):
        side = frame[frame["option_type"].eq(option_type)].dropna(subset=["open_interest"])
        if not side.empty:
            top = side.loc[side["open_interest"].idxmax()]
            result[output_key] = {"strike": float(top["strike"]), "value": float(top["open_interest"])}
    change_rows = frame.dropna(subset=["change_in_open_interest"])
    if not change_rows.empty:
        top = change_rows.loc[change_rows["change_in_open_interest"].idxmax()]
        result["max_change_oi"] = {"strike": float(top["strike"]), "option_type": top["option_type"], "value": float(top["change_in_open_interest"])}
    volume_rows = frame.dropna(subset=["volume"])
    if not volume_rows.empty:
        top = volume_rows.loc[volume_rows["volume"].idxmax()]
        result["max_volume"] = {"strike": float(top["strike"]), "option_type": top["option_type"], "value": float(top["volume"])}
    pivot = frame.pivot_table(index="strike", columns="option_type", values="open_interest", aggfunc="sum")
    if len(pivot) >= 3 and {"CE", "PE"}.issubset(pivot.columns) and pivot[["CE", "PE"]].notna().all().all():
        settlements = pivot.index.to_numpy(dtype=float)
        call_strikes = pivot.index.to_numpy(dtype=float)
        ce_oi = pivot["CE"].to_numpy(dtype=float)
        pe_oi = pivot["PE"].to_numpy(dtype=float)
        payouts = [
            (np.maximum(price - call_strikes, 0) * ce_oi).sum()
            + (np.maximum(call_strikes - price, 0) * pe_oi).sum()
            for price in settlements
        ]
        result["max_pain"] = float(settlements[int(pd.Series(payouts).idxmin())])
    return result


def contract_candles(
    data: pd.DataFrame,
    symbol: str,
    expiry: str,
    strike: float,
    option_type: str,
) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    mask = (
        data["symbol"].map(normalize_underlying).eq(normalize_underlying(symbol))
        & data["expiry"].astype(str).eq(str(expiry))
        & pd.to_numeric(data["strike"], errors="coerce").sub(float(strike)).abs().lt(1e-8)
        & data["option_type"].astype(str).str.upper().eq(option_type.upper())
    )
    frame = data.loc[mask].copy()
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    return frame.sort_values("timestamp").set_index("timestamp")


def analyze_contract(
    contract: Optional[pd.Series],
    candles: pd.DataFrame,
    chain_data: pd.DataFrame,
    underlying_price: Optional[float],
) -> Dict[str, Any]:
    from modules.indicators import IndicatorEngine

    engine = IndicatorEngine()
    result: Dict[str, Any] = {
        "premium_trend": "Unavailable",
        "ema_trend": "Unavailable",
        "rsi_momentum": "Unavailable",
        "macd_momentum": "Unavailable",
        "volume_behavior": "Unavailable",
        "oi_analysis": "Insufficient data",
        "iv_condition": "Unavailable",
        "moneyness": "Unavailable",
        "overall": "Neutral",
        "supporting": [],
        "contradicting": [],
        "indicators": {},
    }
    if contract is None:
        return result

    option_type = str(contract.get("option_type", "")).upper()
    strike = pd.to_numeric(pd.Series([contract.get("strike")]), errors="coerce").iloc[0]
    ltp = pd.to_numeric(pd.Series([contract.get("ltp")]), errors="coerce").iloc[0]
    price_change = pd.to_numeric(pd.Series([contract.get("change")]), errors="coerce").iloc[0]
    oi_change = pd.to_numeric(pd.Series([contract.get("change_in_open_interest")]), errors="coerce").iloc[0]
    open_interest = pd.to_numeric(pd.Series([contract.get("open_interest")]), errors="coerce").iloc[0]

    if underlying_price is not None and pd.notna(strike):
        if abs(float(strike) - float(underlying_price)) <= 1e-8:
            result["moneyness"] = "ATM"
        elif option_type == "CE":
            result["moneyness"] = "ITM" if strike < underlying_price else "OTM"
        else:
            result["moneyness"] = "ITM" if strike > underlying_price else "OTM"

    if not candles.empty:
        close = pd.to_numeric(candles["close"], errors="coerce").dropna()
        if len(close) >= 2:
            result["premium_trend"] = "Bullish" if close.iloc[-1] > close.iloc[0] else ("Bearish" if close.iloc[-1] < close.iloc[0] else "Neutral")
            result["supporting" if result["premium_trend"] == "Bullish" else "contradicting"].append(
                f"Premium moved from {close.iloc[0]:.2f} to {close.iloc[-1]:.2f} across the supplied contract candles."
            )
        if len(close) >= 20:
            ema9 = close.ewm(span=9, adjust=False).mean()
            ema20 = close.ewm(span=20, adjust=False).mean()
            result["ema_trend"] = "Bullish" if close.iloc[-1] > ema9.iloc[-1] > ema20.iloc[-1] else (
                "Bearish" if close.iloc[-1] < ema9.iloc[-1] < ema20.iloc[-1] else "Neutral"
            )
            result["indicators"].update({"ema9": float(ema9.iloc[-1]), "ema20": float(ema20.iloc[-1])})
        rsi = engine.rsi_series(close, 14).dropna()
        if not rsi.empty:
            rsi_value = float(rsi.iloc[-1])
            result["indicators"]["rsi"] = rsi_value
            result["rsi_momentum"] = "Bullish" if rsi_value >= 60 else ("Bearish" if rsi_value <= 40 else "Neutral")
        macd = engine.macd_series(close)
        macd_line = macd["macd"].dropna()
        macd_signal = macd["signal"].dropna()
        if not macd_line.empty and not macd_signal.empty:
            result["macd_momentum"] = "Bullish" if macd_line.iloc[-1] > macd_signal.iloc[-1] else (
                "Bearish" if macd_line.iloc[-1] < macd_signal.iloc[-1] else "Neutral"
            )
            result["indicators"].update({"macd": float(macd_line.iloc[-1]), "macd_signal": float(macd_signal.iloc[-1])})
        if "volume" in candles and len(candles) >= 2:
            volume = pd.to_numeric(candles["volume"], errors="coerce").dropna()
            if len(volume) >= 2:
                result["volume_behavior"] = "Increasing" if volume.iloc[-1] > volume.iloc[-2] else (
                    "Decreasing" if volume.iloc[-1] < volume.iloc[-2] else "Unchanged"
                )

    if pd.notna(price_change) and pd.notna(oi_change) and pd.notna(open_interest):
        if price_change > 0 and oi_change > 0:
            result["oi_analysis"] = "Long buildup (price and OI both increased)"
        elif price_change < 0 and oi_change > 0:
            result["oi_analysis"] = "Short buildup (price fell while OI increased)"
        elif price_change > 0 and oi_change < 0:
            result["oi_analysis"] = "Short covering (price rose while OI decreased)"
        elif price_change < 0 and oi_change < 0:
            result["oi_analysis"] = "Long unwinding (price and OI both decreased)"
        else:
            result["oi_analysis"] = "Insufficient directional change"
        result["indicators"].update({"oi": float(open_interest), "change_in_oi": float(oi_change), "price_change": float(price_change)})

    if contract.get("iv") is not None and pd.notna(pd.to_numeric(pd.Series([contract.get("iv")]), errors="coerce").iloc[0]):
        iv = float(contract.get("iv"))
        iv_values = pd.to_numeric(chain_data.get("iv", pd.Series(dtype=float)), errors="coerce").dropna()
        if not iv_values.empty and iv_values.max() <= 1.0:
            iv *= 100
            iv_values *= 100
        if len(iv_values) >= 4:
            low, high = iv_values.quantile([0.25, 0.75])
            result["iv_condition"] = "High" if iv > high else ("Low" if iv < low else "Neutral")
            result["indicators"]["iv"] = iv

    positive = sum(
        result[key] == "Bullish"
        for key in ("premium_trend", "ema_trend", "rsi_momentum", "macd_momentum")
    )
    negative = sum(
        result[key] == "Bearish"
        for key in ("premium_trend", "ema_trend", "rsi_momentum", "macd_momentum")
    )
    result["overall"] = "Bullish" if positive > negative else ("Bearish" if negative > positive else "Neutral")
    result["supporting"].extend(
        f"{key.replace('_', ' ').title()}: {result[key]}."
        for key in ("ema_trend", "rsi_momentum", "macd_momentum")
        if result[key] == result["overall"] and result["overall"] != "Neutral"
    )
    result["contradicting"].extend(
        f"{key.replace('_', ' ').title()}: {result[key]}."
        for key in ("ema_trend", "rsi_momentum", "macd_momentum")
        if result[key] not in (result["overall"], "Unavailable") and result["overall"] != "Neutral"
    )
    return result


def describe_chain_availability(symbol: str, expiry: Optional[str] = None, strike: Optional[float] = None) -> Dict[str, Any]:
    """Report what is known about the requested options chain without inventing data."""
    return {
        "available": False,
        "status": "UNAVAILABLE",
        "source": "native_providers",
        "timestamp": None,
        "adapter": adapter.label(),
        "symbol": symbol,
        "expiry": expiry,
        "strike": strike,
        "message": "Current options chain is not available from the configured providers. Use a permitted uploaded CSV or provide an authorised provider.",
    }


def get_options_chain_given(symbol: str, expiry: Optional[str] = None, strike: Optional[float] = None) -> Dict[str, Any]:
    """Return chain data or UNAVAILABLE with a clear message."""
    # In this minimal build, the adapter is yfinance and cannot produce a full
    # current chain for indices. If a different authorised provider is later
    # wired in, override adapter here.
    data = adapter.get_chain(symbol, expiry, strike)
    if not data.get("available"):
        return describe_chain_availability(symbol, expiry, strike)
    return data
