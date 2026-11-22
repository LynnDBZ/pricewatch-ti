from pathlib import Path

import pytest

from pricewatch.config import StoreCfg, demo_store
from pricewatch.scraper import parse_page, parse_price, parse_vtex, with_page

FIXTURE = Path(__file__).parent / "fixtures" / "laptops.html"


@pytest.mark.parametrize("text,expected", [
    ("$295.99", 295.99),
    ("$1,299.00", 1299.0),
    ("S/ 2,499.00", 2499.0),
    ("S/ 2.499,00", 2499.0),
    ("1 299,50", 1299.5),
    ("USD 2.499", 2499.0),
    ("899", 899.0),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_parse_price_invalid():
    with pytest.raises(ValueError):
        parse_price("agotado")


def test_parse_html_extracts_products_and_next_page():
    cfg = demo_store()
    items, nxt = parse_page(FIXTURE.read_text(encoding="utf-8"), cfg.start_url, cfg)
    assert len(items) == 6
    first = items[0]
    assert first.name == "Asus VivoBook X441NA-GA190"      # nombre completo desde el atributo title
    assert first.price == 295.99
    assert first.url.startswith("https://webscraper.io/test-sites")
    assert nxt and nxt.endswith("?page=2")


FIX = Path(__file__).parent / "fixtures"


CAT = r"^(laptops?|notebooks?|ultrabooks?|macbooks?|chromebooks?|port[aá]tiles?)\b"


def _cfg(name, type_, url):
    return StoreCfg(name=name, start_url=url, currency="PEN", type=type_, min_price=500,
                    category_regex=CAT if type_ == "vtex_api" else None)


def test_falabella_and_sodimac_next_data():
    for fixture, url in [("falabella.html", "https://www.falabella.com.pe/falabella-pe/search?Ntt=laptops"),
                         ("sodimac.html", "https://www.sodimac.com.pe/sodimac-pe/lista/cat40712/Laptops")]:
        items, _ = parse_page((FIX / fixture).read_text(encoding="utf-8"), url,
                              _cfg("X", "next_falabella", url))
        assert len(items) == 5
        assert all(i.price >= 500 and i.currency == "PEN" and i.url.startswith("https://") for i in items)
    # precio con evento (no el tachado ni el de tarjeta): MacBook Air M2 -> 2,999
    first, _ = parse_page((FIX / "falabella.html").read_text(encoding="utf-8"), "https://www.falabella.com.pe/",
                          _cfg("F", "next_falabella", "https://www.falabella.com.pe/"))
    assert first[0].price == 2999.0


def test_ripley_prices_and_links():
    url = "https://simple.ripley.com.pe/tecnologia/computacion/laptops"
    items, _ = parse_page((FIX / "ripley.html").read_text(encoding="utf-8"), url,
                          _cfg("Ripley", "next_ripley", url))
    assert len(items) == 5 and items[0].price == 2199.0
    assert all(i.url.startswith("https://simple.ripley.com.pe/") and "?" not in i.url for i in items)


def test_vtex_skips_unavailable_and_resolves_links():
    import json
    data = json.loads((FIX / "vtex_products.json").read_text(encoding="utf-8"))
    cfg = _cfg("Promart", "vtex_api", "https://www.promart.pe/x")
    items = parse_vtex(data, "https://www.promart.pe", cfg)
    # fuera: mouse y cable (categoría de accesorios, aunque el cable cuesta > 500) y la agotada
    assert [i.name for i in items] == ["Laptop Lenovo V15 G5 Intel Core i3 8GB 256GB SSD",
                                       "MacBook Air 13 M5"]
    assert items[0].url == "https://www.promart.pe/laptop-lenovo-v15-g5/p"


def test_with_page():
    assert with_page("https://a.pe/search?Ntt=laptops", 2) == "https://a.pe/search?Ntt=laptops&page=2"
    assert with_page("https://a.pe/lista/Laptops", 3) == "https://a.pe/lista/Laptops?page=3"


class _Resp:
    def __init__(self, text="", url="", data=None):
        self.text, self.url, self._data = text, url, data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _scraper(monkeypatch, responder):
    from pricewatch.scraper import Scraper
    sc = Scraper(delay=0)
    monkeypatch.setattr(sc, "allowed", lambda url: True)
    monkeypatch.setattr(sc.session, "get", lambda url, timeout=0: responder(url))
    return sc


def test_scrape_store_paginates_and_stops_on_empty_page(monkeypatch):
    start = "https://www.falabella.com.pe/falabella-pe/search?Ntt=laptops"
    page1 = (FIX / "falabella.html").read_text(encoding="utf-8")
    empty = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"results":[]}}}</script>'
    seen = []

    def responder(url):
        seen.append(url)
        return _Resp(page1 if "page=" not in url else empty, url)

    sc = _scraper(monkeypatch, responder)
    cfg = _cfg("Falabella", "next_falabella", start)
    cfg.max_pages = 5
    items = sc.scrape_store(cfg)
    assert len(items) == 5
    assert seen == [start, start + "&page=2"]          # pidió la 2 y paró al verla vacía


def test_scrape_store_vtex_filters_accessories(monkeypatch):
    import json
    data = json.loads((FIX / "vtex_products.json").read_text(encoding="utf-8"))
    sc = _scraper(monkeypatch, lambda url: _Resp(data=data))
    cfg = _cfg("Promart", "vtex_api", "https://www.promart.pe/tecnologia/laptops?PS=1")
    items = sc.scrape_store(cfg)
    assert [i.price for i in items] == [1849.0, 5799.0]  # accesorios y agotada, fuera


def test_ripley_builds_missing_links_with_site_pattern():
    import re

    from pricewatch.scraper import ripley_slug
    url = "https://simple.ripley.com.pe/tecnologia/computacion/laptops"
    html = (FIX / "ripley.html").read_text(encoding="utf-8")
    real, _ = parse_page(html, url, _cfg("Ripley", "next_ripley", url))
    no_links = re.sub(r'<a class="product-link"[^>]*>x</a>', "", html)       # simula carga diferida
    built, _ = parse_page(no_links, url, _cfg("Ripley", "next_ripley", url))
    assert [i.url for i in built] == [i.url for i in real]                     # mismo enlace
    assert ripley_slug("LAPTOP ACER ASPIRE LITE AMD RYZEN 5 8GB RAM 512GB SSD 15.6”") == \
        "laptop-acer-aspire-lite-amd-ryzen-5-8gb-ram-512gb-ssd-156"
