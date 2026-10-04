"""Investigador cripto: punto de entrada.

Uso (desde la carpeta del proyecto, con el entorno activado):
    python run.py              recolecta, analiza y abre el reporte del día
    python run.py --no-abrir   igual, sin abrir el navegador (para la tarea programada)
    python run.py --verificar  sólo prueba que cada fuente responda
"""
from __future__ import annotations

import argparse
import logging
import sys
import shutil
import traceback
import webbrowser
from datetime import datetime, timedelta, timezone

if sys.version_info < (3, 11):
    sys.exit("Se necesita Python 3.11 o superior. Versión actual: " + sys.version.split()[0])

# La consola de Windows a veces no usa UTF-8 y rompe los acentos
for flujo in (sys.stdout, sys.stderr):
    try:
        flujo.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

from cripto import alertas, indicadores, puntaje, reporte
from cripto.almacen import Almacen, exportar_csv
from cripto.config import DATOS, LOGS, REPORTES, cargar_config
from cripto.fuentes import feargreed
from cripto.fuentes.binance import Binance
from cripto.fuentes.coingecko import CoinGecko
from cripto.http import ClienteHTTP, ErrorFuente
from cripto.recoleccion import actualizar_velas, hoy_utc
from cripto.universo import construir

log = logging.getLogger("investigador")


def configurar_logs() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(fmt)
    archivo = logging.FileHandler(LOGS / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
    archivo.setFormatter(fmt)
    raiz.addHandler(consola)
    raiz.addHandler(archivo)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def verificar(cfg: dict) -> int:
    http = ClienteHTTP(timeout=cfg["red"]["timeout_seg"], reintentos=1)
    pruebas = {
        "Binance (velas)": lambda: Binance(http).ping(),
        "CoinGecko (mercado)": lambda: CoinGecko(http, 0, cfg["keys"]["coingecko"]).ping(),
        "alternative.me (Fear & Greed)": lambda: bool(feargreed.historial(http, 1)),
    }
    fallas = 0
    for nombre, prueba in pruebas.items():
        try:
            prueba()
            print(f"  OK     {nombre}")
        except Exception as e:  # noqa: BLE001
            fallas += 1
            print(f"  FALLA  {nombre}: {e}")
    claves = [k for k, v in cfg["keys"].items() if v]
    print(f"  Keys opcionales cargadas desde .env: {', '.join(claves) if claves else 'ninguna (no hacen falta)'}")
    print("Todo listo." if not fallas else f"{fallas} fuente(s) con problemas; el reporte saldrá sin esos datos.")
    return 1 if fallas == len(pruebas) else 0


def publicar_sitio(ruta) -> None:
    """Deja reportes/index.html (último reporte) y reportes/historial.html (todos) para GitHub Pages."""
    shutil.copyfile(ruta, REPORTES / "index.html")
    items = "\n".join(f'<li><a href="{p.name}">{p.stem.removeprefix("reporte_")}</a></li>'
                      for p in sorted(REPORTES.glob("reporte_*.html"), reverse=True))
    (REPORTES / "historial.html").write_text(
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Cryptometro · historial</title>' + reporte.ICONO_HEAD + '<style>body{font:16px/1.6 system-ui,sans-serif;'
        'max-width:640px;margin:0 auto;padding:24px 16px;background:#fcfcfb;color:#0b0b0b}'
        '@media (prefers-color-scheme:dark){body{background:#1a1a19;color:#fff}a{color:#3987e5}}</style>'
        f'</head><body><h1>Cryptometro: reportes anteriores</h1><p><a href="index.html">Último reporte</a></p><ul>{items}</ul>'
        '</body></html>', encoding="utf-8")


def ejecutar(cfg: dict, abrir: bool, sitio: bool = False) -> int:
    inicio = datetime.now()
    fecha = hoy_utc()
    avisos: list[str] = []
    http = ClienteHTTP(timeout=cfg["red"]["timeout_seg"], reintentos=cfg["red"]["reintentos"])
    cg = CoinGecko(http, cfg["red"]["pausa_coingecko_seg"], cfg["keys"]["coingecko"])
    binance = Binance(http)
    almacen = Almacen(DATOS / "cripto.db")

    try:
        log.info("1/5 Armando el universo (CoinGecko)…")
        universo, res_univ = construir(cg, cfg)
        log.info("Universo: %d monedas (%d excluidas por stable/envueltas, %d por volumen)",
                 res_univ["en_universo"], res_univ["excluidas_stable_envueltas"],
                 res_univ["excluidas_poco_volumen"])
        if res_univ["categorias_fallidas"]:
            avisos.append("No se pudieron leer estas categorías de exclusión de CoinGecko: "
                          + ", ".join(res_univ["categorias_fallidas"])
                          + ". Se usó solo la lista manual de config.yaml; revisa que no se cuele una stablecoin.")

        log.info("2/5 Datos de mercado y Fear & Greed…")
        try:
            mercado = cg.global_()
        except ErrorFuente as e:
            mercado = {}
            avisos.append(f"CoinGecko /global no respondió ({e}); capitalización y dominancia sin datos hoy.")
        try:
            fg_hist = feargreed.historial(http, 30)
            almacen.guardar_fear_greed(fg_hist)
        except ErrorFuente as e:
            avisos.append(f"alternative.me no respondió ({e}); Fear & Greed sin datos hoy.")
        desde30 = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%d")
        fg = almacen.fear_greed(desde30)
        if not fg.empty:
            mercado["fear_greed"] = int(fg.iloc[-1]["valor"])
            mercado["fear_greed_texto"] = fg.iloc[-1]["texto"]
        mercado["fecha"] = fecha
        almacen.guardar_mercado(mercado)

        log.info("3/5 Velas diarias (Binance, respaldo CoinGecko). La primera vez tarda varios minutos…")
        universo = actualizar_velas(universo, almacen, binance, cg, cfg)
        sin_datos = universo.loc[universo["fuente_velas"] == "sin datos", "simbolo"].tolist()
        if sin_datos:
            avisos.append(f"{len(sin_datos)} monedas sin velas hoy (se completan en próximas corridas): "
                          + ", ".join(sin_datos[:20]) + ("…" if len(sin_datos) > 20 else ""))

        log.info("4/5 Indicadores, puntaje y anomalías…")
        desde = (datetime.now(timezone.utc) - timedelta(days=cfg["velas"]["dias"] + 5)).strftime("%Y-%m-%d")
        velas_btc = almacen.velas("bitcoin", desde)
        velas_btc = velas_btc[velas_btc["fecha"] < fecha]
        btc = velas_btc.set_index("fecha")["close"] if len(velas_btc) else None
        serie_btc = indicadores.series_para_grafico(velas_btc) if len(velas_btc) else None
        metricas = []
        for _, f in universo.iterrows():
            velas = almacen.velas(f["coin_id"], desde)
            velas = velas[velas["fecha"] < fecha]
            metricas.append(indicadores.calcular(velas, cfg, btc) if len(velas) else {"dias_historial": 0})
        monedas = pd.concat([universo.reset_index(drop=True), pd.DataFrame(metricas)], axis=1)
        for col in ("anomalias", "dist_sma200", "dist_sma50", "macd_hist_pct", "rsi14", "ret_7d", "ret_30d",
                    "vol_relativo", "volatilidad_30d", "caida_max_90d", "cruce_50_200", "vs_btc_30d"):
            if col not in monedas:
                monedas[col] = "" if col == "anomalias" else None
        monedas = puntaje.calcular(monedas, cfg)
        cambios = alertas.comparar(monedas, almacen.monedas_anteriores(fecha), cfg["puntaje"]["top"])
        almacen.guardar_monedas(fecha, monedas)
        csv = exportar_csv(monedas.drop(columns=["image", "spark"], errors="ignore"), DATOS / "csv", fecha)
        log.info("Datos guardados en %s y %s", DATOS / "cripto.db", csv)

        log.info("5/5 Generando reporte…")
        ruta = reporte.generar(REPORTES, fecha, mercado, almacen.mercado_anterior(fecha), fg,
                               monedas, serie_btc, res_univ, avisos, cfg, cambios)
        log.info("Reporte listo: %s", ruta)
        reporte.guardar_top(monedas, cfg, DATOS / "top.json", fecha)
        if sitio:
            publicar_sitio(ruta)
        almacen.registrar_corrida(inicio.isoformat(), datetime.now().isoformat(), fecha, "ok", "; ".join(avisos))
        if abrir and cfg["reporte"]["abrir_navegador"]:
            webbrowser.open(ruta.resolve().as_uri())
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("La corrida falló: %s\n%s", e, traceback.format_exc())
        almacen.registrar_corrida(inicio.isoformat(), datetime.now().isoformat(), fecha, "error", str(e))
        return 1
    finally:
        almacen.cerrar()


def main() -> int:
    p = argparse.ArgumentParser(description="Investigador cripto: reporte diario de mercado.")
    p.add_argument("--no-abrir", action="store_true", help="no abrir el reporte en el navegador")
    p.add_argument("--verificar", action="store_true", help="probar las fuentes y salir")
    p.add_argument("--sitio", action="store_true", help="dejar index.html e historial.html para publicar")
    args = p.parse_args()
    cfg = cargar_config()
    if args.verificar:
        return verificar(cfg)
    configurar_logs()
    return ejecutar(cfg, abrir=not args.no_abrir, sitio=args.sitio)


if __name__ == "__main__":
    sys.exit(main())
