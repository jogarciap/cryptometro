"""Arma el universo: top N por capitalización, con volumen mínimo y sin stables ni envueltos."""
from __future__ import annotations

import logging

import pandas as pd

from .fuentes.coingecko import CoinGecko
from .http import ErrorFuente

log = logging.getLogger(__name__)


def construir(cg: CoinGecko, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Devuelve (universo, resumen_de_exclusiones)."""
    u = cfg["universo"]
    crudo = pd.DataFrame(cg.mercados(u["top_n"]))
    if crudo.empty:
        raise ErrorFuente("CoinGecko devolvió el top vacío")

    ids_excluidos: set[str] = set()
    categorias_fallidas = []
    for cat in u.get("categorias_excluidas", []):
        try:
            ids_excluidos |= cg.ids_de_categoria(cat)
        except ErrorFuente as e:
            categorias_fallidas.append(cat)
            log.warning("No pude leer la categoría %s: %s", cat, e)

    simbolos = {s.lower() for s in u.get("simbolos_excluidos", [])}
    palabras = [p.lower() for p in u.get("palabras_excluidas", [])]
    nombre = crudo["name"].str.lower()

    por_categoria = crudo["id"].isin(ids_excluidos)
    por_simbolo = crudo["symbol"].str.lower().isin(simbolos)
    por_nombre = nombre.apply(lambda n: any(p in n for p in palabras))
    excluida = por_categoria | por_simbolo | por_nombre
    poco_volumen = ~excluida & (crudo["total_volume"].fillna(0) < u["volumen_minimo_usd"])

    df = crudo[~excluida & ~poco_volumen].copy()
    df = df.rename(columns={
        "id": "coin_id", "symbol": "simbolo", "name": "nombre", "market_cap_rank": "rank",
        "current_price": "precio", "market_cap": "mcap", "total_volume": "volumen_24h",
        "price_change_percentage_24h_in_currency": "cambio_24h",
        "price_change_percentage_7d_in_currency": "cambio_7d",
        "price_change_percentage_30d_in_currency": "cambio_30d",
    })
    df["simbolo"] = df["simbolo"].str.upper()
    cols = ["coin_id", "simbolo", "nombre", "rank", "precio", "mcap", "volumen_24h",
            "cambio_24h", "cambio_7d", "cambio_30d", "image"]
    df = df[[c for c in cols if c in df.columns]].reset_index(drop=True)

    resumen = {
        "top_leido": len(crudo),
        "excluidas_stable_envueltas": int(excluida.sum()),
        "excluidas_poco_volumen": int(poco_volumen.sum()),
        "en_universo": len(df),
        "categorias_fallidas": categorias_fallidas,
        "ejemplos_excluidas": crudo.loc[excluida, "symbol"].str.upper().head(15).tolist(),
    }
    return df, resumen
