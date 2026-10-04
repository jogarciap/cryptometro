"""Indicadores técnicos calculados con pandas (sin dependencias extra)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def calcular(velas: pd.DataFrame, cfg: dict) -> dict:
    """Recibe velas diarias cerradas (orden ascendente) y devuelve métricas del último día."""
    v = velas.sort_values("fecha").reset_index(drop=True)
    c = v["close"].astype(float)
    vol = v["volumen_usd"].astype(float)
    n = len(v)
    r: dict = {"dias_historial": n, "fecha_ultima_vela": v["fecha"].iloc[-1] if n else None}
    if n < 2:
        return r

    ult = c.iloc[-1]
    for p in (20, 50, 200):
        if n >= p:
            sma = c.rolling(p).mean().iloc[-1]
            r[f"sma{p}"] = sma
            r[f"dist_sma{p}"] = (ult / sma - 1) * 100
        else:
            r[f"sma{p}"] = r[f"dist_sma{p}"] = np.nan

    # Volumen del último día cerrado vs el promedio de los 30 anteriores
    if n >= 31:
        prom30 = vol.iloc[-31:-1].mean()
        r["vol_prom30"] = prom30
        r["vol_relativo"] = vol.iloc[-1] / prom30 if prom30 > 0 else np.nan
    else:
        r["vol_prom30"] = r["vol_relativo"] = np.nan

    ret = c.pct_change()
    r["ret_dia"] = ret.iloc[-1] * 100
    # Movimiento del día medido en desviaciones estándar de los 90 días previos
    if n >= 31:
        sd = ret.iloc[-91:-1].std()
        r["ret_z"] = ret.iloc[-1] / sd if sd and sd > 0 else np.nan
        r["volatilidad_30d"] = ret.iloc[-30:].std() * np.sqrt(365) * 100
    else:
        r["ret_z"] = r["volatilidad_30d"] = np.nan

    ventana = c.iloc[-90:]
    r["caida_max_90d"] = ((ventana / ventana.cummax()) - 1).min() * 100

    a = cfg["anomalias"]
    alertas = []
    if r["vol_relativo"] == r["vol_relativo"] and r["vol_relativo"] >= a["volumen_vs_promedio_30d"]:
        alertas.append(f"Volumen {r['vol_relativo']:.1f}x su promedio de 30 días")
    if r["ret_z"] == r["ret_z"] and abs(r["ret_z"]) >= a["desviaciones_precio"]:
        signo = "Subida" if r["ret_z"] > 0 else "Caída"
        alertas.append(f"{signo} diaria de {r['ret_dia']:+.1f}% ({abs(r['ret_z']):.1f} desviaciones)")
    r["anomalias"] = "; ".join(alertas)
    return r


def series_para_grafico(velas: pd.DataFrame) -> pd.DataFrame:
    v = velas.sort_values("fecha").reset_index(drop=True).copy()
    for p in (20, 50, 200):
        v[f"sma{p}"] = v["close"].rolling(p).mean()
    return v
