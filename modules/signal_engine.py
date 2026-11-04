"""Trading signal engine.

Combines:
- technical indicator reviews
- ML probabilities
- market trend
- support/resistance
- options data when available

Produces BUY / SELL / HOLD and full transparent reasoning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _strength(score: float, threshold: float) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= threshold:
        return "STRONG"
    if score >= threshold * 0.5:
        return "MODERATE"
    return "WEAK"


def generate_signal(
    indicators: Dict[str, Any],
    ml_probs: Dict[str, float],
    trend: str = "NEUTRAL",
    support: Optional[List[float]] = None,
    resistance: Optional[List[float]] = None,
    options_hint: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a transparent signal object."""
    config = config or {}
    config_dict = config if isinstance(config, dict) else {}
    ml_threshold = config_dict.get("ml_probability_threshold", 0.60)
    rsi_oversold = config_dict.get("rsi_oversold", 30)
    rsi_overbought = config_dict.get("rsi_overbought", 70)
    ema_confirmation = config_dict.get("ema_confirmation", True)
    options_confirmation = config_dict.get("options_confirmation", True)

    rsi = indicators.get("rsi")
    stoch = indicators.get("stoch_rsi")
    ema9 = indicators.get("ema9")
    ema20 = indicators.get("ema20")
    ema50 = indicators.get("ema50")
    trend_value = indicators.get("trend_direction", "NEUTRAL") if str(trend).upper() == "NEUTRAL" else trend
    trend_direction = str(trend_value).upper()
    close = indicators.get("close")

    ml_bull = ml_probs.get("BULLISH", 0.0)
    ml_bear = ml_probs.get("BEARISH", 0.0)
    ml_neutral = ml_probs.get("NEUTRAL", 0.0)

    signal = "HOLD"
    reasons: List[str] = []
    weights = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}

    # ML driven weighting
    if ml_bull > 0.5:
        weights["BULLISH"] += ml_bull
    if ml_bear > 0.5:
        weights["BEARISH"] += ml_bear
    weights["NEUTRAL"] += ml_neutral

    # RSI
    rsi_conf = 0.0
    if rsi is not None:
        if rsi <= rsi_oversold:
            rsi_conf = (1.0 - (rsi / rsi_oversold)) * 0.15
            reasons.append("RSI is oversold")
        elif rsi >= rsi_overbought:
            rsi_conf = -((rsi - rsi_overbought) / (100 - rsi_overbought)) * 0.15
            reasons.append("RSI overbought")
        else:
            rsi_conf = 0.0
            reasons.append("RSI neutral")

    # EMA trend
    ema_conf = 0.0
    if ema9 is not None and ema20 is not None and ema50 is not None:
        if ema9 > ema20 > ema50 > 0:
            ema_conf = 0.25
            reasons.append("EMA alignment is bullish")
        elif ema9 < ema20 < ema50:
            ema_conf = -0.25
            reasons.append("EMA alignment is bearish")
        else:
            ema_conf = 0.0
            reasons.append("EMA mixed")
    if not ema_confirmation:
        ema_conf = 0.0

    # probability threshold
    if ml_bull >= ml_threshold:
        weights["BULLISH"] += 0.3
        reasons.append("ML bullish confidence above threshold")
    elif ml_bear >= ml_threshold:
        weights["BEARISH"] += 0.3
        reasons.append("ML bearish confidence above threshold")

    # Options confirmation if present
    options_weight = 0.0
    if options_hint and options_confirmation:
        status = options_hint.get("status", "UNAVAILABLE")
        if status == "UNAVAILABLE":
            reasons.append("Options data unavailable and excluded from scoring")
        else:
            option_direction = options_hint.get("direction")
            if option_direction == "BULLISH":
                options_weight = 0.05
                reasons.append("Supplied options context is bullish")
            elif option_direction == "BEARISH":
                options_weight = -0.05
                reasons.append("Supplied options context is bearish")

    score_bull = weights["BULLISH"] + rsi_conf + ema_conf + options_weight
    score_bear = weights["BEARISH"] - rsi_conf - ema_conf - options_weight

    bullish_confirmed = ml_bull >= ml_threshold or (ema_conf > 0 and rsi_conf > 0)
    bearish_confirmed = ml_bear >= ml_threshold or (ema_conf < 0 and rsi_conf < 0)
    if score_bull > score_bear and score_bull > 0.05 and bullish_confirmed:
        signal = "BUY"
    elif score_bear > score_bull and score_bear > 0.05 and bearish_confirmed:
        signal = "SELL"
    else:
        signal = "HOLD"

    if signal == "HOLD" and (trend_direction == "BULLISH" or trend_direction == "BEARISH"):
        reasons.append(f"Trend {trend_direction} but signals balanced: HOLD")

    stop_loss = None
    target1 = None
    target2 = None
    rr = None
    entry = float(close) if close is not None else None
    support_levels = sorted(float(level) for level in (support or []) if level is not None)
    resistance_levels = sorted(float(level) for level in (resistance or []) if level is not None)
    if entry is not None and signal == "BUY":
        below = [level for level in support_levels if level < entry]
        above = [level for level in resistance_levels if level > entry]
        stop_loss = below[-1] if below else None
        target1 = above[0] if above else None
        target2 = above[1] if len(above) > 1 else None
    elif entry is not None and signal == "SELL":
        above = [level for level in resistance_levels if level > entry]
        below = [level for level in support_levels if level < entry]
        stop_loss = above[0] if above else None
        target1 = below[-1] if below else None
        target2 = below[-2] if len(below) > 1 else None
    if entry is not None and stop_loss is not None and target1 is not None and entry != stop_loss:
        risk = abs(entry - stop_loss)
        reward = abs(target1 - entry)
        rr = reward / risk if risk > 0 else None

    supporting_reasons = []
    contradicting_reasons = []
    for reason in reasons:
        if signal == "BUY" and any(token in reason.lower() for token in ("bearish", "overbought")):
            contradicting_reasons.append(reason)
        elif signal == "SELL" and any(token in reason.lower() for token in ("bullish", "oversold")):
            contradicting_reasons.append(reason)
        elif signal != "HOLD":
            supporting_reasons.append(reason)
    invalidating = []
    if signal == "BUY":
        invalidating.append(f"A close below stop-loss {stop_loss:.2f} invalidates this setup." if stop_loss is not None else "No validated support level is available for a stop-loss.")
        if trend_direction == "BEARISH":
            invalidating.append("The prevailing bearish trend contradicts the bullish setup.")
    elif signal == "SELL":
        invalidating.append(f"A close above stop-loss {stop_loss:.2f} invalidates this setup." if stop_loss is not None else "No validated resistance level is available for a stop-loss.")
        if trend_direction == "BULLISH":
            invalidating.append("The prevailing bullish trend contradicts the bearish setup.")
    else:
        invalidating.append("Wait for price, trend, and model probabilities to align before considering a paper trade.")
    confidence = {
        "BUY": ml_bull,
        "SELL": ml_bear,
        "HOLD": ml_neutral,
    }[signal]

    return {
        "signal": signal,
        "market_direction": "BULLISH" if signal == "BUY" else ("BEARISH" if signal == "SELL" else "NEUTRAL"),
        "suggested_entry": entry,
        "stop_loss": stop_loss,
        "target1": target1,
        "target2": target2,
        "risk_to_reward": rr,
        "confidence": float(confidence),
        "ml_probabilities": ml_probs,
        "supporting_indicators": {
            "rsi": rsi,
            "stoch_rsi": stoch,
            "ema9": ema9,
            "ema20": ema20,
            "ema50": ema50,
            "trend": trend_direction,
        },
        "reasons": reasons,
        "supporting_reasons": supporting_reasons,
        "contradicting_reasons": contradicting_reasons,
        "invalidating_conditions": invalidating,
        "signal_timestamp": (state or {}).get("timestamp"),
        "data_freshness": (state or {}).get("freshness", "UNAVAILABLE"),
    }
