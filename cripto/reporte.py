"""Arma el reporte HTML diario a partir de los datos ya calculados."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.offline import get_plotlyjs

from . import graficos
from .config import PLANTILLAS


def _usd(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "s/d"
    for lim, suf in ((1e12, "billones"), (1e9, "mil millones"), (1e6, "M"), (1e3, "mil")):
        if abs(x) >= lim:
            return f"US$ {x / lim:,.2f} {suf}"
    return f"US$ {x:,.2f}"


def _precio(x) -> str:
    if x is None or pd.isna(x):
        return "s/d"
    if x >= 1:
        return f"{x:,.2f}"
    return f"{x:.6g}"


def _pct(x, dec: int = 1) -> str:
    return "s/d" if x is None or pd.isna(x) else f"{x:+.{dec}f}%"


def resumen_mercado(mercado: dict, anterior: dict | None, fg: pd.DataFrame,
                    monedas: pd.DataFrame) -> list[dict]:
    """Cinco líneas, cada una con el dato y su fuente."""
    lineas = []
    lineas.append({
        "texto": f"Capitalización total {_usd(mercado.get('mcap_total_usd'))}, "
                 f"{_pct(mercado.get('cambio_mcap_24h'))} en 24 h.",
        "fuente": "CoinGecko /global"})

    dom = mercado.get("dominancia_btc")
    txt = f"Dominancia de BTC {dom:.1f}%" if dom is not None else "Dominancia de BTC sin datos"
    if anterior and anterior.get("dominancia_btc") is not None and dom is not None:
        txt += f" ({dom - anterior['dominancia_btc']:+.2f} pp vs reporte del {anterior['fecha']})"
    else:
        txt += " (sin reporte anterior para comparar)"
    lineas.append({"texto": txt + ".", "fuente": "CoinGecko /global"})

    if not fg.empty:
        hoy = fg.iloc[-1]
        txt = f"Fear & Greed en {hoy['valor']} ({hoy['texto']})"
        if len(fg) >= 8:
            hace7 = fg.iloc[-8]
            txt += f"; hace 7 días estaba en {hace7['valor']} ({hace7['texto']})"
        lineas.append({"texto": txt + ".", "fuente": "alternative.me"})
    else:
        lineas.append({"texto": "Fear & Greed sin datos hoy.", "fuente": "alternative.me (no respondió)"})

    n = len(monedas)
    suben = int((monedas["cambio_24h"] > 0).sum())
    con_200 = monedas["dist_sma200"].notna()
    sobre_200 = int((monedas.loc[con_200, "dist_sma200"] > 0).sum())
    lineas.append({
        "texto": f"Amplitud: {suben} de {n} monedas del universo suben en 24 h; "
                 f"{sobre_200} de {int(con_200.sum())} con historial suficiente cotizan sobre su SMA 200.",
        "fuente": "Cálculo propio con CoinGecko y velas Binance/CoinGecko"})

    anom = monedas[monedas["anomalias"].fillna("") != ""]
    if len(anom):
        destac = ", ".join(anom.sort_values("vol_relativo", ascending=False)["simbolo"].head(5))
        txt = f"{len(anom)} {'moneda' if len(anom) == 1 else 'monedas'} con movimiento o volumen fuera de lo normal; destacan {destac}."
    else:
        txt = "Ninguna moneda del universo muestra volumen o movimiento fuera de lo normal en la última vela."
    lineas.append({"texto": txt, "fuente": "Cálculo propio sobre la última vela diaria cerrada (UTC)"})
    return lineas


def _num(x):
    """float o None (Jinja no puede comparar NaN ni pd.NA)."""
    try:
        return None if x is None or pd.isna(x) else float(x)
    except (TypeError, ValueError):
        return None


def _fila_tabla(f: pd.Series) -> dict:
    d = {
        "rank": int(f["rank"]) if pd.notna(f["rank"]) else "",
        "simbolo": f["simbolo"], "nombre": f["nombre"],
        "precio": _precio(f["precio"]), "precio_n": f["precio"],
        "c24": _pct(f["cambio_24h"]), "c24_n": f["cambio_24h"],
        "c7": _pct(f["cambio_7d"]), "c7_n": f["cambio_7d"],
        "c30": _pct(f["cambio_30d"]), "c30_n": f["cambio_30d"],
        "vol": _usd(f["volumen_24h"]), "vol_n": f["volumen_24h"],
        "volrel": "s/d" if pd.isna(f.get("vol_relativo")) else f"{f['vol_relativo']:.2f}x",
        "volrel_n": f.get("vol_relativo"),
        "s50": _pct(f.get("dist_sma50")), "s50_n": f.get("dist_sma50"),
        "s200": _pct(f.get("dist_sma200")), "s200_n": f.get("dist_sma200"),
        "volat": "s/d" if pd.isna(f.get("volatilidad_30d")) else f"{f['volatilidad_30d']:.0f}%",
        "volat_n": f.get("volatilidad_30d"),
        "dd": _pct(f.get("caida_max_90d"), 0), "dd_n": f.get("caida_max_90d"),
        "anomalias": f.get("anomalias") or "",
        "fuente": f.get("fuente_velas", ""),
        "dias": int(f["dias_historial"]) if pd.notna(f.get("dias_historial")) else 0,
    }
    return {k: (_num(v) if k.endswith("_n") else v) for k, v in d.items()}


def generar(carpeta: Path, fecha: str, mercado: dict, anterior: dict | None, fg: pd.DataFrame,
            monedas: pd.DataFrame, serie_btc: pd.DataFrame | None, resumen_universo: dict,
            avisos: list[str], cfg: dict) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    js = carpeta / "plotly.min.js"
    if not js.exists():
        js.write_text(get_plotlyjs(), encoding="utf-8")

    for c in ("cambio_24h", "vol_relativo", "dist_sma200", "anomalias"):
        if c not in monedas.columns:
            monedas[c] = pd.NA
    m = monedas.sort_values("rank")
    anom = m[m["anomalias"].fillna("") != ""].sort_values("vol_relativo", ascending=False)

    env = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))
    html = env.get_template("reporte.html").render(
        fecha=fecha,
        generado=datetime.now().strftime("%Y-%m-%d %H:%M"),
        resumen=resumen_mercado(mercado, anterior, fg, m),
        filas=[_fila_tabla(f) for _, f in m.iterrows()],
        anomalias=[_fila_tabla(f) for _, f in anom.iterrows()],
        filas_visibles=cfg["reporte"]["filas_tabla"],
        grafico_btc=graficos.a_html(graficos.precio_y_volumen(serie_btc, "BTC"))
        if serie_btc is not None and len(serie_btc) else None,
        grafico_fg=graficos.a_html(graficos.fear_greed(fg)) if not fg.empty else None,
        universo=resumen_universo,
        umbral_vol=cfg["anomalias"]["volumen_vs_promedio_30d"],
        umbral_sd=cfg["anomalias"]["desviaciones_precio"],
        avisos=avisos,
    )
    ruta = carpeta / f"reporte_{fecha}.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta
