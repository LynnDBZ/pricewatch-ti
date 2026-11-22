from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    store: str
    name: str
    url: str
    price: float
    currency: str = "USD"
    image: str | None = None
