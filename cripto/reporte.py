"""Arma el reporte HTML diario a partir de los datos ya calculados."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.offline import get_plotlyjs

from . import graficos, interpretacion, puntaje
from .config import PLANTILLAS


def _nan(x) -> bool:
    try:
        return x is None or pd.isna(x)
    except (TypeError, ValueError):
        return False


def _usd(x) -> str:
    if _nan(x):
        return "s/d"
    for lim, suf in ((1e12, " billones"), (1e9, " mil M"), (1e6, " M"), (1e3, " mil")):
        if abs(x) >= lim:
            return f"US$ {x / lim:,.2f}{suf}"
    return f"US$ {x:,.2f}"


def _precio(x) -> str:
    if _nan(x):
        return "s/d"
    if x >= 1000:
        return f"{x:,.0f}"
    if x >= 1:
        return f"{x:,.2f}"
    return f"{x:.4g}"


def _pct(x, dec: int = 1) -> str:
    return "s/d" if _nan(x) else f"{x:+.{dec}f}%"


def _num(x):
    """float o None (Jinja no puede comparar NaN ni pd.NA)."""
    try:
        return None if _nan(x) else float(x)
    except (TypeError, ValueError):
        return None


def resumen_mercado(mercado: dict, anterior: dict | None, fg: pd.DataFrame,
                    monedas: pd.DataFrame) -> list[dict]:
    """Cinco líneas, cada una con el dato y su fuente."""
    lineas = []
    lineas.append({
        "texto": f"La capitalización total es {_usd(mercado.get('mcap_total_usd'))}, "
                 f"{_pct(mercado.get('cambio_mcap_24h'))} en 24 horas.",
        "fuente": "CoinGecko /global"})

    dom = mercado.get("dominancia_btc")
    txt = f"Bitcoin representa el {dom:.1f}% del mercado" if not _nan(dom) else "Dominancia de BTC sin datos"
    if anterior and not _nan(anterior.get("dominancia_btc")) and not _nan(dom):
        txt += f" ({dom - anterior['dominancia_btc']:+.2f} pp vs el reporte del {anterior['fecha']})"
    lineas.append({"texto": txt + ".", "fuente": "CoinGecko /global"})

    if not fg.empty:
        hoy = fg.iloc[-1]
        txt = f"El índice Fear & Greed marca {hoy['valor']} ({traducir_fg(hoy['texto'])})"
        if len(fg) >= 8:
            hace7 = fg.iloc[-8]
            txt += f"; hace 7 días marcaba {hace7['valor']}"
        lineas.append({"texto": txt + ".", "fuente": "alternative.me"})
    else:
        lineas.append({"texto": "Fear & Greed sin datos hoy.", "fuente": "alternative.me (no respondió)"})

    n = len(monedas)
    suben = int((monedas["cambio_24h"] > 0).sum())
    con_200 = monedas["dist_sma200"].notna()
    sobre_200 = int((monedas.loc[con_200, "dist_sma200"] > 0).sum())
    lineas.append({
        "texto": f"{suben} de {n} monedas suben en 24 horas y {sobre_200} de {int(con_200.sum())} "
                 f"cotizan sobre su media de 200 días.",
        "fuente": "Cálculo propio con CoinGecko y velas Binance/CoinGecko"})

    anom = monedas[monedas["anomalias"].fillna("") != ""]
    if len(anom):
        destac = ", ".join(anom.sort_values("vol_relativo", ascending=False)["simbolo"].head(5))
        txt = (f"{len(anom)} {'moneda muestra' if len(anom) == 1 else 'monedas muestran'} volumen o "
               f"movimiento fuera de lo normal; destacan {destac}.")
    else:
        txt = "Ninguna moneda muestra volumen o movimiento fuera de lo normal en la última vela."
    lineas.append({"texto": txt, "fuente": "Cálculo propio sobre la última vela diaria cerrada (UTC)"})
    return lineas


FG_ES = {"Extreme Fear": "miedo extremo", "Fear": "miedo", "Neutral": "neutral",
         "Greed": "codicia", "Extreme Greed": "codicia extrema"}


def traducir_fg(t: str) -> str:
    return FG_ES.get(t, t)


def _kpis(mercado: dict, anterior: dict | None, fg: pd.DataFrame, m: pd.DataFrame) -> list[dict]:
    k = []
    cambio = mercado.get("cambio_mcap_24h")
    mc = mercado.get("mcap_total_usd")
    k.append({"titulo": "Capitalización total", "valor": "s/d" if _nan(mc) else f"{mc / 1e12:.2f}",
              "unidad": "billones de US$" if not _nan(mc) else "",
              "detalle": f"{_pct(cambio)} en 24 h", "tono": "" if _nan(cambio) else ("sube" if cambio >= 0 else "baja"),
              "ayuda": "Valor de mercado de todas las criptomonedas. Fuente: CoinGecko."})
    dom = mercado.get("dominancia_btc")
    det = "Peso de BTC en el mercado"
    if anterior and not _nan(anterior.get("dominancia_btc")) and not _nan(dom):
        det = f"{dom - anterior['dominancia_btc']:+.2f} pp vs reporte anterior"
    k.append({"titulo": "Dominancia de BTC", "valor": "s/d" if _nan(dom) else f"{dom:.1f}%", "detalle": det, "tono": "",
              "ayuda": "Si sube, el dinero se refugia en BTC; si baja, suele rotar hacia altcoins. Fuente: CoinGecko."})
    if not fg.empty:
        v = int(fg.iloc[-1]["valor"])
        k.append({"titulo": "Fear & Greed", "valor": str(v), "detalle": traducir_fg(fg.iloc[-1]["texto"]).capitalize(),
                  "tono": "baja" if v <= 25 else ("sube" if v >= 75 else ""), "medidor": v,
                  "ayuda": "Sentimiento del mercado de 0 (miedo extremo) a 100 (codicia extrema). Fuente: alternative.me."})
    con = m["dist_sma200"].notna()
    if con.any():
        amp = (m.loc[con, "dist_sma200"] > 0).mean() * 100
        k.append({"titulo": "Amplitud", "valor": f"{amp:.0f}%", "detalle": "de las monedas sobre su SMA 200",
                  "tono": "sube" if amp >= 60 else ("baja" if amp <= 40 else ""), "medidor": amp,
                  "ayuda": "Qué parte del mercado está en tendencia alcista de largo plazo. Cálculo propio."})
    n_anom = int((m["anomalias"].fillna("") != "").sum())
    k.append({"titulo": "Anomalías", "valor": str(n_anom), "detalle": "volumen o precio fuera de lo normal", "tono": "",
              "ayuda": "Monedas con volumen > 2x su promedio o un movimiento diario extremo. Cálculo propio."})
    return k


def _fila(f: pd.Series) -> dict:
    d = {
        "coin_id": f["coin_id"],
        "rank": int(f["rank"]) if not _nan(f["rank"]) else "",
        "simbolo": f["simbolo"], "nombre": f["nombre"], "imagen": f.get("image") or "",
        "precio": _precio(f["precio"]), "precio_n": f["precio"],
        "c24": _pct(f["cambio_24h"]), "c24_n": f["cambio_24h"],
        "c7": _pct(f["cambio_7d"]), "c7_n": f["cambio_7d"],
        "c30": _pct(f["cambio_30d"]), "c30_n": f["cambio_30d"],
        "mcap": _usd(f.get("mcap")), "mcap_n": f.get("mcap"),
        "vol": _usd(f["volumen_24h"]), "vol_n": f["volumen_24h"],
        "vol_m": "s/d" if _nan(f["volumen_24h"]) else f"{f['volumen_24h'] / 1e6:,.1f}",
        "volrel": "s/d" if _nan(f.get("vol_relativo")) else f"{f['vol_relativo']:.1f}x",
        "volrel_n": f.get("vol_relativo"),
        "s50": _pct(f.get("dist_sma50")), "s50_n": f.get("dist_sma50"),
        "s200": _pct(f.get("dist_sma200")), "s200_n": f.get("dist_sma200"),
        "rsi": "s/d" if _nan(f.get("rsi14")) else f"{f['rsi14']:.0f}", "rsi_n": f.get("rsi14"),
        "vsbtc": "s/d" if _nan(f.get("vs_btc_30d")) else f"{f['vs_btc_30d']:+.1f} pp", "vsbtc_n": f.get("vs_btc_30d"),
        "volat": "s/d" if _nan(f.get("volatilidad_30d")) else f"{f['volatilidad_30d']:.0f}%",
        "volat_n": f.get("volatilidad_30d"),
        "dd": _pct(f.get("caida_max_90d"), 0), "dd_n": f.get("caida_max_90d"),
        "pt": "s/d" if _nan(f.get("puntaje")) else f"{f['puntaje']:.0f}", "pt_n": f.get("puntaje"),
        "pt_t_n": f.get("p_tendencia"), "pt_m_n": f.get("p_momentum"), "pt_r_n": f.get("p_riesgo"),
        "pt_s_n": f.get("p_sentimiento"),
        "anomalias": f.get("anomalias") or "",
        "fuente": f.get("fuente_velas", ""),
        "dias": int(f["dias_historial"]) if not _nan(f.get("dias_historial")) else 0,
        "spark": graficos.sparkline(f.get("spark") if isinstance(f.get("spark"), list) else None),
        "spark_mini": graficos.sparkline(f.get("spark") if isinstance(f.get("spark"), list) else None, 96, 22),
    }
    return {k: (_num(v) if k.endswith("_n") else v) for k, v in d.items()}


def generar(carpeta: Path, fecha: str, mercado: dict, anterior: dict | None, fg: pd.DataFrame,
            monedas: pd.DataFrame, serie_btc: pd.DataFrame | None, resumen_universo: dict,
            avisos: list[str], cfg: dict, cambios: dict | None = None) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    js = carpeta / "plotly.min.js"
    if not js.exists():
        js.write_text(get_plotlyjs(), encoding="utf-8")

    for c in ("cambio_24h", "vol_relativo", "dist_sma200", "anomalias", "puntaje", "vs_btc_30d", "mcap"):
        if c not in monedas.columns:
            monedas[c] = pd.NA
    m = monedas.sort_values("rank")
    n_top = cfg["puntaje"]["top"]
    top = m.dropna(subset=["puntaje"]).sort_values("puntaje", ascending=False).head(n_top)
    anom = m[m["anomalias"].fillna("") != ""].sort_values("vol_relativo", ascending=False)

    # Más y menos volátiles (solo monedas con al menos 30 días de datos)
    con_vol = m.dropna(subset=["volatilidad_30d"])
    vol_max = con_vol["volatilidad_30d"].max() if len(con_vol) else 1
    def _vol(df):
        out = []
        for _, f in df.iterrows():
            fila = _fila(f)
            fila["mov_diario"] = f"±{f['volatilidad_30d'] / 365 ** 0.5:.1f}%"
            fila["barra"] = round(f["volatilidad_30d"] / vol_max * 100, 1)
            out.append(fila)
        return out
    n_vol = cfg["reporte"].get("volatiles", 10)
    mas_volatiles = _vol(con_vol.sort_values("volatilidad_30d", ascending=False).head(n_vol))
    menos_volatiles = _vol(con_vol.sort_values("volatilidad_30d").head(n_vol))
    vol_mediana = con_vol["volatilidad_30d"].median() if len(con_vol) else None

    fichas = []
    puestos_btc = m["vs_btc_30d"].rank(ascending=False, method="min")
    total_btc = int(m["vs_btc_30d"].notna().sum())
    for pos, (i, f) in enumerate(top.iterrows(), start=1):
        fila = _fila(f)
        ctx = {"vol_mediana": vol_mediana, "vs_btc_total": total_btc,
               "vs_btc_puesto": puestos_btc.get(i) if i in puestos_btc.index else None}
        fila.update(interpretacion.ficha(f, ctx))
        fila["pos"] = pos
        fichas.append(fila)

    con_sent = "p_sentimiento" in m and m["p_sentimiento"].notna().any()
    env = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))
    html = env.get_template("reporte.html").render(
        fecha=fecha,
        fecha_larga=_fecha_larga(fecha),
        generado=_ahora(cfg),
        mas_volatiles=mas_volatiles, menos_volatiles=menos_volatiles,
        vol_mediana=vol_mediana, mov_mediano=(vol_mediana / 365 ** 0.5) if vol_mediana else None,
        kpis=_kpis(mercado, anterior, fg, m),
        resumen=resumen_mercado(mercado, anterior, fg, m),
        lectura=interpretacion.lectura_mercado(mercado, m),
        fichas=fichas,
        cambios=cambios or {"items": [], "nota": ""},
        filas=[_fila(f) for _, f in m.iterrows()],
        anomalias=[_fila(f) for _, f in anom.iterrows()],
        filas_visibles=cfg["reporte"]["filas_tabla"],
        grafico_btc=graficos.a_html(graficos.precio_y_volumen(serie_btc, "BTC"))
        if serie_btc is not None and len(serie_btc) else None,
        grafico_fg=graficos.a_html(graficos.fear_greed(fg)) if not fg.empty else None,
        grafico_mapa=graficos.a_html(graficos.mapa(m, set(top["simbolo"]))) if m["dist_sma200"].notna().any() else None,
        grafico_vsbtc=graficos.a_html(graficos.vs_btc(top)) if top["vs_btc_30d"].notna().any() else None,
        pesos=puntaje.pesos_efectivos(cfg, con_sent),
        pesos_config=cfg["puntaje"]["pesos"],
        con_sentimiento=con_sent,
        dias_minimos=cfg["puntaje"]["dias_minimos"],
        rsi_ideal=cfg["puntaje"]["rsi_ideal"],
        n_top=n_top,
        universo=resumen_universo,
        umbral_vol=cfg["anomalias"]["volumen_vs_promedio_30d"],
        umbral_sd=cfg["anomalias"]["desviaciones_precio"],
        avisos=avisos,
    )
    ruta = carpeta / f"reporte_{fecha}.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta


NOMBRES_ZONA = {"America/New_York": "Nueva York", "UTC": "UTC"}


def _ahora(cfg: dict) -> str:
    """Hora de generación en la zona horaria del lector (config.yaml > reporte > zona_horaria)."""
    zona = cfg["reporte"].get("zona_horaria", "UTC")
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo(zona))
        nombre = NOMBRES_ZONA.get(zona, zona.split("/")[-1].replace("_", " "))
        return ahora.strftime("%d/%m %H:%M") + f" {ahora.tzname()} (hora de {nombre})"
    except Exception:  # noqa: BLE001
        return datetime.utcnow().strftime("%d/%m %H:%M") + " UTC"


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fecha_larga(fecha: str) -> str:
    d = datetime.fromisoformat(fecha)
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]} de {d.year}"
