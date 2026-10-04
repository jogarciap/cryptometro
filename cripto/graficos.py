"""Gráficos del reporte: Plotly para los interactivos y SVG en línea para los minigráficos."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paleta categórica validada; tonos que se leen sobre fondo claro y oscuro
PRECIO, SMA20, SMA50, SMA200 = "#2a78d6", "#eb6834", "#1baf7a", "#d55181"
SUBE, BAJA = "#1f9d55", "#d64545"
NEUTRO = "#9a9993"
TEXTO = "#8a8984"
GRILLA = "rgba(138,137,132,0.18)"
FUENTE = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"


def _estilo(fig: go.Figure, alto: int, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=8, r=8, t=36 if leyenda else 12, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FUENTE, size=12, color=TEXTO),
        hovermode="x unified", showlegend=leyenda,
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0),
        hoverlabel=dict(font=dict(family=FUENTE)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRILLA, ticks="outside", tickcolor=GRILLA)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False)
    return fig


def precio_y_volumen(serie: pd.DataFrame, simbolo: str) -> go.Figure:
    """Precio con SMA 20/50/200, volumen diario y RSI en tres paneles con su propio eje."""
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.62, 0.18, 0.20],
                        vertical_spacing=0.035)
    x = serie["fecha"]
    fig.add_trace(go.Scatter(x=x, y=serie["close"], name=f"{simbolo}",
                             line=dict(color=PRECIO, width=2)), row=1, col=1)
    for col, color, nombre in (("sma20", SMA20, "SMA 20"), ("sma50", SMA50, "SMA 50"),
                               ("sma200", SMA200, "SMA 200")):
        fig.add_trace(go.Scatter(x=x, y=serie[col], name=nombre,
                                 line=dict(color=color, width=1.5)), row=1, col=1)
    sube = serie["close"].diff().fillna(0) >= 0
    fig.add_trace(go.Bar(x=x, y=serie["volumen_usd"], name="Volumen",
                         marker_color=np.where(sube, SUBE, BAJA), marker_line_width=0,
                         opacity=0.55, showlegend=False,
                         hovertemplate="Volumen US$ %{y:.3s}<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=serie["rsi14"], name="RSI 14", showlegend=False,
                             line=dict(color=TEXTO, width=1.5),
                             hovertemplate="RSI %{y:.0f}<extra></extra>"), row=3, col=1)
    for y in (30, 70):
        fig.add_hline(y=y, line=dict(color=GRILLA, dash="dot", width=1), row=3, col=1)
    fig.update_yaxes(title_text="USD", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], tickvals=[30, 70], row=3, col=1)
    return _estilo(fig, 560)


def fear_greed(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df["fecha"], y=df["valor"], name="Fear & Greed",
                               mode="lines+markers", line=dict(color=PRECIO, width=2),
                               marker=dict(size=7), customdata=df["texto"],
                               hovertemplate="%{y} (%{customdata})<extra></extra>"))
    for y0, y1, color in ((0, 25, BAJA), (75, 100, SUBE)):
        fig.add_hrect(y0=y0, y1=y1, fillcolor=color, opacity=0.06, line_width=0)
    fig.add_annotation(x=0, xref="paper", y=12, text="Miedo extremo", showarrow=False,
                       xanchor="left", font=dict(color=TEXTO, size=11))
    fig.add_annotation(x=0, xref="paper", y=88, text="Codicia extrema", showarrow=False,
                       xanchor="left", font=dict(color=TEXTO, size=11))
    fig.update_yaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100])
    return _estilo(fig, 260, leyenda=False)


def mapa(m: pd.DataFrame, destacadas: set[str]) -> go.Figure:
    """Tendencia (distancia a SMA 200) contra riesgo (volatilidad); las destacadas con etiqueta."""
    d = m.dropna(subset=["dist_sma200", "volatilidad_30d"]).copy()
    d["x"] = d["dist_sma200"].clip(-80, 200)
    d["tam"] = (np.log10(d["mcap"].clip(lower=1e7)) - 6.5).clip(lower=0.5) * 6
    d["pt"] = d["puntaje"].map(lambda v: "s/d" if pd.isna(v) else f"{v:.0f}")
    hover = ("<b>%{customdata[0]}</b> %{customdata[1]}<br>vs SMA 200: %{x:+.1f}%<br>"
             "Volatilidad 30 d: %{y:.0f}%<br>Puntaje: %{customdata[2]}<extra></extra>")
    fig = go.Figure()
    resto = d[~d["simbolo"].isin(destacadas)]
    top = d[d["simbolo"].isin(destacadas)]
    fig.add_trace(go.Scatter(x=resto["x"], y=resto["volatilidad_30d"], mode="markers", name="Universo",
                             marker=dict(size=resto["tam"], color=NEUTRO, opacity=0.45, line=dict(width=0)),
                             customdata=resto[["simbolo", "nombre", "pt"]], hovertemplate=hover))
    fig.add_trace(go.Scatter(x=top["x"], y=top["volatilidad_30d"], mode="markers+text", name="Top por puntaje",
                             text=top["simbolo"], textposition="top center",
                             textfont=dict(size=11, color=PRECIO),
                             marker=dict(size=top["tam"].clip(lower=9), color=PRECIO, opacity=0.9,
                                         line=dict(width=1.5, color="rgba(255,255,255,0.8)")),
                             customdata=top[["simbolo", "nombre", "pt"]], hovertemplate=hover))
    fig.add_vline(x=0, line=dict(color=GRILLA, width=1.5))
    mediana = d["volatilidad_30d"].median()
    fig.add_hline(y=mediana, line=dict(color=GRILLA, width=1.5, dash="dot"))
    for x, y, t, xa in ((1, 1, "Alcista y volátil", "right"), (0, 1, "Bajista y volátil", "left"),
                        (1, 0, "Alcista y estable", "right"), (0, 0, "Bajista y estable", "left")):
        fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=t, showarrow=False,
                           xanchor=xa, yanchor="top" if y else "bottom", font=dict(size=11, color=TEXTO))
    fig.update_xaxes(title_text="Distancia a la SMA 200 (%) → más alcista", ticksuffix="%")
    fig.update_yaxes(title_text="Volatilidad anualizada 30 d (%) → más riesgo", ticksuffix="%")
    fig.update_layout(hovermode="closest")
    return _estilo(fig, 460)


def vs_btc(top: pd.DataFrame) -> go.Figure:
    """Rendimiento a 30 días contra BTC, en puntos porcentuales."""
    d = top.dropna(subset=["vs_btc_30d"]).sort_values("vs_btc_30d")
    colores = [SUBE if v >= 0 else BAJA for v in d["vs_btc_30d"]]
    fig = go.Figure(go.Bar(x=d["vs_btc_30d"], y=d["simbolo"], orientation="h", marker_color=colores,
                           marker_line_width=0, text=[f"{v:+.1f} pp" for v in d["vs_btc_30d"]],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:+.1f} pp vs BTC en 30 días<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=TEXTO, width=1))
    lo, hi = min(0, d["vs_btc_30d"].min()), max(0, d["vs_btc_30d"].max())
    margen = (hi - lo) * 0.22 or 1
    fig.update_xaxes(title_text="Puntos porcentuales vs BTC (30 días)", zeroline=False,
                     range=[lo - (margen if lo < 0 else 0), hi + margen])
    fig.update_layout(hovermode="closest", bargap=0.35)
    return _estilo(fig, max(220, 34 * len(d) + 80), leyenda=False)


def sparkline(valores: list[float] | None, ancho: int = 120, alto: int = 32) -> str:
    """Minigráfico SVG de los últimos cierres; verde si termina arriba del inicio, rojo si abajo."""
    if not valores or len(valores) < 2:
        return ""
    v = [x for x in valores if x is not None and not math.isnan(x)]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rango = (hi - lo) or 1
    pasos = (ancho - 4) / (len(v) - 1)
    pts = [(2 + i * pasos, 2 + (alto - 4) * (1 - (x - lo) / rango)) for i, x in enumerate(v)]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    color = SUBE if v[-1] >= v[0] else BAJA
    ux, uy = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" '
            f'role="img" aria-label="Precio últimos {len(v)} días">'
            f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ux:.1f}" cy="{uy:.1f}" r="2.4" fill="{color}"/></svg>')


def a_html(fig: go.Figure) -> str:
    # plotly.min.js se guarda una vez en la carpeta reportes/ (funciona sin internet)
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displaylogo": False, "responsive": True,
                               "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
