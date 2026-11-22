"""Panel de visualización: un HTML estático con tabla y mini-gráficos (sin dependencias)."""
from __future__ import annotations

from html import escape
from pathlib import Path

from .storage import Database


def sparkline(values: list[float], w: int = 140, h: int = 36) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = " ".join(
        f"{i * w / (len(values) - 1):.1f},{h - 4 - (v - lo) / span * (h - 8):.1f}"
        for i, v in enumerate(values)
    )
    color = "#16a34a" if values[-1] <= values[0] else "#dc2626"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/></svg>')


def build_dashboard(db: Database, out: str = "docs/index.html") -> Path:
    rows = []
    for p in db.all_series():
        prices = [x[1] for x in p["series"]]
        first, last = prices[0], prices[-1]
        pct = (last - first) / first * 100 if first else 0
        rows.append(
            f"<tr><td><a href='{escape(p['url'])}'>{escape(p['name'])}</a></td>"
            f"<td>{escape(p['store'])}</td>"
            f"<td class='n'>{escape(p['currency'])} {last:,.2f}</td>"
            f"<td class='n'>{min(prices):,.2f}</td><td class='n'>{pct:+.1f}%</td>"
            f"<td>{sparkline(prices)}</td></tr>"
        )
    last_day = max((p["series"][-1][0] for p in db.all_series()), default="—")
    html = f"""<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PriceWatch TI</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem auto;max-width:980px;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.5rem;border-bottom:1px solid #ddd;
text-align:left}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
th{{background:#f3f4f6}}</style>
<h1>PriceWatch TI</h1><p>Última actualización: {escape(last_day)}</p>
<table><tr><th>Producto</th><th>Tienda</th><th>Precio actual</th><th>Mínimo</th>
<th>Variación total</th><th>Evolución</th></tr>{''.join(rows)}</table></html>"""
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
