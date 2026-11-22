"""Simulación de variaciones para la demo (los sitios de prueba tienen precios fijos)."""
from __future__ import annotations

import random
from dataclasses import replace

from .models import Item


def drift(items: list[Item], rng: random.Random) -> list[Item]:
    out = []
    for it in items:
        if rng.random() < 0.35:
            it = replace(it, price=round(it.price * (1 + rng.uniform(-0.12, 0.06)), 2))
        out.append(it)
    return out
