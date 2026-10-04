"""Carga config.yaml y .env, y define las rutas del proyecto."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
REPORTES = RAIZ / "reportes"
LOGS = RAIZ / "logs"
PLANTILLAS = RAIZ / "plantillas"


def cargar_config() -> dict:
    load_dotenv(RAIZ / ".env")
    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["keys"] = {
        "coingecko": os.getenv("COINGECKO_API_KEY", "").strip(),
        "cryptopanic": os.getenv("CRYPTOPANIC_API_KEY", "").strip(),
        "lunarcrush": os.getenv("LUNARCRUSH_API_KEY", "").strip(),
        "coinmarketcal": os.getenv("COINMARKETCAL_API_KEY", "").strip(),
    }
    for carpeta in (DATOS, REPORTES, LOGS):
        carpeta.mkdir(exist_ok=True)
    return cfg
