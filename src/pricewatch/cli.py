from __future__ import annotations

import argparse
import logging
import random
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .analyzer import analyze
from .config import demo_store, get_settings, load_stores
from .dashboard import build_dashboard
from .notifier import email_configured, export_csv, save_report, send_email
from .reporter import generate_report
from .scraper import Scraper, parse_page
from .simulate import drift
from .storage import Database

log = logging.getLogger("pricewatch")
DEFAULT_FIXTURE = "tests/fixtures/laptops.html"


def today() -> str:
    return datetime.now(ZoneInfo("America/Lima")).date().isoformat()


def _publish(db: Database, day: str, st, args) -> None:
    facts = analyze(db, day, st.drop_threshold, st.window_days)
    rep = generate_report(facts, st.model, use_llm=not getattr(args, "no_llm", False))
    path = save_report(rep.markdown, day)
    export_csv(db)
    build_dashboard(db)
    print(rep.markdown)
    log.info("Reporte guardado en %s (resumen: %s, descartados: %d)", path, rep.source, rep.rejected)
    if not getattr(args, "no_email", True) and email_configured():
        send_email(f"PriceWatch TI — {day}", rep.markdown)


def cmd_run(args, st) -> int:
    stores = load_stores()
    items = []
    if args.fixture:
        html = Path(args.fixture).read_text(encoding="utf-8")
        for cfg in stores:
            items += parse_page(html, cfg.start_url, cfg)[0]
    else:
        sc = Scraper(st.request_delay)
        for cfg in stores:
            try:
                items += sc.scrape_store(cfg)
            except Exception as exc:  # noqa: BLE001  una tienda caída no debe tumbar todo el bot
                log.error("Falló %s: %s", cfg.name, exc)
    if not items:
        log.error("No se extrajo ningún producto; no se guarda nada.")
        return 1
    db = Database(args.db)
    day = today()
    db.save(items, day)
    log.info("Guardados %d precios del %s", len(items), day)
    _publish(db, day, st, args)
    return 0


def cmd_demo(args, st) -> int:
    cfg = demo_store()
    base, _ = parse_page(Path(args.fixture).read_text(encoding="utf-8"), cfg.start_url, cfg)
    db, rng = Database(args.db), random.Random(42)
    end = datetime.now(ZoneInfo("America/Lima")).date()
    items = base
    for i in range(args.days):
        day = (end - timedelta(days=args.days - 1 - i)).isoformat()
        if i == args.days - 1:      # el último día siempre trae ofertas, para mostrar el reporte
            items = [replace(it, price=round(it.price * f, 2))
                     for it, f in zip(items, (0.88, 1.0, 1.0, 0.92, 1.0, 1.04))]
        db.save(items, day)
        items = drift(items, rng)
    _publish(db, end.isoformat(), st, args)
    return 0


def cmd_report(args, st) -> int:
    _publish(Database(args.db), args.day or today(), st, args)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    st = get_settings()
    p = argparse.ArgumentParser(prog="pricewatch", description="PriceWatch TI")
    p.add_argument("--db", default=st.db_path)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="scrapea, guarda, analiza y envía el reporte diario")
    r.add_argument("--fixture", help="usar un HTML local en vez de internet")
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--send-email", dest="no_email", action="store_false", default=True)
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("demo", help="genera historial simulado y el reporte (sin internet)")
    d.add_argument("--days", type=int, default=14)
    d.add_argument("--fixture", default=DEFAULT_FIXTURE)
    d.add_argument("--no-llm", action="store_true")
    d.set_defaults(func=cmd_demo, no_email=True)

    rp = sub.add_parser("report", help="regenera el reporte de un día desde la base de datos")
    rp.add_argument("--day")
    rp.add_argument("--no-llm", action="store_true")
    rp.set_defaults(func=cmd_report, no_email=True)

    args = p.parse_args(argv)
    return args.func(args, st)
