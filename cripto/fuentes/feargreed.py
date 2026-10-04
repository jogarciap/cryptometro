"""Índice Fear & Greed de alternative.me (0 = miedo extremo, 100 = codicia extrema)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..http import ClienteHTTP

URL = "https://api.alternative.me/fng/"


def historial(http: ClienteHTTP, dias: int = 30) -> list[dict]:
    d = http.get_json(URL, {"limit": dias})
    return [
        {
            "fecha": datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d"),
            "valor": int(x["value"]),
            "texto": x["value_classification"],
        }
        for x in d["data"]
    ]
