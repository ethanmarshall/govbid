"""Command-line jobs, handy for a daily cron / Task Scheduler entry.

  python -m app.cli sync --days 3            Pull new SAM.gov notices for your NAICS codes
  python -m app.cli digest --days 1          Print the daily digest (new matches, due soon, amendments, follow-ups, alerts)
  python -m app.cli digest --watch --email   Check amendments first, then email the digest (text + HTML)
  python -m app.cli watch                    Re-check tracked SAM.gov opportunities for amendments
"""
from __future__ import annotations

import argparse
import os
import smtplib
from email.message import EmailMessage

from .db import SessionLocal, init_db
from .services import sync_sam


def cmd_sync(args) -> None:
    db = SessionLocal()
    try:
        result = sync_sam(db, days_back=args.days, max_pages=args.pages)
        print(f"SAM.gov: {result['added']} new, {result['updated']} updated, {result['requests_used']} API requests")
        for e in result["errors"]:
            print("  error:", e)
    finally:
        db.close()


def build_digest(db, hours: int) -> tuple[str, int]:
    """Plain-text digest for the last `hours` (kept for older callers; see app/digest.py)."""
    from .digest import build_digest as _build, render_text, total_items

    d = _build(db, days=max(1, round(hours / 24)))
    return render_text(d), total_items(d)


def send_email(subject: str, text_body: str, html_body: str | None = None) -> str:
    """Send through the SMTP settings in .env (DIGEST_TO, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)."""
    to = os.getenv("DIGEST_TO")
    host = os.getenv("SMTP_HOST")
    if not (to and host):
        raise RuntimeError("Set DIGEST_TO and SMTP_HOST in backend/.env to email the digest.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or to
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    port = int(os.getenv("SMTP_PORT", "587"))
    smtp_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with smtp_cls(host, port, timeout=30) as s:
        if port != 465:
            s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        s.send_message(msg)
    return to


def cmd_digest(args) -> None:
    from .digest import build_digest as _build, render_html, render_text, subject, total_items

    if args.watch:
        cmd_watch(argparse.Namespace(max=args.max))
        print()
    db = SessionLocal()
    try:
        d = _build(db, days=args.days)
    finally:
        db.close()
    n = total_items(d)
    if args.email:
        if args.skip_empty and n == 0:
            print("Nothing to report; no email sent.")
            return
        try:
            to = send_email(subject(d), render_text(d), render_html(d))
        except Exception as exc:  # noqa: BLE001
            print(f"Email failed: {exc}")
            raise SystemExit(1) from exc
        print(f"Digest emailed to {to} ({n} items)")
    elif args.html:
        print(render_html(d))
    else:
        print(render_text(d), end="")


def cmd_watch(args) -> None:
    from .bidding import check_amendments

    with SessionLocal() as db:
        r = check_amendments(db, max_requests=args.max)
    print(f"Checked {r['checked']} tracked opportunities ({r['requests_used']} SAM.gov requests).")
    for ch in r["changes"]:
        print(f"- {ch['title'][:70]}: {ch['field']}: {ch['old']} -> {ch['new']}")
    for e in r["errors"]:
        print(f"Error: {e}")


def cmd_backup(args) -> None:
    from .backup import make_backup

    print(f"Backup written: {make_backup(args.out)}")


def main() -> None:
    init_db()
    ap = argparse.ArgumentParser(prog="govbid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--pages", type=int, default=3)
    s.set_defaults(func=cmd_sync)
    d = sub.add_parser("digest")
    d.add_argument("--days", type=int, default=1)
    d.add_argument("--email", action="store_true", help="send by email using the SMTP settings in .env")
    d.add_argument("--html", action="store_true", help="print the HTML version instead of text")
    d.add_argument("--watch", action="store_true", help="check tracked SAM.gov opportunities for amendments first")
    d.add_argument("--max", type=int, default=20, help="with --watch: most SAM.gov requests to use")
    d.add_argument("--skip-empty", action="store_true", help="with --email: do not send when there is nothing to report")
    d.set_defaults(func=cmd_digest)
    w = sub.add_parser("watch", help="re-check tracked SAM.gov opportunities for amendments")
    w.add_argument("--max", type=int, default=20, help="most SAM.gov requests to use")
    w.set_defaults(func=cmd_watch)
    bk = sub.add_parser("backup", help="zip the database and uploaded files")
    bk.add_argument("--out", default="backups", help="folder for the zip (default backups/)")
    bk.set_defaults(func=cmd_backup)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
