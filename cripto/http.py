"""Cliente HTTP con reintentos y espera ante límites de llamadas (429)."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)


class ErrorFuente(Exception):
    """Una fuente no respondió o respondió algo inesperado."""


class ClienteHTTP:
    def __init__(self, timeout: int = 20, reintentos: int = 4):
        self.timeout = timeout
        self.reintentos = reintentos
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "investigador-cripto/1.0 (uso personal)"

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        espera = 2.0
        ultimo_error = None
        for intento in range(1, self.reintentos + 1):
            try:
                r = self.sesion.get(url, params=params, headers=headers, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    # CoinGecko a veces manda Retry-After: 0; ante un 429 se espera al menos 15 s y se duplica.
                    minimo = espera * 7.5 if r.status_code == 429 else espera
                    try:
                        pedido = float(r.headers.get("Retry-After", 0))
                    except ValueError:
                        pedido = 0
                    pausa = min(max(pedido, minimo), 90)
                    ultimo_error = f"HTTP {r.status_code}"
                    log.warning("%s en %s, espero %.0fs (intento %d)", ultimo_error, url, pausa, intento)
                    time.sleep(pausa)
                    espera *= 2
                    continue
                if r.status_code >= 400:
                    raise ErrorFuente(f"HTTP {r.status_code} en {url}: {r.text[:200]}")
                return r.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                ultimo_error = type(e).__name__
                log.warning("%s en %s (intento %d)", ultimo_error, url, intento)
                time.sleep(espera)
                espera *= 2
        raise ErrorFuente(f"{url} falló tras {self.reintentos} intentos ({ultimo_error})")
