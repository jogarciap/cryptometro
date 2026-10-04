"""Gráficos Plotly que se incrustan en el reporte HTML."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paleta categórica validada; tonos que se leen sobre fondo claro y oscuro
PRECIO, SMA20, SMA50, SMA200 = "#2a78d6", "#eb6834", "#1baf7a", "#d55181"
VOLUMEN = "#8a8984"
TEXTO = "#8a8984"
GRILLA = "rgba(138,137,132,0.18)"


def _estilo(fig: go.Figure, alto: int) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, Segoe UI, sans-serif", size=12, color=TEXTO),
        hovermode="x unified", legend=dict(orientation="h", y=1.08, x=0),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRILLA)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False)
    return fig


def precio_y_volumen(serie: pd.DataFrame, simbolo: str) -> go.Figure:
    """Precio con SMA 20/50/200 arriba y volumen diario abajo (dos paneles, un eje cada uno)."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
                        vertical_spacing=0.04)
    x = serie["fecha"]
    fig.add_trace(go.Scatter(x=x, y=serie["close"], name=f"{simbolo} cierre",
                             line=dict(color=PRECIO, width=2)), row=1, col=1)
    for col, color, nombre in ((("sma20", SMA20, "SMA 20")), ("sma50", SMA50, "SMA 50"),
                               ("sma200", SMA200, "SMA 200")):
        fig.add_trace(go.Scatter(x=x, y=serie[col], name=nombre,
                                 line=dict(color=color, width=1.5)), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=serie["volumen_usd"], name="Volumen USD",
                         marker_color=VOLUMEN, opacity=0.6, showlegend=False), row=2, col=1)
    fig.update_yaxes(title_text="USD", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)
    return _estilo(fig, 460)


def fear_greed(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df["fecha"], y=df["valor"], name="Fear & Greed",
                               mode="lines+markers", line=dict(color=PRECIO, width=2),
                               marker=dict(size=8),
                               customdata=df["texto"],
                               hovertemplate="%{y} (%{customdata})<extra></extra>"))
    for y, txt in ((25, "Miedo extremo"), (75, "Codicia extrema")):
        fig.add_hline(y=y, line=dict(color=GRILLA, dash="dot"),
                      annotation_text=txt, annotation_position="top left",
                      annotation_font_color=TEXTO)
    fig.update_yaxes(range=[0, 100])
    fig.update_layout(showlegend=False)
    return _estilo(fig, 260)


def a_html(fig: go.Figure) -> str:
    # plotly.min.js se guarda una vez en la carpeta reportes/ (funciona sin internet)
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displaylogo": False, "responsive": True})
