"""Page 6: AI Market Assistant (Ollama + Qwen3.5 4B)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

from modules.ai_assistant import OllamaAssistant  # noqa: E402

@st.cache_resource(show_spinner=False)
def _assistant_for_model(model_name: str):
    return OllamaAssistant(model=model_name)

CONTEXTS = [
    "market_trends",
    "technical_indicators",
    "ml_predictions",
    "options_chain",
    "options_greeks",
    "order_blocks_fvg",
    "trading_signals",
    "market_summary",
    "stock_performance",
    "custom",
]


def app():
    st.caption("Qwen interprets supplied market data; Python remains the source of all calculated values.")

    assistant = _assistant_for_model(st.session_state.get("ollama_model", "qwen3.5:4b"))
    status = assistant.status()
    status_columns = st.columns(2)
    status_columns[0].metric("Ollama service", "Connected" if status["connected"] else "Unavailable")
    status_columns[1].metric("Qwen model", "Ready" if status["available"] else "Unavailable")
    if not status["available"]:
        st.info("Start Ollama and load qwen3.5:4b to enable answers. Market data and the rest of the terminal remain available.")

    context = st.selectbox("Explanation context", CONTEXTS, index=CONTEXTS.index("market_summary"))
    selected_instrument = st.session_state.get("qe_selected_instrument", "No instrument selected")
    data_context = st.session_state.get("qe_analysis_payload")
    if data_context is None:
        data_context = st.session_state.get("qe_market_snapshot", {})
    st.caption(f"Selected context: {selected_instrument} · Source values only; missing fields remain unavailable.")

    suggested = [
        "Analyse current NIFTY conditions.",
        "Explain this option contract.",
        "What supports or contradicts the current signal?",
        "What are the important risks?",
    ]
    prompt_columns = st.columns(4)
    for column, prompt in zip(prompt_columns, suggested):
        if column.button(prompt, key=f"assistant_suggestion_{suggested.index(prompt)}", use_container_width=True):
            st.session_state["qe_pending_chat_question"] = prompt
            st.rerun()

    history = st.session_state.setdefault("qe_chat_history", [])
    for item in history[-30:]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    prompt = st.chat_input("Ask about the selected instrument or supplied analysis")
    if st.session_state.get("qe_pending_chat_question"):
        prompt = st.session_state.pop("qe_pending_chat_question")
    if prompt:
        history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        if not status["available"]:
            answer = "Ollama/Qwen is unavailable. No AI response was generated; the displayed market data remains unchanged."
        else:
            try:
                with st.spinner("Qwen is interpreting the supplied data..."):
                    result = assistant.chat(prompt, context=context, structured_data=data_context, max_tokens=400)
                answer = result.get("assistant_reply", "No answer returned.") if result.get("success") else result.get("message", "Ollama did not return a response.")
            except Exception as exc:
                answer = f"The local assistant could not complete this request: {exc}"
        history.append({"role": "assistant", "content": answer})
        st.session_state["qe_last_ai_insight"] = answer
        history[:] = history[-30:]
        with st.chat_message("assistant"):
            st.markdown(answer)

    st.caption("Qwen does not execute trades or invent prices, option values, Greeks, or indicators.")


if __name__ == "__main__":
    app()
