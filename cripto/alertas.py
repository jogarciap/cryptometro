"""Qué cambió desde el reporte anterior."""
from __future__ import annotations

import pandas as pd


def comparar(hoy: pd.DataFrame, antes: pd.DataFrame, top: int, umbral_puntaje: float = 15) -> dict:
    if antes.empty:
        return {"fecha_anterior": None, "items": [], "nota": "Es el primer reporte: no hay día anterior para comparar."}
    fecha_ant = antes["fecha"].iloc[0]
    items: list[dict] = []
    h = hoy.set_index("coin_id")
    a = antes.set_index("coin_id")

    tiene_puntaje = "puntaje" in a and a["puntaje"].notna().any()
    if tiene_puntaje:
        top_h = set(h["puntaje"].dropna().sort_values(ascending=False).head(top).index)
        top_a = set(a["puntaje"].dropna().sort_values(ascending=False).head(top).index)
        for cid in sorted(top_h - top_a, key=lambda x: -h.at[x, "puntaje"]):
            prev = a["puntaje"].get(cid)
            desde = f" (venía de {prev:.0f})" if pd.notna(prev) else ""
            items.append({"tipo": "entra", "simbolo": h.at[cid, "simbolo"],
                          "texto": f"Entra al top {top} con {h.at[cid, 'puntaje']:.0f} puntos{desde}."})
        for cid in sorted(top_a - top_h):
            ahora = h["puntaje"].get(cid) if cid in h.index else None
            txt = f"Sale del top {top}" + (f"; ahora tiene {ahora:.0f} puntos." if pd.notna(ahora) else "; hoy no está en el universo.")
            items.append({"tipo": "sale", "simbolo": a.at[cid, "simbolo"], "texto": txt})
        comunes = h.index.intersection(a.index)
        delta = (h.loc[comunes, "puntaje"] - a.loc[comunes, "puntaje"]).dropna()
        for cid, d in delta[delta.abs() >= umbral_puntaje].sort_values(key=abs, ascending=False).head(8).items():
            items.append({"tipo": "sube" if d > 0 else "baja", "simbolo": h.at[cid, "simbolo"],
                          "texto": f"Puntaje {d:+.0f} ({a.at[cid, 'puntaje']:.0f} → {h.at[cid, 'puntaje']:.0f})."})

    anom_h = set(h.index[h["anomalias"].fillna("") != ""])
    anom_a = set(a.index[a["anomalias"].fillna("") != ""]) if "anomalias" in a else set()
    for cid in sorted(anom_h - anom_a):
        items.append({"tipo": "anomalia", "simbolo": h.at[cid, "simbolo"], "texto": "Nueva anomalía: " + h.at[cid, "anomalias"] + "."})

    nuevas = sorted(set(h.index) - set(a.index))
    salen = sorted(set(a.index) - set(h.index))
    if nuevas:
        items.append({"tipo": "universo", "simbolo": "", "texto": "Entran al universo: " + ", ".join(h.loc[nuevas, "simbolo"]) + "."})
    if salen:
        items.append({"tipo": "universo", "simbolo": "", "texto": "Salen del universo: " + ", ".join(a.loc[salen, "simbolo"]) + "."})

    nota = "" if tiene_puntaje else "El reporte anterior no tenía puntaje; desde mañana se comparan también los puntajes."
    return {"fecha_anterior": fecha_ant, "items": items, "nota": nota}
