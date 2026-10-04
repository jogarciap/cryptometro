"""Interpretación por reglas: cada frase sale de un dato calculado y lo cita.

Se separan los HECHOS (datos medidos) de la LECTURA (una interpretación por reglas
fijas, que es opinión y puede estar equivocada).
"""
from __future__ import annotations

import pandas as pd

NOMBRES = {"tendencia": "Tendencia", "momentum": "Momentum", "sentimiento": "Sentimiento", "riesgo": "Riesgo controlado"}


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and pd.isna(x)) and not pd.isna(x)


def ficha(f: pd.Series) -> dict:
    """Devuelve {'por_que': [...], 'respalda': [...], 'riesgos': [...], 'lectura': str, 'insuficiente': [...]}"""
    por_que, respalda, riesgos, insuf = [], [], [], []

    # Por qué aparece: los componentes que más aportan
    comps = {k: f.get(f"p_{k}") for k in NOMBRES}
    fuertes = sorted(((v, k) for k, v in comps.items() if _ok(v)), reverse=True)
    for v, k in fuertes[:2]:
        if v >= 60:
            por_que.append(f"{NOMBRES[k]} alto: {v:.0f}/100 frente al resto del universo.")
    if not por_que and fuertes:
        por_que.append(f"Sin un componente dominante; el mejor es {NOMBRES[fuertes[0][1]].lower()} con {fuertes[0][0]:.0f}/100.")

    # Qué la respalda
    if _ok(f.get("dist_sma200")) and f["dist_sma200"] > 0:
        respalda.append(f"Cotiza {f['dist_sma200']:+.1f}% sobre su SMA 200 (tendencia de largo plazo alcista).")
    if f.get("cruce_50_200") is True:
        respalda.append("SMA 50 por encima de SMA 200 (cruce alcista vigente).")
    if _ok(f.get("macd_hist_pct")) and f["macd_hist_pct"] > 0:
        txt = "MACD sobre su señal (impulso positivo)"
        respalda.append(txt + (", con cruce en los últimos 5 días." if f.get("macd_cruce_reciente") else "."))
    if _ok(f.get("vs_btc_30d")) and f["vs_btc_30d"] > 0:
        respalda.append(f"Supera a BTC por {f['vs_btc_30d']:+.1f} pp en 30 días.")
    if _ok(f.get("rsi14")) and 45 <= f["rsi14"] <= 70:
        respalda.append(f"RSI {f['rsi14']:.0f}: fuerza sin sobrecompra.")
    if _ok(f.get("vol_relativo")) and f["vol_relativo"] >= 1.5:
        respalda.append(f"Volumen {f['vol_relativo']:.1f}x su promedio de 30 días.")

    # Qué la pone en riesgo
    if _ok(f.get("rsi14")) and f["rsi14"] > 70:
        riesgos.append(f"RSI {f['rsi14']:.0f}: zona de sobrecompra (más de 70).")
    if _ok(f.get("rsi14")) and f["rsi14"] < 30:
        riesgos.append(f"RSI {f['rsi14']:.0f}: zona de sobreventa (menos de 30).")
    if _ok(f.get("dist_sma20")) and f["dist_sma20"] > 15:
        riesgos.append(f"Precio {f['dist_sma20']:+.1f}% sobre su SMA 20: muy separado de su media corta.")
    if _ok(f.get("dist_sma200")) and f["dist_sma200"] < 0:
        riesgos.append(f"Cotiza {f['dist_sma200']:+.1f}% bajo su SMA 200 (tendencia de largo plazo bajista).")
    if _ok(f.get("volatilidad_30d")) and f["volatilidad_30d"] > 100:
        riesgos.append(f"Volatilidad anualizada {f['volatilidad_30d']:.0f}%: movimientos diarios grandes en ambos sentidos.")
    if _ok(f.get("caida_max_90d")) and f["caida_max_90d"] < -35:
        riesgos.append(f"Caída máxima de {f['caida_max_90d']:.0f}% en 90 días.")
    if _ok(f.get("volumen_24h")) and f["volumen_24h"] < 20e6:
        riesgos.append(f"Liquidez baja: US$ {f['volumen_24h'] / 1e6:.1f} M negociados en 24 h.")
    if _ok(f.get("macd_hist_pct")) and f["macd_hist_pct"] < 0:
        riesgos.append("MACD bajo su señal (impulso negativo).")
    if not riesgos:
        riesgos.append("Ningún indicador de riesgo supera los umbrales; eso no elimina el riesgo de mercado.")

    # Datos insuficientes
    if _ok(f.get("dias_historial")) and f["dias_historial"] < 200:
        insuf.append(f"Solo {int(f['dias_historial'])} días de historial: sin SMA 200.")
    if f.get("fuente_velas") == "coingecko":
        insuf.append("Velas de CoinGecko (solo cierre y volumen agregado de varios exchanges).")
    if f.get("nota_puntaje"):
        insuf.append(f["nota_puntaje"])

    return {"por_que": por_que, "respalda": respalda, "riesgos": riesgos,
            "lectura": lectura(f), "insuficiente": insuf}


def lectura(f: pd.Series) -> str:
    """Una frase de interpretación (opinión basada en reglas)."""
    t, mo, ri = f.get("p_tendencia"), f.get("p_momentum"), f.get("p_riesgo")
    rsi = f.get("rsi14")
    if _ok(rsi) and rsi > 75:
        return "Fuerte pero recalentada: conviene esperar consolidación antes de sacar conclusiones."
    if _ok(t) and _ok(mo) and t >= 70 and mo >= 70:
        return "Tendencia y momentum alineados al alza; vale la pena investigar qué lo impulsa."
    if _ok(t) and _ok(mo) and t >= 70 and mo < 50:
        return "Tendencia sana pero perdiendo impulso; atención a si sostiene las medias."
    if _ok(t) and _ok(mo) and t < 50 and mo >= 70:
        return "Rebote con fuerza dentro de una tendencia débil; puede ser un giro o solo un rebote."
    if _ok(ri) and ri < 35:
        return "Buen puntaje pero con riesgo alto: candidata para seguir, no para conclusiones rápidas."
    return "Perfil equilibrado sin señales extremas."


def lectura_mercado(mercado: dict, monedas: pd.DataFrame) -> str:
    """Lectura general del día (opinión basada en reglas)."""
    fg = mercado.get("fear_greed")
    con = monedas["dist_sma200"].notna()
    amplitud = (monedas.loc[con, "dist_sma200"] > 0).mean() * 100 if con.any() else None
    partes = []
    if amplitud is not None:
        if amplitud >= 65:
            partes.append(f"el mercado está mayormente alcista ({amplitud:.0f}% de las monedas sobre su SMA 200)")
        elif amplitud <= 35:
            partes.append(f"el mercado está mayormente bajista (solo {amplitud:.0f}% sobre su SMA 200)")
        else:
            partes.append(f"el mercado está dividido ({amplitud:.0f}% sobre su SMA 200)")
    if fg is not None and not pd.isna(fg):
        if fg >= 75:
            partes.append("con codicia extrema, un contexto donde las correcciones suelen ser bruscas")
        elif fg >= 55:
            partes.append("con ánimo optimista")
        elif fg <= 25:
            partes.append("con miedo extremo, un contexto que a veces precede rebotes")
        elif fg <= 45:
            partes.append("con ánimo temeroso")
        else:
            partes.append("con ánimo neutral")
    return ("Lectura del día: " + ", ".join(partes) + ".") if partes else ""
