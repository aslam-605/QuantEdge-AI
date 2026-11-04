"""Local AI assistant backed by Ollama and Qwen3.5 4B.

Uses Python requests against http://localhost:11434/api/chat.
The assistant never fabricates market facts and always returns structured
fallbacks when the local LLM is missing, overloaded, or returns invalid data.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:11434/api/chat"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MODEL = "qwen3.5:4b"

SYSTEM_PROMPT = (
    "You are QuantEdge AI's financial market analysis assistant.\n"
    "Rules:\n"
    "- You only use the market data supplied by the caller for factual claims.\n"
    "- Never fabricate prices, open interest, implied volatility, expiry dates, or live data.\n"
    "- State clearly when data is missing, stale, or a source is unavailable.\n"
    "- Distinguish observed facts from predictions.\n"
    "- Explain uncertainty and limitations.\n"
    "- Do not guarantee profits or present predictions as personalised financial advice.\n"
    "- Never execute trades."
)

DEFAULT_CONTEXTS = {
    "market_trends": "Summarise what the supplied price and indicator data shows about the trend, momentum, and volatility. Separate observed data from any prediction.",
    "technical_indicators": "Explain RSI, MACD, EMA, SMA, VWAP, Bollinger Bands, ATR, and stochastic RSI using the supplied values. Give only definitions and rule-based interpretations.",
    "ml_predictions": "Explain the supplied machine-learning probabilities and predicted class. Do not claim historical accuracy guarantees future performance.",
    "options_chain": "Summarise the supplied options data. Explain call/put, strike, expiry, open interest, volume, PCR, volatility, and Greeks from the actual numbers given. Say if the data is UNAVAILABLE.",
    "options_greeks": "Explain delta, gamma, theta, and vega using the supplied values. Do not invent numbers.",
    "order_blocks_fvg": "Explain order blocks, fair value gaps, break of structure, and change of character as rule-based technical interpretations. Clearly state they are not verified institutional flow.",
    "trading_signals": "Explain the supplied signal, suggested entry, stop-loss, targets, RR, and ML probabilities. Do not claim guaranteed results.",
    "market_summary": "Write a short, neutral market summary from the supplied market data. State whether data is LIVE, DELAYED, HISTORICAL, SIMULATED, or UNAVAILABLE.",
    "stock_performance": "Summarise supplied stock performance using the actual price, change, volume, and indicator data. Do not add unsupported facts.",
}


class OllamaAssistant:
    """Thin wrapper around the Ollama chat API."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.connected = False
        self.available = False
        self._probe()

    def _probe(self) -> None:
        try:
            resp = requests.get(self.base_url.replace("/api/chat", "/api/tags"), timeout=3.0)
            self.connected = resp.ok
            self.available = self.connected
            if self.connected:
                try:
                    payload = resp.json()
                    models = [m.get("name") for m in payload.get("models", [])]
                    self.available = any(self.model in m for m in models)
                except Exception:
                    self.available = True
        except Exception as exc:
            logger.warning("Ollama probe failed: %s", exc)
            self.connected = False
            self.available = False

    def chat(
        self,
        message: str,
        context: str = "market_summary",
        structured_data: Optional[Dict[str, Any]] = None,
        max_tokens: int = 400,
    ) -> Dict[str, Any]:
        data = self._build_payload(message, context, structured_data, max_tokens)
        try:
            resp = requests.post(
                self.base_url,
                json=data,
                timeout=self.timeout,
            )
            if not resp.ok:
                return self._failure("ollama_api_error", resp.text)
            payload = resp.json()
            text = payload.get("message", {}).get("content", "") if isinstance(payload, dict) else str(payload)
            return self._parse_text(text, message, context, structured_data)
        except Exception as exc:
            logger.warning("Ollama request failed: %s", exc)
            return self._failure("ollama_api_error", str(exc))

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "available": self.available,
            "model": self.model,
            "api_url": self.base_url,
            "installed": self.connected,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_payload(
        self,
        message: str,
        context: str,
        structured_data: Optional[Dict[str, Any]],
        max_tokens: int,
    ) -> Dict[str, Any]:
        context_text = DEFAULT_CONTEXTS.get(context, "Answer the question using the supplied data only.")
        pmap = {"role": "system", "content": SYSTEM_PROMPT}
        content = (
            "Context:\n"
            f"{context_text}\n\n"
            "Data:\n"
        )
        if structured_data:
            payload_for_llm = json.dumps(structured_data, ensure_ascii=False, indent=2)
            content += payload_for_llm
        else:
            content += "No structured data supplied."

        content += (
            f"\n\nUser: {message}\n"
            "Assistant:"
        )
        return {
            "model": self.model,
            "messages": [pmap, {"role": "user", "content": content}],
            "stream": False,
            "options": {"temperature": 0.25, "num_ctx": 512},
            "keep_alive": 300,
        }

    def _parse_text(self, text: str, user_message: str, context: str, structured_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        clean = " ".join(text.split())
        if not clean:
            return self._failure("empty_response", user_message)
        try:
            json.loads(clean)
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return {
                    "available": True,
                    "success": True,
                    "text": text,
                    "assistant_reply": parsed.get("answer") or clean,
                    "structured": parsed,
                    "context": context,
                }
        except json.JSONDecodeError:
            pass

        return {
            "available": True,
            "success": True,
            "text": clean,
            "assistant_reply": clean,
            "structured": None,
            "context": context,
        }

    def _failure(self, code: str, detail: str) -> Dict[str, Any]:
        return {
            "available": False,
            "success": False,
            "error_code": code,
            "message": detail,
            "assistant_reply": "I could not reach the local assistant right now.",
            "structured": None,
            "context": "default",
        }
