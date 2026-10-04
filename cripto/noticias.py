"""Noticias y comentarios públicos sobre las monedas del top 10.

Fuentes gratuitas y sin clave (X/Twitter no tiene acceso gratuito):
- Noticias: Google News (búsqueda por moneda) y los RSS de Cointelegraph, Decrypt y The Block.
- Redes: StockTwits (comentarios de traders, con su postura alcista/bajista declarada),
  Reddit y Bluesky.

Cada fuente se consulta por separado: si una falla, se anota en "fallas" y el resto sigue.
Todo es texto de terceros: se muestra tal cual, con su fuente y enlace, sin interpretarlo.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; Cryptometro/1.0; +https://github.com/jogarciap/cryptometro)"
MEDIOS = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
}
# Nombres que también son palabras comunes: se buscan junto al símbolo para no traer ruido
AMBIGUOS = {"quant", "just", "sui", "avalanche", "near", "flow", "graph", "maker", "pump", "sonic",
            "story", "ondo", "aptos", "celestia", "algo", "mantra", "theta", "core", "kaia", "stacks"}
# Símbolos que en mayúsculas también son palabras o siglas comunes en inglés
SIMBOLOS_AMBIGUOS = {"BTW", "ONE", "GAS", "PUMP", "JUST", "NEAR", "FLOW", "CORE", "AI", "IT", "ME", "SUN",
                     "GOLD", "MOVE", "TRUMP", "ZRO", "IP", "OM", "S", "W", "G", "T", "CAT", "DOG", "BIO"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _texto(html_crudo: str | None, maximo: int = 280) -> str:
    """Quita etiquetas HTML y recorta."""
    t = re.sub(r"<[^>]+>", " ", html_crudo or "")
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    return t if len(t) <= maximo else t[: maximo - 1].rsplit(" ", 1)[0] + "…"


def _fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        d = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _patron(m: dict) -> re.Pattern:
    """Reconoce la moneda en un texto: su nombre (si no es ambiguo), $SÍMBOLO o SÍMBOLO en mayúsculas."""
    partes = [rf"\${re.escape(m['simbolo'])}\b"]
    nombre = m["nombre"].split("(")[0].strip()
    if nombre.lower() not in AMBIGUOS and len(nombre) >= 4:
        partes.append(rf"\b{re.escape(nombre)}\b")
    if len(m["simbolo"]) >= 3 and m["simbolo"].upper() not in SIMBOLOS_AMBIGUOS:
        partes.append(rf"(?-i:\b{re.escape(m['simbolo'].upper())}\b)")
    return re.compile("|".join(partes), re.I)


class Recolector:
    def __init__(self, monedas: list[dict], pausa: float = 0.6):
        self.monedas = monedas
        self.pausa = pausa
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.items: list[dict] = []
        self.fallas: list[str] = []

    def _get(self, url: str, **kw) -> requests.Response:
        time.sleep(self.pausa)
        r = self.s.get(url, timeout=15, **kw)
        r.raise_for_status()
        return r

    def _agregar(self, **it) -> None:
        if it.get("url", "").startswith("https://") and it.get("fecha"):
            it["fecha"] = it["fecha"].astimezone(timezone.utc).isoformat(timespec="seconds")
            self.items.append(it)

    def _intentar(self, fuente: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001 — una fuente caída no frena a las demás
            msg = f"{fuente}: {type(e).__name__} {getattr(getattr(e, 'response', None), 'status_code', '') or ''}".strip()
            log.warning("Falló %s", msg)
            if msg not in self.fallas:
                self.fallas.append(msg)

    # --- Noticias ---
    def google_news(self, m: dict) -> None:
        nombre = m["nombre"].split("(")[0].strip()
        extra = m["simbolo"].upper() if nombre.lower() in AMBIGUOS else "crypto"
        q = quote_plus(f'"{nombre}" {extra} when:2d')
        r = self._get(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
        for item in ET.fromstring(r.content).iter("item"):
            titulo = item.findtext("title") or ""
            medio = item.findtext("source") or "Google News"
            if titulo.endswith(" - " + medio):
                titulo = titulo[: -len(medio) - 3]
            self._agregar(tipo="noticia", red=medio, via="Google News", moneda=m["simbolo"],
                          titulo=_texto(titulo, 220), url=item.findtext("link") or "",
                          fecha=_fecha(item.findtext("pubDate")))

    def medio(self, nombre_medio: str, url: str) -> None:
        r = self._get(url)
        patrones = {m["simbolo"]: _patron(m) for m in self.monedas}
        for item in ET.fromstring(r.content).iter("item"):
            titulo = _texto(item.findtext("title"), 220)
            resumen = _texto(item.findtext("description"), 400)
            for sim, p in patrones.items():
                if p.search(titulo) or p.search(resumen):
                    self._agregar(tipo="noticia", red=nombre_medio, via=nombre_medio, moneda=sim, titulo=titulo,
                                  url=(item.findtext("link") or "").strip(), fecha=_fecha(item.findtext("pubDate")))

    # --- Redes ---
    def stocktwits(self, m: dict) -> None:
        r = self._get(f"https://api.stocktwits.com/api/2/streams/symbol/{m['simbolo'].upper()}.X.json")
        for msg in r.json().get("messages", [])[:30]:
            cuerpo = _texto(msg.get("body"))
            if len(cuerpo) < 25:  # descarta mensajes de una palabra o solo emojis
                continue
            postura = ((msg.get("entities") or {}).get("sentiment") or {}).get("basic")
            usuario = (msg.get("user") or {}).get("username", "")
            self._agregar(tipo="social", red="StockTwits", via="StockTwits", moneda=m["simbolo"],
                          titulo=cuerpo, autor=usuario, postura=postura,
                          url=f"https://stocktwits.com/{usuario}/message/{msg.get('id')}",
                          fecha=_fecha(msg.get("created_at")))

    def bluesky(self, m: dict) -> None:
        nombre = m["nombre"].split("(")[0].strip()
        q = f"${m['simbolo'].upper()}" if nombre.lower() in AMBIGUOS else nombre
        r = self._get("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                      params={"q": q, "limit": 25, "sort": "latest", "lang": "en"})
        p = _patron(m)
        for post in r.json().get("posts", []):
            texto = _texto((post.get("record") or {}).get("text"))
            if not p.search(texto) or len(texto) < 30:
                continue
            autor = (post.get("author") or {}).get("handle", "")
            rkey = post.get("uri", "").rsplit("/", 1)[-1]
            self._agregar(tipo="social", red="Bluesky", via="Bluesky", moneda=m["simbolo"], titulo=texto,
                          autor=autor, url=f"https://bsky.app/profile/{autor}/post/{rkey}",
                          fecha=_fecha(post.get("indexedAt") or (post.get("record") or {}).get("createdAt")))

    def reddit(self) -> None:
        """Una sola búsqueda en Reddit con todas las monedas (Reddit limita mucho las consultas)."""
        terminos = []
        for m in self.monedas:
            nombre = m["nombre"].split("(")[0].strip()
            terminos.append(f'"{nombre} {m["simbolo"].upper()}"' if nombre.lower() in AMBIGUOS else f'"{nombre}"')
        q = quote_plus(" OR ".join(terminos))
        r = self._get(f"https://www.reddit.com/search.rss?q={q}&sort=new&t=week&limit=100")
        ns = {"a": "http://www.w3.org/2005/Atom"}
        patrones = {m["simbolo"]: _patron(m) for m in self.monedas}
        for e in ET.fromstring(r.content).findall("a:entry", ns):
            titulo = _texto(e.findtext("a:title", namespaces=ns), 220)
            enlace = e.find("a:link", ns)
            sub = e.find("a:category", ns)
            for sim, p in patrones.items():
                if p.search(titulo):
                    self._agregar(tipo="social", red="Reddit", via="Reddit", moneda=sim, titulo=titulo,
                                  autor=f"r/{sub.get('term')}" if sub is not None else "",
                                  url=enlace.get("href") if enlace is not None else "",
                                  fecha=_fecha(e.findtext("a:updated", namespaces=ns)))

    def recolectar(self) -> dict:
        for m in self.monedas:
            self._intentar("Google News", self.google_news, m)
            self._intentar("StockTwits", self.stocktwits, m)
            self._intentar("Bluesky", self.bluesky, m)
        for nombre_medio, url in MEDIOS.items():
            self._intentar(nombre_medio, self.medio, nombre_medio, url)
        self._intentar("Reddit", self.reddit)
        return self.resultado()

    def resultado(self, por_moneda: int = 8, horas_noticias: int = 72, horas_social: int = 48) -> dict:
        ahora = _ahora()
        vistos, salida = set(), []
        for it in sorted(self.items, key=lambda x: x["fecha"], reverse=True):
            limite = ahora - timedelta(hours=horas_noticias if it["tipo"] == "noticia" else horas_social)
            clave = (it["moneda"], re.sub(r"\W+", "", it["titulo"].lower())[:80])
            enlace = (it["moneda"], it["url"])
            if datetime.fromisoformat(it["fecha"]) < limite or clave in vistos or enlace in vistos:
                continue
            vistos.update({clave, enlace})
            salida.append(it)
        final, cuenta = [], {}
        for it in salida:  # tope por moneda y tipo, para que ninguna tape a las demás
            k = (it["moneda"], it["tipo"])
            if cuenta.get(k, 0) < por_moneda:
                cuenta[k] = cuenta.get(k, 0) + 1
                final.append(it)
        posturas = {}
        for it in self.items:  # postura declarada en StockTwits, sobre todos los mensajes leídos
            if it.get("postura") in ("Bullish", "Bearish"):
                p = posturas.setdefault(it["moneda"], {"Bullish": 0, "Bearish": 0})
                p[it["postura"]] += 1
        return {"generado": ahora.isoformat(timespec="seconds"),
                "monedas": [{"simbolo": m["simbolo"], "nombre": m["nombre"]} for m in self.monedas],
                "items": final, "posturas_stocktwits": posturas, "fallas": self.fallas}


def recolectar(monedas: list[dict]) -> dict:
    return Recolector(monedas).recolectar()


def guardar(datos: dict, ruta) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
