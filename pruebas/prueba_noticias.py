"""Prueba de cripto/noticias.py con respuestas simuladas (no usa internet)."""
import sys, json
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from cripto import noticias
import requests
now = datetime.now(timezone.utc)
rfc = lambda h: (now - timedelta(hours=h)).strftime("%a, %d %b %Y %H:%M:%S GMT")
iso = lambda h: (now - timedelta(hours=h)).isoformat().replace("+00:00", "Z")
class R:
    def __init__(s, content=b"", js=None, code=200): s.content=content; s._js=js; s.status_code=code
    def json(s): return s._js
    def raise_for_status(s):
        if s.status_code>=400:
            e=requests.HTTPError("x"); e.response=s; raise e
def get(self, url, timeout=None, params=None):
    if "news.google.com" in url:
        return R(f"""<rss><channel><item><title>Aave hits record deposits - CoinDesk</title><link>https://news.google.com/rss/articles/abc{len(url)}</link><pubDate>{rfc(3)}</pubDate><source url="https://coindesk.com">CoinDesk</source></item>
        <item><title>Old story - X</title><link>https://news.google.com/rss/articles/old</link><pubDate>{rfc(100)}</pubDate><source>X</source></item></channel></rss>""".encode())
    if "cointelegraph" in url:
        return R(f"""<rss><channel><item><title>Litecoin and SUI rally as altcoins wake up</title><link>https://cointelegraph.com/news/x</link><description>&lt;p&gt;LTC up&lt;/p&gt;</description><pubDate>{rfc(1)}</pubDate></item>
        <item><title>Just a regular day in quant trading</title><link>https://cointelegraph.com/news/y</link><description>nothing</description><pubDate>{rfc(1)}</pubDate></item></channel></rss>""".encode())
    if "decrypt" in url: return R(code=503)
    if "theblock" in url: return R(b"<rss><channel></channel></rss>")
    if "stocktwits" in url:
        sym = url.split("/")[-1].split(".")[0]
        return R(js={"messages":[{"id":1,"body":f"${sym}.X looking strong into the weekly close, volume picking up","created_at":iso(0.5),"user":{"username":"trader1"},"entities":{"sentiment":{"basic":"Bullish"}}},
                                 {"id":2,"body":"moon","created_at":iso(0.6),"user":{"username":"x"},"entities":{}},
                                 {"id":3,"body":f"${sym}.X lost support, careful here, could see more downside","created_at":iso(2),"user":{"username":"bear"},"entities":{"sentiment":{"basic":"Bearish"}}}]})
    if "bsky" in url:
        q = params["q"]
        return R(js={"posts":[{"uri":"at://did:x/app.bsky.feed.post/3abc","author":{"handle":"ana.bsky.social"},"indexedAt":iso(1),"record":{"text":f"Thinking about {q} today, the chart looks interesting honestly"}}]})
    if "reddit" in url:
        return R(f"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Why is Aave pumping?</title><link href="https://www.reddit.com/r/CryptoCurrency/comments/1/x/"/><updated>{iso(4)}</updated><category term="CryptoCurrency" label="r/CryptoCurrency"/></entry></feed>""".encode())
    raise AssertionError(url)
requests.Session.get = get
monedas = [{"simbolo":"QNT","nombre":"Quant"},{"simbolo":"AAVE","nombre":"Aave"},{"simbolo":"LTC","nombre":"Litecoin"},{"simbolo":"SUI","nombre":"Sui"},{"simbolo":"JST","nombre":"JUST"}]
r = noticias.Recolector(monedas, pausa=0).recolectar()
print("fallas", r["fallas"]); print("posturas", r["posturas_stocktwits"])
for i in r["items"]: print(i["tipo"], i["moneda"], i["red"], i["fecha"][:16], "|", i["titulo"][:70], "|", i["url"][:50])

# Comprobaciones
assert r["fallas"] == ["Decrypt: HTTPError 503"], r["fallas"]
assert all(i["url"].startswith("https://") for i in r["items"])
assert not any("Old story" in i["titulo"] for i in r["items"]), "las noticias de más de 72 h se descartan"
assert not any(i["titulo"] == "moon" for i in r["items"]), "los mensajes muy cortos se descartan"
assert {"LTC", "SUI"} <= {i["moneda"] for i in r["items"] if i["red"] == "Cointelegraph"}
assert not any("quant trading" in i["titulo"] for i in r["items"]), "Quant/Just no deben coincidir como palabras sueltas"
assert r["posturas_stocktwits"]["AAVE"] == {"Bullish": 1, "Bearish": 1}
print("OK    prueba de noticias sin internet")
