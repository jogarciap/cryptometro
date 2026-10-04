"""Junta noticias y comentarios sobre el top 10 del último reporte.

Uso:
    python noticias.py                         deja datos/noticias.json
    python noticias.py --salida otra/ruta.json

Lee el top 10 de datos/top.json (lo escribe run.py en cada reporte). Solo necesita
requests: en GitHub Actions corre cada 10 minutos en un flujo aparte y liviano.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from cripto import noticias

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--salida", default=str(RAIZ / "datos" / "noticias.json"))
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    top = RAIZ / "datos" / "top.json"
    if not top.exists():
        logging.error("Falta %s: ejecuta primero run.py", top)
        return 1
    monedas = json.loads(top.read_text(encoding="utf-8"))["monedas"]
    datos = noticias.recolectar(monedas)
    noticias.guardar(datos, Path(a.salida))
    tipos = {t: sum(1 for i in datos["items"] if i["tipo"] == t) for t in ("noticia", "social")}
    logging.info("%d noticias y %d comentarios de %d monedas; fallas: %s",
                 tipos["noticia"], tipos["social"], len(monedas), datos["fallas"] or "ninguna")
    return 0 if datos["items"] else 1


if __name__ == "__main__":
    sys.exit(main())
