"""Shared visual styling and page context for the Streamlit terminal."""

from __future__ import annotations

from typing import Any, Dict


THEMES: Dict[str, Dict[str, str]] = {
    "Dark": {
        "background": "#10171D",
        "surface": "#18232B",
        "surface_alt": "#1D2A33",
        "text": "#E7EEF1",
        "muted": "#9AAAB2",
        "border": "#2C3B44",
        "accent": "#18A999",
        "bullish": "#31B982",
        "bearish": "#E46F70",
    },
    "Light": {
        "background": "#F2F6F6",
        "surface": "#FFFFFF",
        "surface_alt": "#E9F0F0",
        "text": "#17262D",
        "muted": "#61747D",
        "border": "#D3DFE1",
        "accent": "#087F75",
        "bullish": "#168A59",
        "bearish": "#C74448",
    },
}


def apply_theme(st: Any, theme_name: str) -> None:
    colors = THEMES.get(theme_name, THEMES["Dark"])
    st.markdown(
        f"""
        <style>
        :root {{
            --qe-bg: {colors['background']};
            --qe-surface: {colors['surface']};
            --qe-surface-alt: {colors['surface_alt']};
            --qe-text: {colors['text']};
            --qe-muted: {colors['muted']};
            --qe-border: {colors['border']};
            --qe-accent: {colors['accent']};
            --qe-bullish: {colors['bullish']};
            --qe-bearish: {colors['bearish']};
        }}
        .stApp, [data-testid="stAppViewContainer"] {{
            background: var(--qe-bg);
            color: var(--qe-text);
            font-family: "Aptos", "Segoe UI Variable", "Segoe UI", sans-serif;
            letter-spacing: 0;
        }}
        [data-testid="stHeader"] {{ background: transparent; }}
        [data-testid="stSidebar"] {{
            background: var(--qe-surface);
            border-right: 1px solid var(--qe-border);
        }}
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: var(--qe-muted); }}
        h1, h2, h3 {{ color: var(--qe-text); letter-spacing: 0; }}
        h1 {{ font-size: 1.75rem; font-weight: 680; }}
        h2 {{ font-size: 1.35rem; font-weight: 640; }}
        h3 {{ font-size: 1.02rem; font-weight: 620; }}
        [data-testid="stMetric"] {{
            background: var(--qe-surface);
            border: 1px solid var(--qe-border);
            border-radius: 9px;
            padding: 14px 16px;
            min-height: 92px;
        }}
        [data-testid="stMetricLabel"] {{ color: var(--qe-muted); font-size: .82rem; }}
        [data-testid="stMetricValue"] {{ color: var(--qe-text); font-size: 1.42rem; }}
        [data-testid="stMetricDelta"] svg {{ display: inline-block; }}
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            border: 1px solid var(--qe-border);
            border-radius: 8px;
            overflow: hidden;
        }}
        div.stButton > button, div.stFormSubmitButton > button {{
            border-radius: 7px;
            border-color: var(--qe-border);
            min-height: 2.45rem;
        }}
        div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {{
            background: var(--qe-accent);
            border-color: var(--qe-accent);
            color: #FFFFFF;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            color: var(--qe-accent);
            border-bottom-color: var(--qe-accent);
        }}
        .qe-topbar {{
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid var(--qe-border);
            padding: 0 0 12px 0;
            margin: 0 0 18px 0;
        }}
        .qe-topbar-title {{ color: var(--qe-text); font-size: 1.5rem; font-weight: 680; }}
        .qe-topbar-context {{ color: var(--qe-muted); font-size: .78rem; }}
        .qe-status-dot {{ color: var(--qe-accent); padding-right: 5px; }}
        .qe-section-label {{ color: var(--qe-muted); font-size: .72rem; text-transform: uppercase; }}
        .qe-brand-name {{ color: var(--qe-text); font-size: 1.04rem; font-weight: 700; padding: 4px 0 14px 0; }}
        @media (max-width: 720px) {{
            [data-testid="stMetric"] {{ padding: 10px 11px; min-height: 82px; }}
            [data-testid="stMetricValue"] {{ font-size: 1.15rem; }}
            h1 {{ font-size: 1.5rem; }}
            .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_market_context(st: Any, instrument: str, source: str, freshness: str, timestamp: str | None) -> None:
    st.session_state["qe_market_context"] = {
        "instrument": instrument,
        "source": source,
        "freshness": freshness,
        "timestamp": timestamp,
    }


def get_market_context(st: Any) -> Dict[str, str]:
    context = st.session_state.get("qe_market_context", {})
    return {
        "instrument": str(context.get("instrument", "No instrument selected")),
        "source": str(context.get("source", "Source unavailable")),
        "freshness": str(context.get("freshness", "UNAVAILABLE")),
        "timestamp": str(context.get("timestamp") or "Timestamp unavailable"),
    }