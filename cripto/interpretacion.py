"""Interpretación por reglas: cada frase sale de un dato calculado y lo cita.

Se separan los HECHOS (datos medidos) de la LECTURA (una interpretación por reglas
fijas, que es opinión y puede estar equivocada).
"""
from __future__ import annotations

import pandas as pd

NOMBRES = {"tendencia": "Tendencia", "momentum": "Momentum", "sentimiento": "Sentimiento", "riesgo": "Riesgo controlado"}

FUERTE = {"tendencia": "la tendencia", "momentum": "el impulso reciente", "riesgo": "el riesgo controlado"}
DEBIL = {"tendencia": "la tendencia de fondo", "momentum": "el impulso reciente", "riesgo": "el riesgo"}


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and pd.isna(x)) and not pd.isna(x)


def ficha(f: pd.Series, ctx: dict | None = None) -> dict:
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
            "lectura": opinion(f, ctx or {}), "insuficiente": insuf}


def _abajo(dist: float) -> float:
    """Cuánto tendría que caer el precio (en %) para tocar una media que está dist% por debajo."""
    return (1 - 1 / (1 + dist / 100)) * 100


def _arriba(dist: float) -> float:
    """Cuánto tendría que subir el precio (en %) para recuperar una media que está por encima."""
    return (1 / (1 + dist / 100) - 1) * 100


def _usd(x: float) -> str:
    if x >= 1000:
        return f"US$ {x:,.0f}"
    if x >= 1:
        return f"US$ {x:,.2f}"
    return f"US$ {x:.4g}"


def _situacion(f: pd.Series) -> str:
    """Primera frase: en qué etapa está el precio, con los números que la sostienen."""
    s = f.get("simbolo", "").upper()
    r30, r7, d200 = f.get("ret_30d"), f.get("ret_7d"), f.get("dist_sma200")
    if not _ok(d200) and _ok(f.get("dias_historial")):
        return (f"{s} tiene solo {int(f['dias_historial'])} días de historial, así que su tendencia "
                f"de largo plazo todavía no se puede medir.")
    if _ok(r30) and _ok(r7) and r30 > 40:
        if r7 > 5:
            return f"{s} sigue en plena subida: {r30:+.0f}% en 30 días y todavía {r7:+.1f}% en la última semana."
        if r7 < -5:
            return (f"{s} subió {r30:.0f}% en 30 días, pero la última semana devolvió {r7:.1f}%: "
                    f"la subida se está enfriando.")
        return (f"{s} subió {r30:.0f}% en 30 días y en la última semana casi no se movió ({r7:+.1f}%): "
                f"está asentando la suba.")
    if _ok(d200) and d200 < 0:
        if _ok(r30) and r30 > 10:
            return (f"{s} rebota ({r30:+.0f}% en 30 días) pero sigue {d200:.0f}% bajo su SMA 200: "
                    f"todavía no es una tendencia alcista.")
        return f"{s} sigue en tendencia bajista ({d200:.0f}% bajo su SMA 200) y entra al top por otros factores."
    if _ok(d200) and f.get("cruce_50_200") is True:
        extra = f" y {r30:+.0f}% en 30 días" if _ok(r30) else ""
        return f"{s} mantiene una tendencia alcista ordenada: {d200:+.0f}% sobre su SMA 200{extra}."
    if _ok(d200):
        return (f"{s} está {d200:+.0f}% sobre su SMA 200, pero la SMA 50 aún no cruzó por encima de la 200: "
                f"la recuperación es reciente.")
    return f"{s} aparece por su combinación de indicadores."


def _balance(f: pd.Series, ctx: dict) -> str:
    """Segunda frase: el componente más fuerte contra el más flojo, traducido a algo concreto."""
    comps = [(f.get(f"p_{k}"), k) for k in ("tendencia", "momentum", "riesgo")]
    comps = [(v, k) for v, k in comps if _ok(v)]
    if len(comps) < 2:
        return ""
    comps.sort(reverse=True)
    (vb, kb), (vw, kw) = comps[0], comps[-1]
    if vb - vw < 10:
        return f"Sus tres componentes están parejos (entre {vw:.0f} y {vb:.0f}/100): no depende de un solo factor."
    if vw >= 65:
        return (f"Es pareja en todo: su punto fuerte es {FUERTE[kb]} ({vb:.0f}/100) y hasta su componente "
                f"más bajo, {DEBIL[kw]} ({vw:.0f}/100), supera a la mayoría del universo.")
    detalle = ""
    vol, med = f.get("volatilidad_30d"), ctx.get("vol_mediana")
    if kw == "riesgo" and _ok(vol):
        mov = vol / 365 ** 0.5
        veces = f", {vol / med:.1f} veces la mediana del universo" if med else ""
        detalle = f": se mueve ±{mov:.1f}% en un día típico{veces}"
    elif kw == "momentum" and _ok(f.get("ret_7d")):
        detalle = f": en la última semana hizo {f['ret_7d']:+.1f}%"
    elif kw == "tendencia" and _ok(f.get("dist_sma50")):
        detalle = f": está {f['dist_sma50']:+.1f}% respecto de su SMA 50"
    return (f"Su punto fuerte es {FUERTE[kb]} ({vb:.0f}/100) y el más flojo, "
            f"{DEBIL[kw]} ({vw:.0f}/100){detalle}.")


def _contexto(f: pd.Series, ctx: dict) -> str:
    """Tercera frase: lo más llamativo entre su tamaño y su comparación con BTC (o nada, si no destaca)."""
    rank, vol24, vsb = f.get("rank"), f.get("volumen_24h"), f.get("vs_btc_30d")
    puesto, total = ctx.get("vs_btc_puesto"), ctx.get("vs_btc_total")
    if _ok(rank) and rank > 150:
        return (f"Es una moneda chica (puesto {int(rank)} por capitalización), así que pocas órdenes "
                f"pueden moverla mucho.")
    if _ok(vol24) and vol24 < 20e6:
        return (f"Tiene poca liquidez (US$ {vol24 / 1e6:.0f} M negociados en 24 h), así que pocas órdenes "
                f"pueden moverla mucho.")
    if _ok(vsb) and vsb > 0 and puesto and total and puesto <= 10:
        cual = "la que más" if puesto == 1 else f"la {int(puesto)}.ª que más"
        return (f"Es {cual} le gana a BTC de las {total} monedas analizadas ({vsb:+.0f} pp en 30 días): "
                f"su movimiento es propio, no solo arrastre del mercado.")
    if _ok(vsb) and vsb < 0:
        return f"Aun así va detrás de BTC ({vsb:+.1f} pp en 30 días), es decir, sube menos que la referencia del mercado."
    if _ok(rank) and rank <= 25:
        return f"Es de las grandes (puesto {int(rank)} por capitalización): hace falta mucho dinero para moverla."
    return ""


def _a_vigilar(f: pd.Series) -> str:
    """Última frase: qué nivel concreto confirmaría o rompería esta lectura."""
    rsi, precio = f.get("rsi14"), f.get("precio")
    sma20, sma50, d20, d50 = f.get("sma20"), f.get("sma50"), f.get("dist_sma20"), f.get("dist_sma50")
    if _ok(rsi) and rsi > 70 and _ok(sma20) and _ok(d20):
        return (f"Con el RSI en {rsi:.0f} está recalentada: yo esperaría a que se calme antes de sacar conclusiones, "
                f"y una primera señal de debilidad sería perder la SMA 20 ({_usd(sma20)}, "
                f"{_abajo(d20):.0f}% por debajo del precio).")
    if _ok(sma50) and _ok(d50) and d50 > 0:
        return (f"El nivel a vigilar es la SMA 50 ({_usd(sma50)}, {_abajo(d50):.0f}% por debajo del precio): "
                f"mientras se mantenga arriba, esta lectura sigue en pie.")
    if _ok(sma50) and _ok(d50):
        return (f"Lo que mejoraría el panorama es recuperar la SMA 50 ({_usd(sma50)}, "
                f"{_arriba(d50):.0f}% arriba del precio).")
    return ""


def opinion(f: pd.Series, ctx: dict) -> str:
    """Opinión por reglas, armada con los datos propios de la moneda (no una frase genérica)."""
    partes = [_situacion(f), _balance(f, ctx), _contexto(f, ctx), _a_vigilar(f)]
    if f.get("anomalias"):
        partes.append(f"Hoy además marca una anomalía: {f['anomalias'][0].lower()}{f['anomalias'][1:]}. "
                      f"Conviene buscar la noticia detrás.")
    return " ".join(p for p in partes if p)


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
