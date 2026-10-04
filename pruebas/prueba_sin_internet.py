"""Prueba de punta a punta con datos inventados (no usa internet ni toca tus datos reales).

    python pruebas\\prueba_sin_internet.py

Genera un reporte de ejemplo en una carpeta temporal y muestra su ruta.
"""
from __future__ import annotations

import math
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run  # noqa: E402
from cripto import reporte  # noqa: E402
from cripto.config import cargar_config  # noqa: E402
from cripto.http import ClienteHTTP, ErrorFuente  # noqa: E402

random.seed(7)
MONEDAS = [("bitcoin", "btc", "Bitcoin", 60000), ("ethereum", "eth", "Ethereum", 2500),
           ("tether", "usdt", "Tether", 1), ("solana", "sol", "Solana", 150),
           ("wrapped-bitcoin", "wbtc", "Wrapped Bitcoin", 60000), ("ripple", "xrp", "XRP", 0.6),
           ("dogecoin", "doge", "Dogecoin", 0.12), ("chico", "chico", "Moneda Chica", 0.5),
           ("solo-gecko", "sgk", "Solo Gecko", 3.0)]
HOY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def velas(precio0: float, dias: int, salto: bool):
    filas, p = [], precio0
    for i in range(dias, -1, -1):  # incluye la vela de hoy (abierta) para probar que se descarta
        p *= math.exp(random.gauss(0.0005, 0.03))
        vol = 1e8 * random.uniform(0.7, 1.3)
        if salto and i == 1:
            p *= 1.18
            vol *= 4
        ts = int((HOY - timedelta(days=i)).timestamp() * 1000)
        filas.append([ts, p, p * 1.02, p * 0.98, p, 0, ts, vol])
    k = precio0 / filas[-2][4]  # que el cierre de ayer coincida con el precio de CoinGecko
    return [[f[0], f[1] * k, f[2] * k, f[3] * k, f[4] * k, f[5], f[6], f[7]] for f in filas]


def falso_get_json(self, url, params=None, headers=None):
    params = params or {}
    if "binance" in url:
        if url.endswith("/ping"):
            return {}
        if "exchangeInfo" in url:
            return {"symbols": [{"baseAsset": s.upper(), "quoteAsset": "USDT", "symbol": s.upper() + "USDT",
                                 "status": "TRADING"} for _, s, _, _ in MONEDAS if s != "sgk"]}
        if "klines" in url:
            base = next(m for m in MONEDAS if m[1].upper() + "USDT" == params["symbol"])
            return velas(base[3], params["limit"] - 1, salto=base[1] == "sol")
    if "coingecko" in url:
        if url.endswith("/ping"):
            return {"gecko_says": "ok"}
        if url.endswith("/global"):
            return {"data": {"total_market_cap": {"usd": 2.4e12}, "total_volume": {"usd": 9e10},
                             "market_cap_percentage": {"btc": 56.3, "eth": 12.1},
                             "market_cap_change_percentage_24h_usd": 1.8}}
        if url.endswith("/coins/markets"):
            if params.get("category") == "stablecoins":
                return [{"id": "tether"}]
            if params.get("category"):
                raise ErrorFuente("categoría simulada no disponible")
            if params["page"] > 1:
                return []
            return [{"id": i, "symbol": s, "name": n, "market_cap_rank": k + 1, "current_price": p,
                     "market_cap": 1e10 / (k + 1), "total_volume": 1e6 if i == "chico" else 2e8,
                     "price_change_percentage_24h_in_currency": random.uniform(-5, 5),
                     "price_change_percentage_7d_in_currency": random.uniform(-10, 10),
                     "price_change_percentage_30d_in_currency": random.uniform(-20, 20), "image": ""}
                    for k, (i, s, n, p) in enumerate(MONEDAS)]
        if "/market_chart" in url:
            v = velas(3.0, params["days"], False)
            return {"prices": [[f[0], f[4]] for f in v], "total_volumes": [[f[0], f[7]] for f in v]}
    if "alternative.me" in url:
        return {"data": [{"timestamp": str(int((HOY - timedelta(days=i)).timestamp())),
                          "value": str(40 + i), "value_classification": "Fear" if i < 10 else "Neutral"}
                         for i in range(params["limit"])]}
    raise ErrorFuente(f"URL no simulada: {url}")


def log_txt() -> str:
    return "".join(p.read_text(encoding="utf-8") for p in (run.LOGS).glob("*.log"))


def main() -> int:
    ClienteHTTP.get_json = falso_get_json
    tmp = Path(tempfile.mkdtemp(prefix="cripto_prueba_"))
    for nombre in ("DATOS", "REPORTES", "LOGS"):
        (tmp / nombre.lower()).mkdir()
        setattr(run, nombre, tmp / nombre.lower())
    cfg = cargar_config()
    cfg["red"]["pausa_coingecko_seg"] = 0
    run.configurar_logs()
    codigo = run.ejecutar(cfg, abrir=False)
    # Segunda corrida: debe usar la caché y no fallar
    codigo |= run.ejecutar(cfg, abrir=False)
    html = next((tmp / "reportes").glob("reporte_*.html")).read_text(encoding="utf-8")
    chequeos = {
        "corrida sin errores": codigo == 0,
        "USDT y WBTC excluidas": ">USDT<" not in html and ">WBTC<" not in html,
        "moneda de bajo volumen excluida": ">CHICO<" not in html,
        "SOL marcada como anomalía": ">SOL<" in html.split('id="anomalias"')[1].split('id="tabla-sec"')[0],
        "sin monedas descartadas por precio": "parece otra moneda" not in log_txt(),
        "moneda sin par en Binance usa CoinGecko": "coingecko" in html,
        "gráfico de BTC presente": "SMA 200" in html,
        "aviso de no recomendación": "No es una recomendación" in html,
        "fichas con puntaje e interpretación": html.count('class="tarjeta ficha"') >= 3 and "Qué la pone en riesgo" in html,
        "mapa y comparación vs BTC": "Tendencia contra riesgo" in html and "contra Bitcoin" in html,
    }
    for k, ok in chequeos.items():
        print(f"  {'OK   ' if ok else 'FALLA'} {k}")
    print(f"Reporte de prueba: {(tmp / 'reportes').resolve()}")
    return 0 if all(chequeos.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
