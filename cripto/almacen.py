"""Histórico en SQLite (datos/cripto.db) y exportación a CSV."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ESQUEMA = """
CREATE TABLE IF NOT EXISTS velas (
    coin_id TEXT, fecha TEXT, open REAL, high REAL, low REAL, close REAL,
    volumen_usd REAL, fuente TEXT, PRIMARY KEY (coin_id, fecha));
CREATE TABLE IF NOT EXISTS mercado (
    fecha TEXT PRIMARY KEY, mcap_total_usd REAL, volumen_total_usd REAL,
    dominancia_btc REAL, dominancia_eth REAL, cambio_mcap_24h REAL,
    fear_greed INTEGER, fear_greed_texto TEXT);
CREATE TABLE IF NOT EXISTS fear_greed (fecha TEXT PRIMARY KEY, valor INTEGER, texto TEXT);
CREATE TABLE IF NOT EXISTS monedas_diario (
    fecha TEXT, coin_id TEXT, simbolo TEXT, nombre TEXT, rank INTEGER, precio REAL,
    mcap REAL, volumen_24h REAL, cambio_24h REAL, cambio_7d REAL, cambio_30d REAL,
    fuente_velas TEXT, dias_historial INTEGER, fecha_ultima_vela TEXT,
    dist_sma20 REAL, dist_sma50 REAL, dist_sma200 REAL, vol_relativo REAL,
    ret_dia REAL, ret_z REAL, volatilidad_30d REAL, caida_max_90d REAL, anomalias TEXT,
    PRIMARY KEY (fecha, coin_id));
CREATE TABLE IF NOT EXISTS corridas (
    inicio TEXT PRIMARY KEY, fin TEXT, fecha TEXT, estado TEXT, notas TEXT);
"""


# Columnas agregadas después de la etapa 1: se suman a bases ya existentes.
COLUMNAS_NUEVAS = {
    "monedas_diario": ["rsi14 REAL", "macd_hist_pct REAL", "ret_7d REAL", "ret_30d REAL", "ret_90d REAL",
                       "vs_btc_30d REAL", "dist_max_90d REAL", "p_tendencia REAL", "p_momentum REAL",
                       "p_sentimiento REAL", "p_riesgo REAL", "puntaje REAL"],
}


class Almacen:
    def __init__(self, ruta: Path):
        self.con = sqlite3.connect(ruta)
        self.con.executescript(ESQUEMA)
        for tabla, columnas in COLUMNAS_NUEVAS.items():
            existentes = {r[1] for r in self.con.execute(f"PRAGMA table_info({tabla})")}
            for col in columnas:
                if col.split()[0] not in existentes:
                    self.con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col}")
        self.con.commit()

    def cerrar(self):
        self.con.commit()
        self.con.close()

    def _upsert(self, tabla: str, df: pd.DataFrame):
        if df.empty:
            return
        cols = list(df.columns)
        sql = f"INSERT OR REPLACE INTO {tabla} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        filas = [tuple(None if pd.isna(x) else x for x in fila) for fila in df.itertuples(index=False)]
        self.con.executemany(sql, filas)
        self.con.commit()

    # --- velas (también funciona como caché para no descargar todo cada día)
    def ultima_fecha_vela(self, coin_id: str) -> str | None:
        fila = self.con.execute("SELECT MAX(fecha) FROM velas WHERE coin_id=?", (coin_id,)).fetchone()
        return fila[0] if fila else None

    def guardar_velas(self, coin_id: str, df: pd.DataFrame, fuente: str):
        df = df.copy()
        df["coin_id"] = coin_id
        df["fuente"] = fuente
        self._upsert("velas", df[["coin_id", "fecha", "open", "high", "low", "close", "volumen_usd", "fuente"]])

    def velas(self, coin_id: str, desde: str | None = None) -> pd.DataFrame:
        q = "SELECT fecha, open, high, low, close, volumen_usd, fuente FROM velas WHERE coin_id=?"
        params: list = [coin_id]
        if desde:
            q += " AND fecha >= ?"
            params.append(desde)
        return pd.read_sql_query(q + " ORDER BY fecha", self.con, params=params)

    # --- snapshots diarios
    def guardar_mercado(self, fila: dict):
        self._upsert("mercado", pd.DataFrame([fila]))

    def guardar_fear_greed(self, filas: list[dict]):
        self._upsert("fear_greed", pd.DataFrame(filas, columns=["fecha", "valor", "texto"]))

    def fear_greed(self, desde: str) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM fear_greed WHERE fecha>=? ORDER BY fecha",
                                 self.con, params=[desde])

    def guardar_monedas(self, fecha: str, df: pd.DataFrame):
        cols = [r[1] for r in self.con.execute("PRAGMA table_info(monedas_diario)")]
        d = df.copy()
        d["fecha"] = fecha
        self._upsert("monedas_diario", d[[c for c in cols if c in d.columns]])

    def mercado_anterior(self, fecha: str) -> dict | None:
        fila = pd.read_sql_query("SELECT * FROM mercado WHERE fecha<? ORDER BY fecha DESC LIMIT 1",
                                 self.con, params=[fecha])
        return None if fila.empty else fila.iloc[0].to_dict()

    def monedas_anteriores(self, fecha: str) -> pd.DataFrame:
        """Snapshot del último día anterior a `fecha` (para comparar y armar alertas)."""
        fila = self.con.execute("SELECT MAX(fecha) FROM monedas_diario WHERE fecha<?", (fecha,)).fetchone()
        if not fila or not fila[0]:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM monedas_diario WHERE fecha=?", self.con, params=[fila[0]])

    def registrar_corrida(self, inicio: str, fin: str, fecha: str, estado: str, notas: str):
        self.con.execute("INSERT OR REPLACE INTO corridas VALUES (?,?,?,?,?)",
                         (inicio, fin, fecha, estado, notas))
        self.con.commit()


def exportar_csv(df: pd.DataFrame, carpeta: Path, fecha: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"monedas_{fecha}.csv"
    # utf-8-sig para que Excel en Windows muestre bien los acentos
    df.to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta
