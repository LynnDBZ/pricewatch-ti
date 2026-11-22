"""Reporte diario: la IA solo REDACTA; cada cifra que escribe se verifica contra los datos.

Si el texto de la IA contiene un número que no está en los datos calculados, se descarta
y se reintenta; si vuelve a fallar, se usa un resumen determinista (plantilla).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")

SYSTEM = (
    "Eres un analista de compras de tecnología. Redactas el resumen diario de precios de "
    "laptops en español claro, en un solo párrafo de máximo 110 palabras. "
    "REGLAS ESTRICTAS: usa ÚNICAMENTE los datos del JSON que recibes; no inventes productos, "
    "tiendas ni cifras; no calcules números nuevos (sumas, promedios, diferencias) y copia "
    "las cifras tal cual aparecen; si no hay bajadas, dilo sin rodeos. No uses listas ni títulos."
)


def _norm(token: str) -> float:
    return round(float(token.replace(",", "")), 2)


def numbers_in(text: str) -> set[float]:
    return {_norm(t) for t in NUM_RE.findall(text)}


def verify(summary: str, facts: dict) -> list[float]:
    """Devuelve los números del resumen que NO están respaldados por los datos."""
    allowed = numbers_in(json.dumps(facts, ensure_ascii=False))
    return sorted(n for n in numbers_in(summary) if n not in allowed)


SYMBOLS = {"PEN": "S/"}


def money(cur: str, x: float) -> str:
    return f"{SYMBOLS.get(cur, cur)} {x:,.2f}"


def template_summary(facts: dict) -> str:
    s = (f"Hoy se monitorearon {facts['products_tracked']} productos en "
         f"{facts['stores_tracked']} tienda(s).")
    if facts["new_products"]:
        s += f" Se registraron {facts['new_products']} productos nuevos."
    if facts["drops_total"]:
        t = facts["top_drops"][0]
        s += (f" Se detectaron {facts['drops_total']} bajadas de al menos "
              f"{facts['threshold_pct']}%. La mayor fue «{t['name']}» en {t['store']}: "
              f"pasó de {money(t['currency'], t['price_before'])} a "
              f"{money(t['currency'], t['price_now'])} ({t['change_pct']}%).")
    else:
        s += f" No hubo bajadas de al menos {facts['threshold_pct']}%."
    if facts["rises_total"]:
        s += f" {facts['rises_total']} productos subieron de precio."
    return s


def llm_summary(facts: dict, model: str, client=None) -> str:
    import anthropic

    client = client or anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=500,
        system=SYSTEM,
        messages=[{"role": "user",
                   "content": "Datos verificados (JSON):\n" + json.dumps(facts, ensure_ascii=False)}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def drops_table(facts: dict) -> str:
    if not facts["top_drops"]:
        return "_Sin bajadas relevantes hoy._"
    lines = ["| Producto | Tienda | Antes | Ahora | Cambio | Señal |",
             "|---|---|---:|---:|---:|---|"]
    for d in facts["top_drops"]:
        flag = ""
        if d["lowest_in_window"]:
            flag = f"Mínimo de {facts['window_days']} días"
        elif d.get("vs_window_avg_pct", 0) <= -10:
            flag = "Muy bajo vs. promedio"
        lines.append(
            f"| [{d['name']}]({d['url']}) | {d['store']} | "
            f"{money(d['currency'], d['price_before'])} | {money(d['currency'], d['price_now'])} | "
            f"{d['change_pct']}% | {flag} |"
        )
    return "\n".join(lines)


@dataclass
class Report:
    markdown: str
    source: str            # "llm" o "template"
    rejected: int = 0      # intentos de la IA descartados por la verificación


def generate_report(facts: dict, model: str = "claude-haiku-5-5", use_llm: bool = True,
                    client=None, attempts: int = 2) -> Report:
    summary, source, rejected = None, "template", 0
    if use_llm and (client is not None or os.getenv("ANTHROPIC_API_KEY")):
        for _ in range(attempts):
            try:
                text = llm_summary(facts, model, client)
            except Exception as exc:  # noqa: BLE001  red, cuota, clave inválida...
                log.warning("Fallo la IA: %s", exc)
                break
            bad = verify(text, facts)
            if not bad:
                summary, source = text, "llm"
                break
            rejected += 1
            log.warning("Resumen descartado, cifras no respaldadas: %s", bad)
    if summary is None:
        summary = template_summary(facts)
    md = (f"# PriceWatch TI — Reporte del {facts['date']}\n\n{summary}\n\n"
          f"## Mayores bajadas\n\n{drops_table(facts)}\n\n"
          f"---\n_Cifras calculadas por código a partir del scraping. "
          f"Resumen: {'IA verificada' if source == 'llm' else 'plantilla automática'}._\n")
    return Report(md, source, rejected)
