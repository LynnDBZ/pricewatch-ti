"""Los NÚMEROS se calculan aquí, con código. La IA nunca calcula cifras."""
from __future__ import annotations

from datetime import date, timedelta

from .storage import Database


def analyze(db: Database, day: str, drop_threshold: float = 5.0,
            window_days: int = 30, top_n: int = 5) -> dict:
    d = date.fromisoformat(day)
    cutoff = (d - timedelta(days=window_days)).isoformat()
    rows = db.prices_on(day)
    stores: set[str] = set()
    new = rises = 0
    drops: list[dict] = []

    for r in rows:
        stores.add(r["store"])
        hist = db.history_before(r["product_id"], day)
        if not hist:
            new += 1
            continue
        prev = hist[0][1]
        pct = round((r["price"] - prev) / prev * 100, 1)
        if pct >= drop_threshold:
            rises += 1
        if pct > -drop_threshold:
            continue
        window = [p for (dd, p) in hist if dd >= cutoff]
        item = {
            "name": r["name"], "store": r["store"], "url": r["url"],
            "currency": r["currency"],
            "price_now": round(r["price"], 2),
            "price_before": round(prev, 2),
            "saving_amount": round(prev - r["price"], 2),
            "change_pct": pct,
            "lowest_in_window": len(window) >= 3 and r["price"] < min(window),
        }
        if len(window) >= 3:
            avg = sum(window) / len(window)
            item["window_avg"] = round(avg, 2)
            item["vs_window_avg_pct"] = round((r["price"] - avg) / avg * 100, 1)
        drops.append(item)

    drops.sort(key=lambda x: x["change_pct"])
    return {
        "date": day,
        "window_days": window_days,
        "threshold_pct": drop_threshold,
        "products_tracked": len(rows),
        "stores_tracked": len(stores),
        "new_products": new,
        "drops_total": len(drops),
        "rises_total": rises,
        "top_drops": drops[:top_n],
    }
