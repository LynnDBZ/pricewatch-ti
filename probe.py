"""Diagnóstico de tiendas v2: ¿se puede leer esta página? Uso:
    python probe.py URL1 URL2 ...
Usa la URL de la LISTA DE LAPTOPS de cada tienda (no la página de inicio).
Guarda el HTML en la carpeta probe_html/ (cada archivo dentro es una página).
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

UA = "PriceWatchTI/1.0 (proyecto academico UTP)"
PRICE = re.compile(r"S/\.?\s?\d[\d.,]*\d|US\$\s?\d[\d.,]*\d|(?<![\w$])\$\s?\d[\d.,]*\d")
BLOCK = ("just a moment", "access denied", "cf-chl", "px-captcha", "are you a robot",
         "verify you are human", "unusual traffic")
JSON_KEYS = ("value_number", "sellingprice", '"price"', "pricerange", "commertialoffer")


def vtex_api(origin: str):
    """Muchas tiendas peruanas usan VTEX, que tiene una API pública de catálogo."""
    url = origin + "/api/catalog_system/pub/products/search?ft=laptop&_from=0&_to=4"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        data = r.json()
        if not isinstance(data, list) or not data:
            return f"API VTEX: respondió pero sin productos (status {r.status_code})"
        p = data[0]
        price = p["items"][0]["sellers"][0]["commertialOffer"]["Price"]
        return f"API VTEX: FUNCIONA. {len(data)} productos; ejemplo: {p.get('productName')} -> {price}"
    except Exception as e:  # noqa: BLE001
        return f"API VTEX: no disponible ({type(e).__name__})"


def probe(url: str) -> None:
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    print("=" * 72)
    print(url)
    try:
        r = requests.get(origin + "/robots.txt", headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 200:
            rp = RobotFileParser()
            rp.parse(r.text.splitlines())
            ok = rp.can_fetch(UA, url)
            print("robots.txt :", "PERMITE esta URL" if ok else "NO PERMITE esta URL  <-- no usar")
        else:
            print(f"robots.txt : no existe (status {r.status_code}), sin restricciones declaradas")
    except requests.RequestException as e:
        print("robots.txt : error de red:", e)

    try:
        resp = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"},
                            timeout=20)
    except requests.RequestException as e:
        print("Página     : error de red:", e)
        return
    html = resp.text
    low = html.lower()
    prices = PRICE.findall(html)
    json_hits = {k: low.count(k) for k in JSON_KEYS if low.count(k)}
    Path("probe_html").mkdir(exist_ok=True)
    out = Path("probe_html") / (p.netloc.replace(":", "_") + ".html")
    out.write_text(html, encoding="utf-8")

    print(f"Página     : status {resp.status_code}, {len(html):,} caracteres  (guardada en {out})")
    print(f"Precios visibles en el HTML: {len(prices)}  ejemplos: {prices[:4]}")
    print(f"Datos de precio dentro de JSON: {json_hits or 'ninguno'}")
    is_vtex = "vtex" in low
    blocked = resp.status_code in (401, 403, 429) or any(b in low for b in BLOCK)
    if blocked:
        verdict = "BLOQUEADA o con protección anti-bots. Descartar esta tienda."
    elif resp.status_code != 200:
        verdict = f"Respondió con status {resp.status_code}. Revisa que la URL abra en el navegador."
    elif len(prices) >= 5:
        verdict = "PROMETEDORA: hay precios en el HTML. Revisa que sean de laptops y no del menú."
    elif json_hits:
        verdict = "POSIBLE: los precios vienen dentro de JSON; se puede leer con otro método."
    elif is_vtex:
        verdict = "Tienda VTEX: los precios se cargan con JavaScript; mira el resultado de la API."
    else:
        verdict = "Probablemente carga los precios con JavaScript (necesitaría Playwright)."
    print("Veredicto  :", verdict)
    if is_vtex:
        print(vtex_api(origin))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python probe.py URL1 URL2 ...")
    for u in sys.argv[1:]:
        probe(u)
