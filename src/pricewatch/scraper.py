"""Módulo RPA: extrae nombre, precio, enlace e imagen de tiendas públicas.

Buenas prácticas incluidas: respeta robots.txt, se identifica con un User-Agent,
espera entre peticiones y reintenta ante errores temporales.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import StoreCfg
from .models import Item

log = logging.getLogger(__name__)
USER_AGENT = "PriceWatchTI/1.0 (proyecto academico UTP)"


def parse_price(text: str) -> float:
    """Convierte '$1,299.00', 'S/ 2.499,00' o '1 299,50' en float."""
    m = re.search(r"\d[\d.,]*", text.replace("\xa0", " ").replace(" ", ""))
    if not m:
        raise ValueError(f"Sin precio en: {text!r}")
    s = m.group().rstrip(".,")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):      # 2.499,00 (formato europeo/latino)
            s = s.replace(".", "").replace(",", ".")
        else:                                 # 1,299.00
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        if s.count(".") > 1 or len(tail) == 3:  # 2.499 -> miles
            s = s.replace(".", "")
    return float(s)


def parse_html(html: str, base_url: str, cfg: StoreCfg) -> tuple[list[Item], str | None]:
    """Extrae productos de una página y devuelve también la URL de la página siguiente."""
    soup = BeautifulSoup(html, "html.parser")
    sel = cfg.selectors
    items: list[Item] = []
    for card in soup.select(sel["item"]):
        name_el = card.select_one(sel["name"])
        price_el = card.select_one(sel["price"])
        link_el = card.select_one(sel.get("link", sel["name"]))
        if not (name_el and price_el and link_el and link_el.get("href")):
            continue
        attr = sel.get("name_attr")
        name = (name_el.get(attr) if attr else None) or name_el.get_text(" ", strip=True)
        try:
            price = parse_price(price_el.get_text(" ", strip=True))
        except ValueError:
            log.warning("Precio ilegible en %s", cfg.name)
            continue
        img = card.select_one(sel["image"]) if sel.get("image") else None
        image = urljoin(base_url, img["src"]) if img is not None and img.get("src") else None
        items.append(
            Item(cfg.name, " ".join(name.split()), urljoin(base_url, link_el["href"]),
                 price, cfg.currency, image)
        )
    nxt = None
    if sel.get("next"):
        n = soup.select_one(sel["next"])
        if n is not None and n.get("href"):
            nxt = urljoin(base_url, n["href"])
    return items, nxt


def _next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        raise ValueError("La página no trae __NEXT_DATA__ (¿cambió la tienda o bloqueó el acceso?)")
    return json.loads(m.group(1))


def with_page(url: str, n: int) -> str:
    """Pone/cambia el parámetro ?page=N de una URL."""
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q["page"] = str(n)
    return urlunparse(p._replace(query=urlencode(q)))


def _falabella_price(prices: list[dict]) -> float:
    """Precio vigente SIN tarjeta: evento/internet; si no hay, el normal.
    (cmrPrice es un precio exclusivo con tarjeta y se ignora.)"""
    current = {}
    for pr in prices:
        if not pr.get("crossed") and pr.get("price"):
            current.setdefault(pr["type"], pr["price"][0])
    for t in ("eventPrice", "internetPrice", "normalPrice"):
        if t in current:
            return parse_price(str(current[t]))
    for pr in prices:
        if pr.get("type") == "normalPrice" and pr.get("price"):
            return parse_price(str(pr["price"][0]))
    raise ValueError("sin precio")


def parse_next_falabella(html: str, base_url: str, cfg: StoreCfg) -> list[Item]:
    """Falabella y Sodimac (mismo grupo y misma plataforma)."""
    results = _next_data(html)["props"]["pageProps"].get("results", [])
    items = []
    for r in results:
        try:
            price = _falabella_price(r.get("prices", []))
        except (ValueError, KeyError):
            continue
        img = (r.get("mediaUrls") or [None])[0]
        items.append(Item(cfg.name, " ".join(r["displayName"].split()),
                          urljoin(base_url, r["url"]), price, cfg.currency, img))
    return items


def ripley_slug(name: str) -> str:
    """Nombre -> parte del enlace de Ripley (ej. 'LAPTOP ... 15.6”' -> 'laptop-...-156')."""
    for sym in "™®©":                   # NFKD convertiría ™ en "tm"; Ripley simplemente lo omite
        name = name.replace(sym, "")
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def parse_next_ripley(html: str, base_url: str, cfg: StoreCfg) -> list[Item]:
    """Enlace de Ripley = nombre-en-minúsculas + '-' + parentProductID en minúsculas.
    Productos propios: ...-2004376315445p ; vendedores externos: ...-pmp20001530892."""
    products = _next_data(html)["props"]["pageProps"]["findabilityProps"]["data"]["products"]
    # enlaces reales presentes en la página (cuando existen, se prefieren)
    links = {}
    for path, pid in re.findall(r'href="(/[^"?#]*-([a-z]{0,3}\d+p?))[?"#]', html):
        links.setdefault(pid, urljoin(base_url, path))
    items = []
    for p in products:
        try:
            price = float(p["priceNumber"])
        except (KeyError, TypeError, ValueError):
            continue
        pid = str(p.get("parentProductID") or p["sku"]).lower()
        url = links.get(pid) or urljoin(base_url, f"/{ripley_slug(p['name'])}-{pid}")
        items.append(Item(cfg.name, " ".join(p["name"].split()), url, price,
                          p.get("currency") or cfg.currency, p.get("primaryImage")))
    return items


def _vtex_categories(p: dict) -> list[str]:
    cats = p.get("categories") or []
    if isinstance(cats, dict):          # formato del estado interno (VTEX IO)
        cats = cats.get("json", [])
    return [c.strip("/").split("/")[-1] for c in cats if isinstance(c, str) and c.strip("/")]


def parse_vtex(products: list[dict], base_url: str, cfg: StoreCfg) -> list[Item]:
    """Respuesta de /api/catalog_system/pub/products/search (Promart, Coolbox)."""
    items = []
    for p in products:
        price = None
        for it in p.get("items", []):
            for s in it.get("sellers", []):
                o = s.get("commertialOffer") or {}
                if o.get("Price", 0) > 0 and o.get("AvailableQuantity", 1) > 0:
                    price = float(o["Price"])
                    break
            if price:
                break
        if not price or not p.get("link"):
            continue
        cats = _vtex_categories(p)
        if cfg.category_regex and cats and not any(
                re.search(cfg.category_regex, c, re.IGNORECASE) for c in cats):
            continue                    # accesorios, cables, discos duros...
        imgs = (p.get("items") or [{}])[0].get("images") or [{}]
        items.append(Item(cfg.name, " ".join(p["productName"].split()),
                          urljoin(base_url, p["link"]), price, cfg.currency,
                          imgs[0].get("imageUrl")))
    return items


def parse_page(html: str, url: str, cfg: StoreCfg) -> tuple[list[Item], str | None]:
    """Punto único de entrada según el tipo de tienda (páginas HTML)."""
    if cfg.type == "next_falabella":
        items, nxt = parse_next_falabella(html, url, cfg), None
    elif cfg.type == "next_ripley":
        items, nxt = parse_next_ripley(html, url, cfg), None
    else:
        items, nxt = parse_html(html, url, cfg)
    return [i for i in items if i.price >= cfg.min_price], nxt


class Scraper:
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self._robots: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.session.get(origin + "/robots.txt", timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[origin] = rp
                else:                       # sin robots.txt => sin restricciones
                    self._robots[origin] = None
            except requests.RequestException:
                log.warning("No se pudo leer robots.txt de %s", origin)
                return False
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def _scrape_vtex(self, cfg: StoreCfg) -> list[Item]:
        p = urlparse(cfg.start_url)
        origin = f"{p.scheme}://{p.netloc}"
        found: list[Item] = []
        for page in range(cfg.max_pages):
            a, b = page * 50, page * 50 + 49
            url = (f"{origin}/api/catalog_system/pub/products/search"
                   f"?ft={cfg.api_query}&_from={a}&_to={b}")
            if not self.allowed(url):
                log.warning("robots.txt no permite la API de %s; se omite", cfg.name)
                break
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            items = parse_vtex(data, origin, cfg)
            found += items
            log.info("%s lote %d: %d laptops de %d productos", cfg.name, page + 1,
                     len(items), len(data))
            if data and not items and cfg.category_regex:
                seen = sorted({c for p in data for c in _vtex_categories(p)})[:8]
                log.warning("%s: ningún producto pasó el filtro de categoría. Categorías vistas: %s",
                            cfg.name, seen)
            if len(data) < 50:
                break
            time.sleep(self.delay)
        return found

    def scrape_store(self, cfg: StoreCfg) -> list[Item]:
        if cfg.type == "vtex_api":
            found = self._scrape_vtex(cfg)
        else:
            found = []
            url: str | None = cfg.start_url
            for page in range(cfg.max_pages):
                if not url:
                    break
                if not self.allowed(url):
                    log.warning("robots.txt no permite %s; se omite", url)
                    break
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                items, url = parse_page(resp.text, resp.url, cfg)
                found += items
                log.info("%s página %d: %d productos", cfg.name, page + 1, len(items))
                if not items:
                    break
                if cfg.type.startswith("next_"):
                    url = with_page(cfg.start_url, page + 2)
                if url:
                    time.sleep(self.delay)
        unique = {i.url: i for i in found if i.price >= cfg.min_price}
        return list(unique.values())
