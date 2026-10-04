"""Puntaje de 0 a 100 por moneda, combinando componentes con los pesos de config.yaml.

Cada métrica se convierte en percentil dentro del universo del día (0 = la peor,
100 = la mejor). Un componente es el promedio de sus métricas disponibles, y el
puntaje final es el promedio ponderado de los componentes con datos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COMPONENTES = ("tendencia", "momentum", "sentimiento", "riesgo")


def _pct(s: pd.Series, mayor_es_mejor: bool = True) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    p = s.rank(pct=True, ascending=mayor_es_mejor) * 100
    return p.where(s.notna())


def calcular(m: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Agrega columnas p_tendencia, p_momentum, p_sentimiento, p_riesgo, puntaje y nota_puntaje."""
    c = cfg["puntaje"]
    df = m.copy()
    apto = df["dias_historial"].fillna(0) >= c["dias_minimos"]

    cruce = df["cruce_50_200"].map({True: 100.0, False: 0.0}) if "cruce_50_200" in df else np.nan
    tendencia = pd.concat([
        _pct(df["dist_sma50"]),
        _pct(df["dist_sma200"]),
        pd.Series(cruce, index=df.index, dtype=float),
        _pct(df["macd_hist_pct"]),
    ], axis=1).mean(axis=1)

    rsi_score = (100 - (df["rsi14"] - c["rsi_ideal"]).abs() * 2.5).clip(0, 100)
    momentum = pd.concat([
        _pct(df["ret_7d"]),
        _pct(df["ret_30d"]),
        rsi_score,
        _pct(df["vol_relativo"].clip(upper=5)),
    ], axis=1).mean(axis=1)

    riesgo = pd.concat([
        _pct(df["volatilidad_30d"], mayor_es_mejor=False),
        _pct(df["caida_max_90d"]),          # menos negativo = mejor
        _pct(df["volumen_24h"]),            # más liquidez = mejor
    ], axis=1).mean(axis=1)

    sentimiento = df["sentimiento"] if "sentimiento" in df else pd.Series(np.nan, index=df.index)

    partes = {"tendencia": tendencia, "momentum": momentum, "sentimiento": sentimiento, "riesgo": riesgo}
    pesos = c["pesos"]
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for nombre, serie in partes.items():
        df[f"p_{nombre}"] = serie.where(apto).round(0)
        w = float(pesos.get(nombre, 0))
        ok = serie.notna() & apto
        num += serie.fillna(0) * w * ok
        den += w * ok
    df["puntaje"] = (num / den.replace(0, np.nan)).where(apto).round(0)

    notas = []
    for i in df.index:
        if not apto[i]:
            notas.append(f"Sin puntaje: solo {int(df.at[i, 'dias_historial'] or 0)} días de historial "
                         f"(mínimo {c['dias_minimos']}).")
            continue
        # Componentes sin datos para esta moneda en particular (lo que falta para todas se explica en el reporte)
        faltan = [n for n in COMPONENTES if pd.isna(df.at[i, f"p_{n}"]) and pesos.get(n, 0)
                  and df[f"p_{n}"].notna().any()]
        notas.append("Sin datos de " + ", ".join(faltan) + "; su peso se repartió entre el resto."
                     if faltan else "")
    df["nota_puntaje"] = notas
    return df


def pesos_efectivos(cfg: dict, con_sentimiento: bool) -> dict[str, float]:
    """Pesos normalizados a 100 que se aplicaron hoy (para mostrarlos en el reporte)."""
    pesos = {k: float(v) for k, v in cfg["puntaje"]["pesos"].items() if v}
    if not con_sentimiento:
        pesos.pop("sentimiento", None)
    total = sum(pesos.values()) or 1
    return {k: round(v / total * 100, 1) for k, v in pesos.items()}
