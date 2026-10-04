"""Indicadores técnicos calculados con pandas (sin dependencias extra)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(c: pd.Series, periodo: int = 14) -> pd.Series:
    """RSI de Wilder."""
    delta = c.diff()
    sube = delta.clip(lower=0).ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    baja = (-delta.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    rs = sube / baja.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(c: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD clásico (12, 26, 9): línea, señal e histograma."""
    linea = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    senal = linea.ewm(span=9, adjust=False).mean()
    return linea, senal, linea - senal


def _ret(c: pd.Series, dias: int) -> float:
    return (c.iloc[-1] / c.iloc[-1 - dias] - 1) * 100 if len(c) > dias else np.nan


def calcular(velas: pd.DataFrame, cfg: dict, btc: pd.Series | None = None) -> dict:
    """Recibe velas diarias cerradas (orden ascendente) y devuelve métricas del último día.

    btc: cierres diarios de BTC indexados por fecha, para medir el rendimiento relativo.
    """
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
    r["cruce_50_200"] = (r["sma50"] > r["sma200"]) if n >= 200 else None

    for d in (7, 30, 90):
        r[f"ret_{d}d"] = _ret(c, d)

    r["rsi14"] = rsi(c).iloc[-1] if n >= 15 else np.nan
    if n >= 35:
        linea, senal, hist = macd(c)
        r["macd"], r["macd_senal"] = linea.iloc[-1], senal.iloc[-1]
        # Histograma relativo al precio para poder comparar monedas entre sí
        r["macd_hist_pct"] = hist.iloc[-1] / ult * 100
        r["macd_cruce_reciente"] = bool((np.sign(hist.iloc[-5:]).diff().fillna(0) != 0).any())
    else:
        r["macd"] = r["macd_senal"] = r["macd_hist_pct"] = np.nan
        r["macd_cruce_reciente"] = False

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
    r["max_90d"] = ventana.max()
    r["dist_max_90d"] = (ult / ventana.max() - 1) * 100

    # Rendimiento contra BTC en 30 días (puntos porcentuales)
    r["vs_btc_30d"] = np.nan
    if btc is not None and n > 30:
        serie = pd.Series(c.values, index=v["fecha"])
        comun = serie.index.intersection(btc.index)
        if len(comun) > 30:
            s, b = serie.loc[comun], btc.loc[comun]
            r["vs_btc_30d"] = ((s.iloc[-1] / s.iloc[-31]) - (b.iloc[-1] / b.iloc[-31])) * 100

    # Últimos 90 cierres para el minigráfico
    r["spark"] = [round(float(x), 10) for x in c.iloc[-90:]]

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
    v["rsi14"] = rsi(v["close"])
    return v
