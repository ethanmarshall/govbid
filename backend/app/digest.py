"""Daily digest: new matching opportunities with bid scores, pipeline items due within 7 days, unseen amendment
changes, follow-ups due, and alerts from every module that offers dashboard_items(db).

build_digest(db, days) returns a plain dict; render_text and render_html turn it into an email body.
Used by `python -m app.cli digest` and GET /api/search/digest-preview.
"""
from __future__ import annotations

import html
import importlib
import os
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .bidding import OPEN_STAGES, _days_left, bid_score
from .eligibility import evaluate
from .models import Opportunity, OpportunityChange, PipelineEntry
from .services import get_profile

ALERT_MODULES = ["jobs_api", "quality_api", "finance_api", "sar_api", "workbook_api"]
DUE_WITHIN_DAYS = 7
ELIGIBILITY_LABELS = {"eligible_now": "Eligible now", "eligible_once_certified": "Eligible once certified"}


def app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:5173").rstrip("/")


def module_alerts(db: Session, modules: list[str] | None = None) -> list[dict]:
    """Call dashboard_items(db) on each module that has one. Missing modules or errors are skipped."""
    out = []
    for name in modules or ALERT_MODULES:
        try:
            mod = importlib.import_module(f"{__package__}.{name}")
        except Exception:  # noqa: BLE001
            continue
        fn = getattr(mod, "dashboard_items", None)
        if not callable(fn):
            continue
        try:
            items = fn(db) or []
        except Exception:  # noqa: BLE001
            db.rollback()
            continue
        out += [{"source": name.replace("_api", ""), "text": str(t)} for t in items]
    return out


def build_digest(db: Session, days: int = 1) -> dict:
    profile = get_profile(db)
    since = datetime.utcnow() - timedelta(days=days)

    new = []
    for o in db.scalars(select(Opportunity).where(Opportunity.fetched_at >= since)).all():
        st = evaluate(o.set_aside_code, o.naics, profile).status
        if st not in ELIGIBILITY_LABELS:
            continue
        try:
            sc = bid_score(db, o, profile, with_past_performance=True)
        except Exception:  # noqa: BLE001
            sc = {"score": None, "recommendation": ""}
        new.append({"id": o.id, "title": o.title, "agency": o.agency, "solicitation_number": o.solicitation_number,
                    "naics": o.naics, "set_aside": o.set_aside_desc or o.set_aside_code, "due": o.response_deadline,
                    "url": o.url, "eligibility": st, "eligibility_label": ELIGIBILITY_LABELS[st],
                    "score": sc.get("score"), "recommendation": sc.get("recommendation", ""), "jcp_note": sc.get("jcp_note")})
    new.sort(key=lambda r: (r["eligibility"] != "eligible_now", -(r["score"] or 0)))

    due = []
    for p in db.scalars(select(PipelineEntry).where(PipelineEntry.stage.in_(OPEN_STAGES))).all():
        o = p.opportunity
        n = _days_left(o.response_deadline)
        if n is not None and 0 <= n <= DUE_WITHIN_DAYS:
            due.append({"id": o.id, "title": o.title, "solicitation_number": o.solicitation_number, "due": o.response_deadline,
                        "days_left": n, "stage": p.stage, "url": o.url})
    due.sort(key=lambda r: r["days_left"])

    changes = []
    for c, o in db.execute(select(OpportunityChange, Opportunity).join(Opportunity, Opportunity.id == OpportunityChange.opportunity_id)
                           .where(OpportunityChange.seen.is_(False)).order_by(OpportunityChange.detected_at.desc())).all():
        changes.append({"id": c.id, "opportunity_id": o.id, "title": o.title, "solicitation_number": o.solicitation_number,
                        "field": c.field, "old": c.old, "new": c.new,
                        "detected_at": c.detected_at.strftime("%Y-%m-%d") if c.detected_at else ""})

    try:
        from .crm_api import open_follow_ups
        follow_ups = open_follow_ups(db, 0)
    except Exception:  # noqa: BLE001
        follow_ups = []

    alerts = module_alerts(db)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "date_label": datetime.now().strftime("%B %d, %Y"),
        "days": days, "company": profile.name or "", "app_url": app_url(),
        "new_opportunities": new, "due_soon": due, "changes": changes, "follow_ups": follow_ups, "alerts": alerts,
        "counts": {"new": len(new), "due": len(due), "changes": len(changes), "follow_ups": len(follow_ups), "alerts": len(alerts)},
    }


def total_items(d: dict) -> int:
    return sum(d["counts"].values())


def subject(d: dict) -> str:
    c = d["counts"]
    bits = []
    if c["new"]:
        bits.append(f"{c['new']} new")
    if c["due"]:
        bits.append(f"{c['due']} due this week")
    if c["changes"]:
        bits.append(f"{c['changes']} amendment change{'s' if c['changes'] != 1 else ''}")
    if c["follow_ups"]:
        bits.append(f"{c['follow_ups']} follow-up{'s' if c['follow_ups'] != 1 else ''}")
    if c["alerts"]:
        bits.append(f"{c['alerts']} alert{'s' if c['alerts'] != 1 else ''}")
    return "GovBid Pro digest: " + (", ".join(bits) if bits else "nothing new")


def _period(d: dict) -> str:
    return "the last day" if d["days"] == 1 else f"the last {d['days']} days"


# ------------------------------------------------------------------ plain text
def render_text(d: dict) -> str:
    base = d["app_url"]
    L = [f"GovBid Pro digest, {d['date_label']}", f"Covers {_period(d)}.", ""]

    L.append(f"New matching opportunities ({len(d['new_opportunities'])})")
    if not d["new_opportunities"]:
        L.append("  None.")
    for o in d["new_opportunities"]:
        score = f"score {o['score']} ({o['recommendation']})" if o["score"] is not None else "not scored"
        L.append(f"  - {o['title']} | {o['eligibility_label']} | {score}")
        L.append(f"    {o['solicitation_number'] or 'n/a'} | {(o['agency'] or '')[:60]} | due {o['due'] or 'n/a'}")
        if o.get("jcp_note"):
            L.append(f"    {o['jcp_note']}")
        L.append(f"    {base}/opportunities/{o['id']}")
    L.append("")

    L.append(f"Due within {DUE_WITHIN_DAYS} days ({len(d['due_soon'])})")
    if not d["due_soon"]:
        L.append("  None.")
    for o in d["due_soon"]:
        when = "today" if o["days_left"] == 0 else f"in {o['days_left']} day{'s' if o['days_left'] != 1 else ''}"
        L.append(f"  - {o['title']} | {o['stage']} | due {when} ({o['due']})")
        L.append(f"    {base}/opportunities/{o['id']}")
    L.append("")

    L.append(f"Amendment changes not yet reviewed ({len(d['changes'])})")
    if not d["changes"]:
        L.append("  None.")
    for c in d["changes"]:
        L.append(f"  - {c['title'][:70]}: {c['field']}: {c['old'][:60]} -> {c['new'][:60]}")
    L.append("")

    L.append(f"Follow-ups due ({len(d['follow_ups'])})")
    if not d["follow_ups"]:
        L.append("  None.")
    for f in d["follow_ups"]:
        tag = "OVERDUE " if f.get("overdue") else ""
        L.append(f"  - {tag}{f['follow_up_date']} {f['organization']}: {f.get('next_step') or f.get('summary') or ''}".rstrip())
    L.append("")

    if d["alerts"]:
        L.append(f"Alerts ({len(d['alerts'])})")
        for a in d["alerts"]:
            L.append(f"  - [{a['source']}] {a['text']}")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


# ------------------------------------------------------------------ HTML (inline styles only, for email clients)
_C = {"ink": "#1f2933", "ink2": "#52606d", "ink3": "#7b8794", "line": "#e4e0d8", "accent": "#2f5d8a", "bg": "#f6f4ef",
      "ok": "#2d6a4f", "okbg": "#e3f1e8", "wait": "#8a5a00", "waitbg": "#fff1d6", "warn": "#b5442c"}
_TD = f"padding:8px 10px;border-bottom:1px solid {_C['line']};vertical-align:top;font-size:14px;color:{_C['ink']};"
_TH = f"padding:6px 10px;border-bottom:1px solid {_C['line']};text-align:left;font-size:12px;color:{_C['ink2']};font-weight:600;"


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _link(href: str, label: str) -> str:
    return f'<a href="{_e(href)}" style="color:{_C["accent"]};text-decoration:none;">{_e(label)}</a>'


def _badge(label: str, fg: str, bg: str) -> str:
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;'
            f'background:{bg};color:{fg};white-space:nowrap;">{_e(label)}</span>')


def _section(title: str, count: int, inner: str) -> str:
    return (f'<h2 style="font-size:16px;margin:24px 0 8px;color:{_C["ink"]};">{_e(title)} '
            f'<span style="color:{_C["ink3"]};font-weight:normal;">({count})</span></h2>{inner}')


def _empty() -> str:
    return f'<p style="margin:0;color:{_C["ink3"]};font-size:14px;">None.</p>'


def _table(head: list[str], rows: list[str]) -> str:
    th = "".join(f'<th style="{_TH}">{_e(h)}</th>' for h in head)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">'
            f"<tr>{th}</tr>{''.join(rows)}</table>")


def render_html(d: dict) -> str:
    base = d["app_url"]
    parts = []

    rows = []
    for o in d["new_opportunities"]:
        elig = _badge(o["eligibility_label"], _C["ok"], _C["okbg"]) if o["eligibility"] == "eligible_now" else _badge(o["eligibility_label"], _C["wait"], _C["waitbg"])
        score = f'<b>{_e(o["score"])}</b><br><span style="color:{_C["ink2"]};font-size:12px;">{_e(o["recommendation"])}</span>' if o["score"] is not None else "n/a"
        jcp = f'<br><span style="color:{_C["warn"]};font-size:12px;">{_e(o["jcp_note"])}</span>' if o.get("jcp_note") else ""
        sam = f' &middot; {_link(o["url"], "SAM.gov")}' if o.get("url") else ""
        link = _link(base + "/opportunities/" + str(o["id"]), o["title"] or "(untitled)")
        rows.append(f'<tr><td style="{_TD}">{link}'
                    f'<br><span style="color:{_C["ink2"]};font-size:12px;">{_e(o["solicitation_number"])} &middot; {_e((o["agency"] or "")[:60])}{sam}</span>{jcp}</td>'
                    f'<td style="{_TD}">{elig}</td><td style="{_TD}text-align:center;">{score}</td>'
                    f'<td style="{_TD}white-space:nowrap;">{_e(o["due"] or "n/a")}</td></tr>')
    parts.append(_section("New matching opportunities", len(rows), _table(["Opportunity", "Eligibility", "Bid score", "Due"], rows) if rows else _empty()))

    rows = []
    for o in d["due_soon"]:
        when = "today" if o["days_left"] == 0 else f'{o["days_left"]} day{"s" if o["days_left"] != 1 else ""}'
        color = _C["warn"] if o["days_left"] <= 2 else _C["ink"]
        link = _link(base + "/opportunities/" + str(o["id"]), o["title"] or "(untitled)")
        rows.append(f'<tr><td style="{_TD}">{link}</td>'
                    f'<td style="{_TD}">{_e(o["stage"])}</td><td style="{_TD}color:{color};font-weight:600;white-space:nowrap;">{_e(when)}</td></tr>')
    parts.append(_section(f"Due within {DUE_WITHIN_DAYS} days", len(rows), _table(["Opportunity", "Stage", "Due in"], rows) if rows else _empty()))

    rows = []
    for c in d["changes"]:
        link = _link(base + "/opportunities/" + str(c["opportunity_id"]), c["title"] or "(untitled)")
        rows.append(f'<tr><td style="{_TD}">{link}</td>'
                    f'<td style="{_TD}">{_e(c["field"])}</td>'
                    f'<td style="{_TD}font-size:13px;"><span style="color:{_C["ink3"]};">{_e(c["old"][:80])}</span> &rarr; {_e(c["new"][:80])}</td></tr>')
    parts.append(_section("Amendment changes not yet reviewed", len(rows), _table(["Opportunity", "Change", "Old to new"], rows) if rows else _empty()))

    rows = []
    for f in d["follow_ups"]:
        date_cell = f'<span style="color:{_C["warn"]};font-weight:600;">{_e(f["follow_up_date"])} overdue</span>' if f.get("overdue") else _e(f["follow_up_date"])
        rows.append(f'<tr><td style="{_TD}white-space:nowrap;">{date_cell}</td>'
                    f'<td style="{_TD}">{_link(base + "/contacts?id=" + str(f["organization_id"]), f["organization"])}</td>'
                    f'<td style="{_TD}">{_e(f.get("next_step") or f.get("summary") or "")}</td></tr>')
    parts.append(_section("Follow-ups due", len(rows), _table(["Date", "Organization", "Next step"], rows) if rows else _empty()))

    if d["alerts"]:
        items = "".join(f'<li style="margin:0 0 6px;font-size:14px;color:{_C["ink"]};">'
                        f'<span style="color:{_C["ink3"]};font-size:12px;">{_e(a["source"])}</span> {_e(a["text"])}</li>' for a in d["alerts"])
        parts.append(_section("Alerts", len(d["alerts"]), f'<ul style="margin:0;padding-left:18px;">{items}</ul>'))

    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_e(subject(d))}</title></head>'
        f'<body style="margin:0;padding:0;background:{_C["bg"]};">'
        f'<div style="max-width:720px;margin:0 auto;padding:24px 16px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;">'
        f'<div style="background:#ffffff;border:1px solid {_C["line"]};border-radius:8px;padding:20px 22px;">'
        f'<h1 style="font-size:20px;margin:0 0 4px;color:{_C["ink"]};">GovBid Pro digest</h1>'
        f'<p style="margin:0;color:{_C["ink2"]};font-size:14px;">{_e(d["date_label"])} &middot; covers {_e(_period(d))}'
        f'{(" &middot; " + _e(d["company"])) if d.get("company") else ""}</p>'
        f'{"".join(parts)}'
        f'<p style="margin:24px 0 0;font-size:12px;color:{_C["ink3"]};">Open {_link(base, "GovBid Pro")} for details. '
        f'Bid scores are a guide for where to spend proposal time, not a verdict.</p>'
        '</div></div></body></html>'
    )
