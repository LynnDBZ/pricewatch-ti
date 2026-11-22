from __future__ import annotations

import csv
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import markdown

from .storage import Database

log = logging.getLogger(__name__)


def save_report(md: str, day: str, folder: str = "reports") -> Path:
    Path(folder).mkdir(parents=True, exist_ok=True)
    path = Path(folder) / f"{day}.md"
    path.write_text(md, encoding="utf-8")
    return path


def export_csv(db: Database, path: str = "data/history.csv") -> Path:
    """CSV listo para abrir en Excel / Google Sheets / Power BI."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "tienda", "producto", "precio", "moneda", "url"])
        for p in db.all_series():
            for day, price in p["series"]:
                w.writerow([day, p["store"], p["name"], price, p["currency"], p["url"]])
    return Path(path)


def email_configured() -> bool:
    return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))


def send_email(subject: str, md: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("MAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content(md)
    msg.add_alternative(markdown.markdown(md, extensions=["tables"]), subtype="html")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    log.info("Correo enviado a %s", msg["To"])
