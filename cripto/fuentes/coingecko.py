"""CoinGecko: universo top N, datos globales y respaldo de velas diarias."""
from __future__ import annotations

import logging
import time

import pandas as pd

from ..http import ClienteHTTP, ErrorFuente

log = logging.getLogger(__name__)
BASE = "https://api.coingecko.com/api/v3"


class CoinGecko:
    def __init__(self, http: ClienteHTTP, pausa: float = 2.5, api_key: str = ""):
        self.http = http
        self.pausa = pausa if not api_key else min(pausa, 1.0)
        self.headers = {"x-cg-demo-api-key": api_key} if api_key else None
        self._ultima = 0.0

    def _get(self, ruta: str, params: dict | None = None):
        espera = self.pausa - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        try:
            return self.http.get_json(f"{BASE}{ruta}", params=params, headers=self.headers)
        finally:
            self._ultima = time.monotonic()

    def ping(self) -> bool:
        return "gecko_says" in self._get("/ping")

    def mercados(self, top_n: int, categoria: str | None = None) -> list[dict]:
        """Monedas ordenadas por capitalización (100 por página)."""
        filas: list[dict] = []
        pagina = 1
        while len(filas) < top_n:
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": min(250, top_n) if categoria else 100,
                "page": pagina,
                "price_change_percentage": "24h,7d,30d",
            }
            if categoria:
                params["category"] = categoria
            lote = self._get("/coins/markets", params)
            if not lote:
                break
            filas.extend(lote)
            if categoria or len(lote) < params["per_page"]:
                break
            pagina += 1
        return filas[:top_n]

    def ids_de_categoria(self, categoria: str) -> set[str]:
        return {m["id"] for m in self.mercados(250, categoria=categoria)}

    def global_(self) -> dict:
        d = self._get("/global")["data"]
        return {
            "mcap_total_usd": d["total_market_cap"]["usd"],
            "volumen_total_usd": d["total_volume"]["usd"],
            "dominancia_btc": d["market_cap_percentage"].get("btc"),
            "dominancia_eth": d["market_cap_percentage"].get("eth"),
            "cambio_mcap_24h": d.get("market_cap_change_percentage_24h_usd"),
        }

    def velas_diarias(self, coin_id: str, dias: int) -> pd.DataFrame:
        """Cierre y volumen diario (CoinGecko gratis no da OHLC diario de 365 días)."""
        d = self._get(f"/coins/{coin_id}/market_chart",
                      {"vs_currency": "usd", "days": dias, "interval": "daily"})
        if not d.get("prices"):
            raise ErrorFuente(f"CoinGecko sin precios para {coin_id}")
        precios = pd.DataFrame(d["prices"], columns=["ts", "close"])
        vol = pd.DataFrame(d["total_volumes"], columns=["ts", "volumen_usd"])
        df = precios.merge(vol, on="ts", how="left")
        df["fecha"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        # El último punto es el precio "ahora"; se queda con un valor por día.
        df = df.drop_duplicates("fecha", keep="last")
        df["open"] = df["high"] = df["low"] = float("nan")
        return df[["fecha", "open", "high", "low", "close", "volumen_usd"]]
