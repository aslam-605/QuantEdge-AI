"""Plotly charting helpers for QuantEdge AI.

Provides reusable candlestick charts, volume, indicators, OOP/GTC zones,
entry/exit markers, and clean dark financial styling.

All charts are interactive Plotly figures.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# Dark professional theme colours
BACKGROUND = "#0B1120"
GRID = "#1E2A3A"
TEXT = "#E5E7EB"
GREEN = "#22C55E"
RED = "#EF4444"
INDICATOR_COLORS = {
    "ema9": "#22D3EE",
    "ema20": "#FBBF24",
    "ema50": "#F97316",
    "vwap": "#38BDF8",
    "bb_upper": "#FBBF24",
    "bb_middle": "#9CA3AF",
    "bb_lower": "#38BDF8",
    "volume": "#4B5563",
    "buy": "#22C55E",
    "sell": "#EF4444",
    "support": "#22C55E",
    "resistance": "#EF4444",
    "signal": "#FBBF24",
}


def _chart_palette(theme: str = "Dark") -> Dict[str, str]:
    light = theme == "Light"
    if light:
        return {"background": "#F2F6F6", "plot": "#FFFFFF", "grid": "#D3DFE1", "text": "#17262D", "panel": "#FFFFFF"}
    return {"background": BACKGROUND, "plot": BACKGROUND, "grid": GRID, "text": TEXT, "panel": "#111A20"}


def _base_layout(title: str = "Chart", theme: str = "Dark") -> go.Layout:
    palette = _chart_palette(theme)
    layout = go.Layout(
        paper_bgcolor=palette["background"],
        plot_bgcolor=palette["plot"],
        font={"color": palette["text"], "family": "Aptos, Segoe UI, sans-serif"},
        xaxis={"gridcolor": palette["grid"], "zerolinecolor": palette["grid"], "color": palette["text"]},
        yaxis={"gridcolor": palette["grid"], "zerolinecolor": palette["grid"], "color": palette["text"]},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        hoverlabel={"bgcolor": palette["panel"], "font": {"color": palette["text"]}},
        legend={"bgcolor": palette["background"], "traceorder": "normal", "font": {"color": palette["text"]}},
        hovermode="x unified",
        title=title,
    )
    return layout


def _trace_line(x, y, color, name, width=1.0, mode="lines"):
    return go.Scatter(
        x=list(x) if x is not None else [],
        y=list(y) if y is not None else [],
        mode=mode,
        line=dict(color=color, width=width),
        name=name,
        hovertemplate="%{y:.4f}<extra>%{name}</extra>",
    )


def candlestick_figure(
    df: pd.DataFrame,
    title: str = "Price Candle Chart",
    show_volume: bool = True,
    indicators: Optional[Dict[str, pd.Series]] = None,
    entry: Optional[Dict[str, float]] = None,
    exit: Optional[Dict[str, float]] = None,
    support_levels: Optional[List[float]] = None,
    resistance_levels: Optional[List[float]] = None,
    buy_signals: Optional[List[Dict[str, Any]]] = None,
    sell_signals: Optional[List[Dict[str, Any]]] = None,
    height: int = 620,
) -> go.Figure:
    """Build a clean interactive multi-panel chart."""
    df = df if df is not None else pd.DataFrame()
    if df.empty:
        fig = go.Figure()
        fig.update_layout(_base_layout(title))
        return fig

    fig = go.Figure()

    open_col = "open" if "open" in df.columns else None
    high_col = "high" if "high" in df.columns else None
    low_col = "low" if "low" in df.columns else None
    close_col = "close" if "close" in df.columns else None
    volume_col = "volume" if "volume" in df.columns else None

    if open_col and high_col and low_col and close_col:
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df[open_col],
                high=df[high_col],
                low=df[low_col],
                close=df[close_col],
                name="OHLC",
                increasing_line_color=GREEN,
                decreasing_line_color=RED,
                hovertemplate="Date: %{x|%Y-%m-%d}<br>Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<extra>OHLC</extra>",
            )
        )

    if volume_col is not None and show_volume:
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df[volume_col],
                name="Volume",
                marker_color=INDICATOR_COLORS["volume"],
                opacity=0.55,
                hovertemplate="Volume: %{y:,.0f}<extra>Volume</extra>",
            )
        )

    indicators = indicators or {}
    for key, series in indicators.items():
        if not isinstance(series, pd.Series) or series.empty:
            continue
        color = INDICATOR_COLORS.get(key, "#AEB4BE")
        fig.add_trace(
            _trace_line(
                series.index,
                series,
                color,
                key,
                width=1.4,
            )
        )

    # Entry / exit markers
    for mark in (entry, exit):
        if mark:
            fig.add_trace(
                go.Scatter(
                    x=[mark["x"]],
                    y=[mark["y"]],
                    mode="markers",
                    marker=dict(size=14, color=INDICATOR_COLORS.get(mark.get("tag", "signal"), "#FBBF24"), symbol="triangle-up" if mark["tag"] == "entry" else "triangle-down"),
                    name=f"{mark['tag'].upper()}",
                    hovertemplate=f"{mark.get('label', mark['tag'].upper())}: %{y:.2f}<extra>{mark.get('label', mark['tag'].upper())}</extra>",
                )
            )

    # Support / resistance
    for level in (support_levels or []):
        fig.add_trace(_trace_line(df.index, [level] * len(df), INDICATOR_COLORS["support"], "S/R", width=1.2))
    for level in (resistance_levels or []):
        fig.add_trace(_trace_line(df.index, [level] * len(df), INDICATOR_COLORS["resistance"], "S/R", width=1.2))

    # Signal markers
    for sig in (buy_signals or []):
        fig.add_trace(
            go.Scatter(
                x=[sig["x"]], y=[sig["y"]],
                mode="markers", marker=dict(size=16, color=GREEN, symbol="triangle-up"),
                name="Buy Signal", hovertemplate="Buy signal<extra>Buy</extra>",
            )
        )
    for sig in (sell_signals or []):
        fig.add_trace(
            go.Scatter(
                x=[sig["x"]], y=[sig["y"]],
                mode="markers", marker=dict(size=16, color=RED, symbol="triangle-down"),
                name="Sell Signal", hovertemplate="Sell signal<extra>Sell</extra>",
            )
        )

    fig.update_layout(
        _base_layout(title),
        height=height,
        yaxis=dict(rangemode="tozero"),
        showlegend=True,
    )
    return fig


CHART_INDICATORS = ["EMA 9", "EMA 20", "EMA 50", "VWAP", "Bollinger Bands", "RSI", "MACD", "Volume"]


def _chart_layers(df: pd.DataFrame, selected: List[str]):
    from modules.indicators import IndicatorEngine

    engine = IndicatorEngine()
    indicators: Dict[str, pd.Series] = {}
    if "EMA 9" in selected:
        indicators["ema9"] = engine.ema_series(df["close"], 9)
    if "EMA 20" in selected:
        indicators["ema20"] = engine.ema_series(df["close"], 20)
    if "EMA 50" in selected:
        indicators["ema50"] = engine.ema_series(df["close"], 50)
    if "VWAP" in selected and {"close", "volume"}.issubset(df.columns):
        indicators["vwap"] = engine.vwap_series(df["close"], df["volume"])
    bands = engine.bollinger_bands(df["close"]) if "Bollinger Bands" in selected else {}
    if bands:
        indicators.update({key: value for key, value in bands.items()})
    rsi = engine.rsi_series(df["close"]) if "RSI" in selected else None
    macd = engine.macd_series(df["close"]) if "MACD" in selected else None
    return indicators, rsi, macd


def interactive_candlestick_figure(
    df: pd.DataFrame,
    title: str,
    selected: List[str],
    support_levels: Optional[List[float]] = None,
    resistance_levels: Optional[List[float]] = None,
    signal: Optional[Dict[str, Any]] = None,
    height: int = 720,
    theme: str = "Dark",
) -> go.Figure:
    """Create a consistent price/volume/oscillator view from supplied candles."""
    if df is None or df.empty:
        return candlestick_figure(df, title=title, height=height)

    has_ohlc = {"open", "high", "low", "close"}.issubset(df.columns)
    if not has_ohlc:
        return candlestick_figure(df, title=title, height=height)
    indicators, rsi, macd = _chart_layers(df, selected)
    panels = [("price", 0.62)]
    if "Volume" in selected and "volume" in df.columns:
        panels.append(("volume", 0.16))
    if rsi is not None:
        panels.append(("rsi", 0.12))
    if macd is not None:
        panels.append(("macd", 0.16))
    total = sum(weight for _, weight in panels)
    row_heights = [weight / total for _, weight in panels]
    subplot_titles = ["Price"] + [name.upper() for name, _ in panels[1:]]
    fig = make_subplots(
        rows=len(panels),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
            increasing_line_color=GREEN,
            decreasing_line_color=RED,
            hovertemplate=(
                "Date: %{x|%Y-%m-%d %H:%M}<br>Open: %{open:.2f}<br>"
                "High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}"
                "<extra>OHLC</extra>"
            ),
        ),
        row=1,
        col=1,
    )
    for key, series in indicators.items():
        color = INDICATOR_COLORS.get(key, "#AEB4BE")
        fig.add_trace(_trace_line(series.index, series, color, key.upper(), 1.5), row=1, col=1)

    row_for = {name: index + 1 for index, (name, _) in enumerate(panels)}
    if "volume" in row_for:
        colors = [GREEN if close >= open_ else RED for open_, close in zip(df["open"], df["close"])]
        fig.add_trace(
            go.Bar(x=df.index, y=df["volume"], name="Volume", marker_color=colors, opacity=0.65),
            row=row_for["volume"], col=1,
        )
    if rsi is not None:
        row = row_for["rsi"]
        fig.add_trace(_trace_line(rsi.index, rsi, "#FBBF24", "RSI (14)"), row=row, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color=RED, row=row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color=GREEN, row=row, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=row, col=1)
    if macd is not None:
        row = row_for["macd"]
        fig.add_trace(_trace_line(macd["macd"].index, macd["macd"], "#38BDF8", "MACD"), row=row, col=1)
        fig.add_trace(_trace_line(macd["signal"].index, macd["signal"], "#FBBF24", "Signal"), row=row, col=1)
        fig.add_trace(
            go.Bar(x=macd["hist"].index, y=macd["hist"], name="MACD Histogram", marker_color="#64748B"),
            row=row, col=1,
        )
        fig.update_yaxes(title_text="MACD", row=row, col=1)

    for level in support_levels or []:
        fig.add_hline(y=level, line_dash="dash", line_color=GREEN, annotation_text=f"Support {level:.2f}", row=1, col=1)
    for level in resistance_levels or []:
        fig.add_hline(y=level, line_dash="dash", line_color=RED, annotation_text=f"Resistance {level:.2f}", row=1, col=1)
    if signal and signal.get("signal") in {"BUY", "SELL"}:
        latest_x = df.index[-1]
        latest_y = float(df["close"].iloc[-1])
        bullish = signal["signal"] == "BUY"
        fig.add_trace(
            go.Scatter(
                x=[latest_x], y=[latest_y], mode="markers+text",
                marker={"size": 14, "color": GREEN if bullish else RED, "symbol": "triangle-up" if bullish else "triangle-down"},
                text=[f"Current {signal['signal']} signal"], textposition="top center",
                name=f"Current {signal['signal']} signal",
            ),
            row=1, col=1,
        )
        for field, color, label in (
            ("suggested_entry", "#FBBF24", "Entry"),
            ("stop_loss", RED, "Stop-loss"),
            ("target1", GREEN, "Target 1"),
            ("target2", "#2DD4BF", "Target 2"),
        ):
            value = signal.get(field)
            if value is not None:
                fig.add_hline(y=float(value), line_dash="dot", line_color=color, annotation_text=label, row=1, col=1)

    layout = _base_layout(title, theme).to_plotly_json()
    layout.update(
        {
            "height": height,
            "showlegend": True,
            "legend": {"orientation": "h", "y": 1.12, "bgcolor": _chart_palette(theme)["background"], "font": {"color": _chart_palette(theme)["text"]}},
            "margin": {"l": 55, "r": 30, "t": 75, "b": 45},
            "xaxis_rangeslider_visible": False,
            "uirevision": title,
        }
    )
    fig.update_layout(**layout)
    fig.update_xaxes(
        title_text="Date / time",
        rangeselector={"buttons": [
            {"count": 1, "label": "1M", "step": "month", "stepmode": "backward"},
            {"count": 3, "label": "3M", "step": "month", "stepmode": "backward"},
            {"count": 6, "label": "6M", "step": "month", "stepmode": "backward"},
            {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
            {"step": "all", "label": "All"},
        ]},
        gridcolor=_chart_palette(theme)["grid"],
    )
    fig.update_yaxes(title_text="Price", row=1, col=1, gridcolor=_chart_palette(theme)["grid"])
    return fig


def render_interactive_chart(
    df: pd.DataFrame,
    title: str,
    key: str,
    default_indicators: Optional[List[str]] = None,
    support_levels: Optional[List[float]] = None,
    resistance_levels: Optional[List[float]] = None,
    signal: Optional[Dict[str, Any]] = None,
    height: int = 720,
) -> go.Figure:
    import streamlit as st

    configured = st.session_state.get("qe_default_chart_indicators")
    default = configured if configured is not None else (default_indicators or ["EMA 9", "EMA 20", "Volume"])
    selected = st.multiselect(
        "Chart indicators",
        options=CHART_INDICATORS,
        default=[item for item in default if item in CHART_INDICATORS],
        key=f"{key}_indicators",
    )
    fig = interactive_candlestick_figure(
        df,
        title,
        selected,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        signal=signal,
        height=height,
        theme=st.session_state.get("qe_theme", "Dark"),
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": True, "responsive": True},
    )
    return fig


def indicator_table(df: pd.DataFrame) -> go.Figure:
    """Render a small DataFrame as a table figure."""
    if df is None or df.empty:
        return go.Figure()
    header = list(df.columns)
    cells = [[str(v) for v in row] for row in df.itertuples(index=False)]
    fig = go.Figure(data=go.Table(header=dict(values=header, fill_color="#1E2A3A", font_color=TEXT), cells=dict(values=cells, fill_color="#0B1120", font_color=TEXT)))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return fig


def strip_legend(fig: go.Figure) -> go.Figure:
    fig.update_layout(showlegend=False)
    return fig
