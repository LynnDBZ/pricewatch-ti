from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class StoreCfg:
    name: str
    start_url: str
    currency: str = "USD"
    max_pages: int = 3
    selectors: dict = field(default_factory=dict)
    enabled: bool = True
    type: str = "css"          # css | next_falabella | next_ripley | vtex_api
    min_price: float = 0.0     # descarta accesorios baratos que se cuelan en la búsqueda
    api_query: str = "laptop"  # solo vtex_api: texto de búsqueda
    category_regex: str | None = None  # solo vtex_api: la categoría final debe cumplirla


@dataclass
class Settings:
    db_path: str
    drop_threshold: float
    window_days: int
    request_delay: float
    model: str


def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("DB_PATH", "data/pricewatch.db"),
        drop_threshold=float(os.getenv("DROP_THRESHOLD_PCT", "5")),
        window_days=int(os.getenv("WINDOW_DAYS", "30")),
        request_delay=float(os.getenv("REQUEST_DELAY_SEC", "2")),
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
    )


def load_stores(path: str = "config/stores.yaml") -> list[StoreCfg]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [StoreCfg(**s) for s in data["stores"] if s.get("enabled", True)]


def demo_store() -> StoreCfg:
    """Sitio de prueba público, usado por el comando demo y por los tests."""
    return StoreCfg(
        name="WebScraper Test Site",
        start_url="https://webscraper.io/test-sites/e-commerce/static/computers/laptops",
        currency="USD",
        selectors={
            "item": "div.thumbnail", "name": "a.title", "name_attr": "title", "price": ".price",
            "link": "a.title", "image": "img", "next": "a[rel='next'], a.next",
        },
    )
