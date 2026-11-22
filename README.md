# PriceWatch TI

Bot que **vigila precios de laptops** en tiendas públicas, **guarda su historial**, **detecta bajadas** y envía cada día un **reporte redactado con IA** cuyas cifras se verifican por código.

Proyecto final · Herramientas de Desarrollo Profesional TIC · UTP

## Cómo funciona

```
stores.yaml ─► Scraper (RPA) ─► SQLite (historial) ─► Analyzer (calcula cifras)
                                                          │
                                  ┌───────────────────────┘
                                  ▼
                    IA redacta el resumen ─► Verificador de cifras ─► (si falla) plantilla
                                  │
                                  ▼
              Reporte .md + correo + CSV (Excel/Sheets) + panel HTML
```

| Requisito del proyecto | Dónde está |
|---|---|
| **RPA** (web scraping) | `src/pricewatch/scraper.py` — respeta robots.txt, User-Agent propio, pausas y reintentos |
| **IA** | `src/pricewatch/reporter.py` — la IA solo redacta; **no calcula** |
| **Control contra datos inventados** | `reporter.verify()` — todo número del texto debe existir en los datos; si no, se descarta, se reintenta y finalmente se usa una plantilla |
| **Historial propio** | `storage.py` (SQLite, un precio por producto por día) |
| **Fuentes controladas** | `config/stores.yaml` — el usuario decide qué tiendas vigilar |
| **Acción automática** | `.github/workflows/daily.yml` (cron diario) + correo SMTP |
| **Integración** | CSV (`data/history.csv`), correo HTML y panel `docs/index.html` |
| **DevOps** | `Dockerfile`, `docker-compose.yml`, CI con lint + tests + build (`ci.yml`) |

## Uso rápido (sin internet ni API key)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
pricewatch demo --no-llm          # historial simulado de 14 días + reporte
```
Abre `docs/index.html` para ver el panel y `reports/AAAA-MM-DD.md` para el reporte.

## Uso real

```bash
cp .env.example .env              # completa ANTHROPIC_API_KEY y datos de correo
export $(grep -v '^#' .env | xargs)
pricewatch run                    # scrapea, guarda, analiza y genera el reporte
pricewatch run --send-email       # además lo envía por correo
```
Sin `ANTHROPIC_API_KEY` el bot funciona igual con un resumen de plantilla.

### Docker
```bash
docker compose up --build
```

### Automatización diaria (GitHub Actions)
1. Sube el repo a GitHub.
2. En *Settings → Secrets and variables → Actions* crea: `ANTHROPIC_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_TO`.
3. El flujo *Reporte diario* corre todos los días a las 07:00 (Perú) y conserva el historial con caché de Actions. También se puede lanzar a mano (*Run workflow*).

## Tiendas incluidas (`config/stores.yaml`)
| Tienda | Método | Notas |
|---|---|---|
| Falabella | datos `__NEXT_DATA__` de la página | precio vigente sin tarjeta (se ignora el precio CMR) |
| Ripley | datos `__NEXT_DATA__` de la página | enlace canónico del producto |
| Promart y Coolbox | API pública de catálogo VTEX | 50 productos por lote |
| Sodimac | igual que Falabella | apagada por defecto (comparte vendedores con Falabella) |

`min_price` descarta accesorios baratos que se cuelan en la búsqueda. Antes de agregar una tienda nueva,
ejecuta `python probe.py "URL-de-la-lista-de-laptops"` para saber si se puede leer.

## Agregar otra tienda
Copia un bloque de `config/stores.yaml`. Según el tipo de tienda usa `next_falabella`, `next_ripley`, `vtex_api`
o `css` (con selectores CSS; mira `demo_store()` en `config.py` como ejemplo). Revisa antes los términos de uso y el `robots.txt`.

## Limitaciones
- Funciona con páginas HTML estáticas; sitios que cargan precios con JavaScript necesitarían Playwright.
- La verificación comprueba **cifras**, no que cada frase sea perfecta; por eso la tabla de bajadas se genera siempre por código.
- El sitio de prueba tiene precios fijos: para ver bajadas usa `pricewatch demo`.
