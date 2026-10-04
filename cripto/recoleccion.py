"""Descarga de velas: Binance primero, CoinGecko como respaldo, con caché en SQLite."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from .almacen import Almacen
from .fuentes.binance import Binance
from .fuentes.coingecko import CoinGecko
from .http import ErrorFuente

log = logging.getLogger(__name__)


def hoy_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _solo_cerradas(df: pd.DataFrame) -> pd.DataFrame:
    """Quita la vela del día en curso (UTC): todavía no cerró y distorsiona el volumen."""
    return df[df["fecha"] < hoy_utc()]


def actualizar_velas(universo: pd.DataFrame, almacen: Almacen, binance: Binance | None,
                     cg: CoinGecko, cfg: dict) -> pd.DataFrame:
    """Actualiza velas de cada moneda y devuelve el universo con la columna fuente_velas."""
    v = cfg["velas"]
    dias = v["dias"]
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    pares: dict[str, str] = {}
    if binance:
        try:
            pares = binance.pares_activos(v["par_cotizacion"])
            log.info("Binance: %d pares %s activos", len(pares), v["par_cotizacion"])
        except ErrorFuente as e:
            log.warning("No pude leer los pares de Binance, uso solo CoinGecko: %s", e)
            binance = None

    fuentes = []
    respaldos = 0
    total = len(universo)
    for i, fila in universo.iterrows():
        cid, sim = fila["coin_id"], fila["simbolo"].lower()
        ultima = almacen.ultima_fecha_vela(cid)
        if ultima and ultima >= ayer:
            fuentes.append(almacen.velas(cid).iloc[-1]["fuente"])
            continue
        # Con caché sólo se piden los días que faltan (+2 por las dudas)
        faltan = dias if not ultima else min(dias, (datetime.now(timezone.utc).date()
                                                     - datetime.fromisoformat(ultima).date()).days + 2)
        fuente = None
        par = pares.get(sim)
        if binance and par:
            try:
                df = _solo_cerradas(binance.velas_diarias(par, faltan + 1))
                precio_bn = df["close"].iloc[-1] if not df.empty else None
                if precio_bn and fila["precio"] and abs(precio_bn / fila["precio"] - 1) > v["tolerancia_precio"]:
                    log.warning("%s: %s en Binance cotiza %.6g vs %.6g en CoinGecko; parece otra moneda",
                                sim.upper(), par, precio_bn, fila["precio"])
                else:
                    almacen.guardar_velas(cid, df, "binance")
                    fuente = "binance"
            except ErrorFuente as e:
                log.warning("%s: Binance falló (%s)", par, e)
        if fuente is None and respaldos < v["max_respaldo_coingecko"]:
            try:
                df = _solo_cerradas(cg.velas_diarias(cid, max(faltan, 2)))
                almacen.guardar_velas(cid, df, "coingecko")
                fuente = "coingecko"
                respaldos += 1
            except ErrorFuente as e:
                log.warning("%s: CoinGecko falló (%s)", cid, e)
        if fuente is None and ultima:
            fuente = "caché"
        fuentes.append(fuente or "sin datos")
        if (i + 1) % 25 == 0:
            log.info("Velas: %d/%d monedas", i + 1, total)

    out = universo.copy()
    out["fuente_velas"] = fuentes
    return out
