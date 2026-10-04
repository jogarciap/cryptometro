# Cryptometro (investigador cripto)

Herramienta de investigación: junta precios y datos de mercado, marca lo que se sale de lo normal y arma un reporte HTML diario. No opera ni pide claves de exchange. No es una recomendación de inversión.

## En la nube (sin instalar nada)

Este repositorio corre solo 4 veces por día con GitHub Actions (`.github/workflows/reporte-diario.yml`: 09:00, 13:00, 17:00 y 21:15 hora de Argentina) y publica el último reporte en GitHub Pages:

- Último reporte: https://jogarciap.github.io/cryptometro/
- Reportes anteriores: https://jogarciap.github.io/cryptometro/historial.html
- Para correrlo a mano: pestaña **Actions** > **Reporte diario** > **Run workflow**.
- Keys opcionales: **Settings > Secrets and variables > Actions > New repository secret** con el nombre `COINGECKO_API_KEY` (y las demás de `.env.example` cuando se usen).
- El histórico (`datos/cripto.db` y los CSV) se guarda en el propio repositorio después de cada corrida.

## En tu PC (opcional)

### Instalar (una sola vez)

1. Instala Python 3.11 o superior desde https://www.python.org/downloads/ y marca **"Add python.exe to PATH"**.
2. Abre la carpeta `investigador-cripto` y haz doble clic en **`instalar.bat`**. Crea un entorno `.venv`, instala las librerías y copia `.env.example` a `.env`.

### Ejecutar

- Doble clic en **`ejecutar.bat`**, o desde una terminal en la carpeta: `ejecutar.bat`
- La primera vez tarda unos minutos (descarga un año de velas de ~150 monedas). Después solo baja lo que falta.
- Al terminar abre el reporte en el navegador. Queda guardado en `reportes\reporte_AAAA-MM-DD.html`.

Opciones: `ejecutar.bat --no-abrir` (no abre el navegador) y `ejecutar.bat --verificar` (solo prueba las fuentes).

### Verificar que funciona

1. `ejecutar.bat --verificar` debe mostrar `OK` en Binance, CoinGecko y alternative.me.
2. `.venv\Scripts\python.exe pruebas\prueba_sin_internet.py` corre todo con datos inventados y debe mostrar 8 líneas `OK`.
3. Tras `ejecutar.bat`, revisa en el reporte que el precio de BTC coincida con el de tu exchange (puede variar unos minutos) y que en la tabla no aparezcan USDT, USDC ni WBTC.
4. Si algo falla, el detalle queda en `logs\AAAA-MM-DD.log`.

### Programar una vez al día

Doble clic en **`programar_tarea.bat`** (09:00 por defecto) o desde una terminal: `programar_tarea.bat 07:30`.
La tarea corre si tu sesión de Windows está iniciada. Para borrarla: `schtasks /Delete /TN "InvestigadorCripto" /F`.

## Qué guarda

| Dónde | Qué |
|---|---|
| `datos\cripto.db` | SQLite: velas diarias, mercado, Fear & Greed, métricas por moneda y día, registro de corridas |
| `datos\csv\monedas_AAAA-MM-DD.csv` | Lo mismo por moneda, para abrir en Excel |
| `reportes\` | Un HTML por día (necesitan `plotly.min.js`, que está en la misma carpeta) |

## Configurar

Todo se ajusta en `config.yaml`: tamaño del universo, volumen mínimo, exclusiones, umbrales de anomalía. `.env` es opcional; una key gratuita de CoinGecko (Demo) acelera la descarga.

## Fuentes de esta etapa

- **CoinGecko**: top 200, capitalización, dominancia, variaciones 24 h/7 d/30 d, y velas de respaldo para monedas sin par en Binance.
- **Binance** (API pública, sin key): velas diarias del par USDT. Si `api.binance.com` no responde, usa el espejo oficial `data-api.binance.vision`.
- **alternative.me**: índice Fear & Greed.

Los indicadores usan la **última vela diaria cerrada (UTC)**, no la del día en curso, para que el volumen sea comparable.
