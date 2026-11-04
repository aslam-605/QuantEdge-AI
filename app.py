import logging
import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="QuantEdge AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from modules.market_data import market  # noqa: E402
LOG_PATH = _PROJECT_ROOT / "logs" / "quantedge_app.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.getLogger().handlers.clear()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)

from utils.ui import apply_theme, get_market_context  # noqa: E402


def _toggle_theme() -> None:
    st.session_state["qe_theme"] = "Light" if st.session_state.get("qe_theme", "Dark") == "Dark" else "Dark"

st.logo(str(_PROJECT_ROOT / "assets" / "quantedge_logo.svg"), size="large")
st.sidebar.markdown("<div class='qe-brand-name'>QuantEdge AI</div>", unsafe_allow_html=True)

page = st.navigation(
    {
        "Markets": [
            st.Page("pages/1_Market_Overview.py", title="Market Overview", icon=":material/dashboard:", default=True),
        ],
        "Research": [
            st.Page("pages/2_Stock_Analysis.py", title="Stock Explorer", icon=":material/search:"),
            st.Page("pages/3_Technical_Analysis.py", title="Technical Analysis", icon=":material/query_stats:"),
            st.Page("pages/4_Options_Chain.py", title="Options Chain", icon=":material/candlestick_chart:"),
            st.Page("pages/5_AI_Predictions.py", title="AI Predictions", icon=":material/insights:"),
        ],
        "Assistant": [
            st.Page("pages/6_AI_Assistant.py", title="AI Assistant", icon=":material/chat:")
        ],
        "Trading": [
            st.Page("pages/7_Paper_Trading.py", title="Paper Trading", icon=":material/swap_vert:"),
            st.Page("pages/8_Portfolio.py", title="Portfolio", icon=":material/account_balance_wallet:"),
        ],
        "System": [
            st.Page("pages/9_Settings.py", title="Settings", icon=":material/settings:")
        ],
    },
    position="sidebar",
)

st.session_state.setdefault("qe_theme", "Dark")
market_context = get_market_context(st)
header_columns = st.columns([1.8, 1.6, 2.4, 0.9, 1.1], vertical_alignment="center")
with header_columns[0]:
    st.markdown(f"<div class='qe-topbar-title'>{page.title or 'QuantEdge AI'}</div>", unsafe_allow_html=True)
with header_columns[1]:
    st.markdown(f"<div class='qe-topbar-context'>{market_context['instrument']}</div>", unsafe_allow_html=True)
with header_columns[2]:
    st.markdown(
        f"<div class='qe-topbar-context'><span class='qe-status-dot'>●</span>{market_context['freshness']} · "
        f"{market_context['source']}<br>{market_context['timestamp']}</div>",
        unsafe_allow_html=True,
    )
with header_columns[3]:
    refresh = st.button("Refresh", icon=":material/refresh:", use_container_width=True, key="qe_refresh")
with header_columns[4]:
    current_theme = st.session_state["qe_theme"]
    toggle_label = "Light mode" if current_theme == "Dark" else "Dark mode"
    toggle_icon = ":material/light_mode:" if current_theme == "Dark" else ":material/dark_mode:"
    st.button(
        toggle_label,
        icon=toggle_icon,
        key="qe_theme_toggle_button",
        help="Switch application appearance.",
        use_container_width=True,
        on_click=_toggle_theme,
    )
theme = st.session_state["qe_theme"]

apply_theme(st, theme or "Dark")
if refresh:
    market.clear_cache()
    st.cache_data.clear()
    st.rerun()

context_before = get_market_context(st)
page.run()
if get_market_context(st) != context_before:
    st.rerun()
