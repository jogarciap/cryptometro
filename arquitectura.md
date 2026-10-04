# Investigador cripto: propuesta de arquitectura

Herramienta de investigación, no de trading: no ejecuta órdenes ni usa claves de exchange. Corre en Windows con Python 3.11+, a mano o una vez al día con el Programador de tareas.

## 1. Estructura del proyecto

```
investigador-cripto/
├─ run.py                  # punto de entrada: python run.py
├─ config.yaml             # universo, umbrales, pesos del puntaje (comentados)
├─ .env.example            # keys opcionales (CryptoPanic, LunarCrush, Reddit)
├─ requirements.txt
├─ programar_tarea.ps1     # registra la tarea diaria en Windows
├─ cripto/
│  ├─ fuentes/             # un módulo por fuente, todos con la misma interfaz
│  │  ├─ binance.py        # velas diarias y volumen (REST público)
│  │  ├─ coingecko.py      # top 200, capitalización, dominancia, respaldo de velas
│  │  ├─ feargreed.py      # índice Fear & Greed (alternative.me)
│  │  ├─ noticias.py       # CryptoPanic (si hay key) + RSS
│  │  ├─ social.py         # Reddit + LunarCrush (si hay key)
│  │  └─ eventos.py        # listados, upgrades, desbloqueos (ver limitaciones)
│  ├─ universo.py          # top 200, volumen > 5 M USD, sin stables ni wrapped
│  ├─ indicadores.py       # SMA 20/50/200, RSI, MACD, volatilidad, drawdown
│  ├─ filtros.py           # anomalías, deduplicado de noticias, reputación
│  ├─ puntaje.py           # puntaje 0-100 con pesos de config.yaml
│  ├─ interpretacion.py    # textos por regla, cada frase con su dato y fuente
│  ├─ almacen.py           # SQLite: snapshots diarios, noticias, puntajes
│  ├─ graficos.py          # Plotly (interactivo, embebido en el HTML)
│  └─ reporte.py           # plantilla Jinja2 -> reportes/AAAA-MM-DD.html
├─ plantillas/reporte.html
├─ datos/cripto.db         # histórico SQLite (+ export CSV opcional)
└─ reportes/               # un HTML por día; se abre solo en el navegador
```

## 2. Flujo de datos (una corrida)

1. **Universo**: CoinGecko top 200 por capitalización, quito stablecoins y wrapped (lista en config) y lo que tenga volumen 24 h < 5 M USD.
2. **Velas**: 365 días diarios desde Binance (par USDT); si la moneda no está en Binance, CoinGecko como respaldo. Todo con caché local para no repetir descargas.
3. **Mercado**: capitalización total y dominancia BTC (CoinGecko /global), Fear & Greed.
4. **Noticias y social**: recolecto, deduplico por título y URL, descarto fuentes fuera de la lista blanca y noticias que no mencionan una moneda del universo.
5. **Indicadores y filtros**: calculo indicadores y marco anomalías (volumen > 2x su media de 30 días, movimientos de precio fuera de 2 desviaciones, saltos de sentimiento).
6. **Puntaje** 0-100 por moneda (ver punto 4).
7. **Guardar** en SQLite y **comparar** contra la corrida anterior para las alertas.
8. **Reporte HTML** y se abre en el navegador.

Si una fuente falla, el programa sigue y el reporte lo dice ("Noticias: sin datos hoy, CryptoPanic no respondió").

## 3. Fuentes y qué esperar de cada una

| Necesidad | Fuente | Key | Nota |
|---|---|---|---|
| Velas, volumen | Binance REST público | No | El WebSocket no aporta a un reporte diario; lo dejaría fuera |
| Top 200, mcap, dominancia, respaldo | CoinGecko API pública | No | Límite ~30 llamadas/min, lo respeto con pausas |
| Fear & Greed | alternative.me | No | |
| Noticias | RSS (CoinDesk, Cointelegraph, The Block, Decrypt, Bitcoin Magazine) | No | Base sin key |
| Noticias + votos | CryptoPanic | Sí (gratis) | Opcional; hoy su API pide token |
| Social | Reddit (r/CryptoCurrency y subreddits por moneda) | No / opcional | Conteo de menciones y tono por palabras clave |
| Social | LunarCrush | Sí (de pago) | Opcional |
| Social | Binance Square | — | No tiene API pública; scrapearlo es frágil, propongo omitirlo |
| Listados | Anuncios de Binance (RSS/JSON público) | No | |
| Desbloqueos | — | — | No hay fuente gratuita confiable; el reporte dirá "datos insuficientes" salvo que agregues una key (CoinMarketCal tiene plan gratis) |

## 4. Puntaje (pesos editables en config.yaml)

| Componente | Peso inicial | Qué mide |
|---|---|---|
| Tendencia | 30 | Precio vs SMA 20/50/200, cruce de medias, MACD |
| Momentum y volumen | 25 | Retorno 7 y 30 días, RSI (penaliza > 75 y < 25), volumen relativo |
| Sentimiento | 20 | Tono y cantidad de noticias y menciones, cambio vs ayer |
| Riesgo (invertido) | 25 | Volatilidad 30 d, caída máxima 90 d, liquidez |

Cada subpuntaje se normaliza a 0-100 por percentil dentro del universo del día. Si una moneda no tiene datos de sentimiento, su peso se reparte entre los demás y el reporte lo marca.

## 5. Reporte

- Resumen del mercado en 5 líneas, cada una con su número y fuente.
- Top 10 con tabla y, por moneda: por qué aparece, qué la respalda, qué la pone en riesgo. Textos generados por reglas (no IA), así cada frase sale de un dato verificable; hechos y lecturas van separados.
- Gráficos: precio con SMA, volumen, sentimiento en el tiempo, rendimiento relativo vs BTC.
- Noticias relevantes con enlace.
- Alertas: entradas y salidas del top 10, cambios de puntaje grandes, anomalías nuevas.
- Pie con aviso: no es recomendación de inversión.

## 6. Librerías

requests, pandas, numpy, plotly, jinja2, feedparser, python-dotenv, pyyaml. Indicadores calculados con pandas (evito pandas-ta/TA-Lib, que suelen dar problemas al instalar en Windows). SQLite viene con Python.

## 7. Etapas

1. Universo + velas + mercado + SQLite + reporte mínimo (tabla y un gráfico) + tarea programada.
2. Indicadores, puntaje y gráficos completos.
3. Noticias y filtros.
4. Sentimiento social y eventos.
5. Interpretaciones y alertas día contra día.
