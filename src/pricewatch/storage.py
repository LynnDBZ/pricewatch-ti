"""Historial propio: SQLite con un precio por producto por día."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY,
  store TEXT NOT NULL,
  name TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  image TEXT
);
CREATE TABLE IF NOT EXISTS prices(
  product_id INTEGER NOT NULL REFERENCES products(id),
  day TEXT NOT NULL,
  price REAL NOT NULL,
  currency TEXT NOT NULL,
  PRIMARY KEY(product_id, day)
);
"""


class Database:
    def __init__(self, path: str = "data/pricewatch.db"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save(self, items: list[Item], day: str) -> None:
        with self.conn:
            for it in items:
                self.conn.execute(
                    "INSERT INTO products(store,name,url,image) VALUES(?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET name=excluded.name, image=excluded.image",
                    (it.store, it.name, it.url, it.image),
                )
                pid = self.conn.execute(
                    "SELECT id FROM products WHERE url=?", (it.url,)
                ).fetchone()["id"]
                self.conn.execute(
                    "INSERT OR REPLACE INTO prices(product_id,day,price,currency) VALUES(?,?,?,?)",
                    (pid, day, it.price, it.currency),
                )

    def prices_on(self, day: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT p.id AS product_id, p.store, p.name, p.url, pr.price, pr.currency "
            "FROM prices pr JOIN products p ON p.id=pr.product_id WHERE pr.day=? "
            "ORDER BY p.store, p.name",
            (day,),
        ).fetchall()

    def history_before(self, product_id: int, day: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT day, price FROM prices WHERE product_id=? AND day<? ORDER BY day DESC",
            (product_id, day),
        ).fetchall()
        return [(r["day"], r["price"]) for r in rows]

    def all_series(self) -> list[dict]:
        out = []
        for p in self.conn.execute("SELECT * FROM products ORDER BY store, name"):
            rows = self.conn.execute(
                "SELECT day, price, currency FROM prices WHERE product_id=? ORDER BY day",
                (p["id"],),
            ).fetchall()
            if rows:
                out.append({
                    "store": p["store"], "name": p["name"], "url": p["url"],
                    "currency": rows[-1]["currency"],
                    "series": [(r["day"], r["price"]) for r in rows],
                })
        return out
