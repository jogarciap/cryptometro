"""Binance: velas diarias por la API pública de datos de mercado (sin key)."""
from __future__ import annotations

import logging

import pandas as pd

from ..http import ClienteHTTP, ErrorFuente

log = logging.getLogger(__name__)
# data-api.binance.vision es el espejo oficial de solo datos de mercado;
# se prueba primero api.binance.com y, si falla, el espejo.
BASES = ["https://api.binance.com", "https://data-api.binance.vision"]


class Binance:
    def __init__(self, http: ClienteHTTP):
        self.http = http
        self.base = None

    def _get(self, ruta: str, params: dict | None = None):
        bases = [self.base] if self.base else BASES
        ultimo = None
        for base in bases:
            try:
                datos = self.http.get_json(f"{base}{ruta}", params=params)
                self.base = base
                return datos
            except ErrorFuente as e:
                ultimo = e
                log.warning("Binance %s no respondió: %s", base, e)
        raise ErrorFuente(f"Binance no disponible: {ultimo}")

    def ping(self) -> bool:
        self._get("/api/v3/ping")
        return True

    def pares_activos(self, cotizacion: str = "USDT") -> dict[str, str]:
        """{simbolo_base_en_minusculas: 'BASEUSDT'} de los pares que operan hoy."""
        info = self._get("/api/v3/exchangeInfo", {"permissions": "SPOT"})
        return {
            s["baseAsset"].lower(): s["symbol"]
            for s in info["symbols"]
            if s["quoteAsset"] == cotizacion and s["status"] == "TRADING"
        }

    def velas_diarias(self, par: str, dias: int) -> pd.DataFrame:
        filas = self._get("/api/v3/klines", {"symbol": par, "interval": "1d", "limit": min(dias, 1000)})
        if not filas:
            raise ErrorFuente(f"Binance sin velas para {par}")
        df = pd.DataFrame(filas).iloc[:, :8]
        df.columns = ["ts", "open", "high", "low", "close", "vol_base", "cierre_ts", "volumen_usd"]
        df["fecha"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        for c in ("open", "high", "low", "close", "volumen_usd"):
            df[c] = df[c].astype(float)
        return df[["fecha", "open", "high", "low", "close", "volumen_usd"]]
