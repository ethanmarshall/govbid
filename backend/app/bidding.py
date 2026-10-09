"""Bid decision helpers: export-control (JCP) detection, bid/no-bid score, amendment watch and calendar feed."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .eligibility import evaluate
from .models import Opportunity, OpportunityChange, Package, PartQuote, PipelineEntry

SAT = 350_000  # simplified acquisition threshold (FAR 2.101, Oct 2025)
MICRO = 15_000  # micro-purchase threshold (FAR 2.101, Oct 2025)
SMALL_BUSINESS_SET_ASIDES = {"SBA", "SBP", "SDVOSBC", "SDVOSBS", "WOSB", "WOSBSS", "EDWOSB", "EDWOSBSS", "HZC", "HZS", "8A", "8AN", "VSA", "VSS"}
OPEN_STAGES = ("tracking", "evaluating", "bidding")

# ------------------------------------------------------------------ export control / JCP
EXPORT_PATTERNS = [
    ("jcp", r"\bJ(?:oint)?\s*C(?:ertification)?\s*P(?:rogram)?\b|\bJCP\b"),
    ("dd2345", r"\bDD\s*(?:Form\s*)?2345\b"),
    ("itar", r"\bITAR\b|International Traffic in Arms"),
    ("ear", r"\bExport Administration Regulations\b|\bEAR99\b"),
    ("export", r"export[- ]controlled|whose export is restricted|export control(?:led)? (?:data|information|technical data)"),
    ("distribution", r"\bDistribution\s+Statement\s+[B-F]\b|\bDISTRIBUTION\s+[B-F]\b"),
    ("mctd", r"militarily critical technical data"),
    ("cfolders", r"\bcFolders\b"),
]


def export_control(text: str) -> dict:
    """Find signs that the technical data is export controlled, so a JCP certification (DD Form 2345) is needed."""
    hits, snippets = [], []
    for key, pat in EXPORT_PATTERNS:
        m = re.search(pat, text or "", re.I)
        if m:
            hits.append(key)
            a, b = max(m.start() - 70, 0), min(m.end() + 70, len(text))
            snippets.append(re.sub(r"\s+", " ", text[a:b]).strip())
    # "cfolders" alone only means drawings are on DLA's site; it matters when paired with a control marking
    flagged = any(h != "cfolders" for h in hits)
    return {"flagged": flagged, "hits": hits, "snippets": snippets[:4]}


def jcp_status_note(profile, flagged: bool) -> str | None:
    if not flagged:
        return None
    status = getattr(profile, "jcp_status", "none") or "none"
    exp = getattr(profile, "jcp_expiration", "") or ""
    if status == "approved":
        if exp and exp < date.today().isoformat():
            return f"Export-controlled data, and your JCP certification expired {exp}. Renew it (DD Form 2345) before requesting drawings."
        return None
    if status == "applied":
        return "Export-controlled data: your JCP application is pending, so you cannot download the drawings yet."
    return "Export-controlled data: you need an approved JCP certification (DD Form 2345) to get the drawings. Apply now; approval takes weeks."


def opportunity_text(o: Opportunity) -> str:
    parts = [o.title or "", re.sub(r"<[^>]+>", " ", o.description or "")]
    if o.analysis and o.analysis.breakdown:
        b = o.analysis.breakdown
        ec = b.get("export_control") or {}
        parts += ec.get("snippets", [])
        parts.append(b.get("scope", "") if isinstance(b.get("scope"), str) else "")
    return "\n".join(parts)


def export_flags_for(o: Opportunity) -> dict:
    stored = ((o.analysis.breakdown or {}).get("export_control") if o.analysis else None) or {}
    live = export_control(opportunity_text(o))
    hits = sorted(set(live["hits"]) | set(stored.get("hits", [])))
    return {"flagged": bool(live["flagged"] or stored.get("flagged")), "hits": hits,
            "snippets": (stored.get("snippets") or []) + [s for s in live["snippets"] if s not in (stored.get("snippets") or [])]}


# ------------------------------------------------------------------ bid / no-bid score
def _days_left(deadline: str) -> int | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", deadline or "")
    if m:
        return (date(int(m[1]), int(m[2]), int(m[3])) - date.today()).days
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", deadline or "")
    if m:
        y = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
        try:
            return (date(y, int(m[1]), int(m[2])) - date.today()).days
        except ValueError:
            return None
    return None


def bid_score(db: Session, o: Opportunity, profile, *, with_past_performance: bool = True) -> dict:
    """0 to 100 with the reason for every point. A guide for where to spend proposal time, not a verdict."""
    factors: list[dict] = []

    def add(name: str, points: float, out_of: float, note: str) -> None:
        factors.append({"factor": name, "points": round(points, 1), "out_of": out_of, "note": note})

    elig = evaluate(o.set_aside_code, o.naics, profile)
    if elig.status == "eligible_now":
        add("Eligibility", 25, 25, "You can bid today.")
    elif elig.status == "eligible_once_certified":
        add("Eligibility", 12, 25, "Only after your certification is approved. Check the timing against the due date.")
    else:
        add("Eligibility", 0, 25, elig.reason)

    # Fit: NAICS, keywords and past performance
    text = opportunity_text(o)
    low = text.lower()
    fit = 0.0
    notes = []
    if o.naics and o.naics in (profile.naics_codes or []):
        fit += 8
        notes.append(f"NAICS {o.naics} is on your profile")
    kw = [k for k in (profile.keywords or []) if k and k.lower() in low]
    if kw:
        fit += min(len(kw) * 2, 6)
        notes.append("keywords: " + ", ".join(kw[:4]))
    if with_past_performance:
        try:
            from .past_performance_api import match_past_performance
            pp = match_past_performance(db, text, limit=2)
        except Exception:  # noqa: BLE001
            pp = []
        if pp:
            fit += min(6, 2 + pp[0]["score"] / 3)
            notes.append("past performance: " + pp[0]["title"])
    add("Fit", min(fit, 20), 20, "; ".join(notes) or "Nothing on your profile or past performance matches yet.")

    # Time
    days = _days_left(o.response_deadline)
    nt = (o.notice_type or "").lower()
    if "sources sought" in nt or "presolicitation" in nt or "special notice" in nt:
        add("Time", 12, 15, "Not a bid yet: answering is cheap and puts you on the buyer's radar.")
    elif days is None:
        add("Time", 8, 15, "No due date found.")
    elif days < 0:
        add("Time", 0, 15, "Past due.")
    elif days < 3:
        add("Time", 2, 15, f"{days} day(s) left.")
    elif days < 7:
        add("Time", 6, 15, f"{days} days left.")
    elif days < 14:
        add("Time", 11, 15, f"{days} days left.")
    else:
        add("Time", 15, 15, f"{days} days left.")

    # Competition
    sa = (o.set_aside_code or "").upper()
    comp = {"SDVOSBS": (15, "SDVOSB sole source."), "SDVOSBC": (13, "SDVOSB set-aside: a small field."),
            "VSS": (14, "VA veteran sole source."), "VSA": (12, "VA veteran set-aside.")}.get(sa)
    if comp is None:
        comp = (10, "Small business set-aside.") if sa in SMALL_BUSINESS_SET_ASIDES else (4, "Full and open: you compete with everyone.")
    add("Competition", comp[0], 15, comp[1])

    # Size of the job
    v = o.estimated_value
    if v is None:
        add("Size", 5, 10, "No estimated value given.")
    elif v <= SAT:
        add("Size", 10, 10, "Under the simplified acquisition threshold: simpler buying rules, good for building past performance.")
    elif v <= 2_000_000:
        add("Size", 6, 10, "Mid-size: you will need solid past performance or a teaming partner.")
    else:
        add("Size", 2, 10, "Large: usually needs a team and past performance at this scale.")

    # Price position from a linked part quote
    q = db.scalar(select(PartQuote).where(PartQuote.opportunity_id == o.id).order_by(PartQuote.updated_at.desc()))
    if q and q.quoted_unit_price:
        ref = (q.spec or {}).get("reference_unit_price")
        if not ref and q.nsn:
            try:
                from .nsn_history import reference_price
                ref = reference_price(db, q.nsn)
            except Exception:  # noqa: BLE001
                ref = None
        if ref:
            gap = (q.quoted_unit_price - float(ref)) / float(ref)
            pts = 10 if gap <= 0 else 6 if gap <= 0.10 else 2
            add("Price", pts, 10, f"Your ${q.quoted_unit_price:,.2f} is {gap:+.0%} vs the last award ${float(ref):,.2f}.")
        else:
            add("Price", 5, 10, "Quoted, but no last award price to compare.")
    else:
        add("Price", 5, 10, "No part quote linked.")

    # Risks
    risk = 5.0
    rnotes = []
    flags = export_flags_for(o)
    jcp = jcp_status_note(profile, flags["flagged"])
    if jcp:
        risk -= 4
        rnotes.append("needs JCP")
    if o.analysis:
        reds = (o.analysis.breakdown or {}).get("red_flags") or []
        if reds:
            risk -= min(len(reds), 3)
            rnotes.append(f"{len(reds)} red flag(s) in the analysis")
        clauses = {str(c.get("clause", "")) for c in (o.analysis.breakdown or {}).get("key_clauses") or [] if isinstance(c, dict)}
        if any(c.startswith("252.204-70") for c in clauses):
            rnotes.append("DFARS cyber clauses: check your CMMC level and SPRS score")
            try:
                from .cmmc_api import compute_summary
                s = compute_summary(db)
                if not s.get("last_sprs_submission_date"):
                    risk -= 2
            except Exception:  # noqa: BLE001
                pass
    add("Risk", max(risk, 0), 5, "; ".join(rnotes) or "No red flags found.")

    total = round(sum(f["points"] for f in factors))
    if elig.status == "not_eligible":
        rec = "Not eligible"
    elif total >= 70 and jcp:
        rec = "Bid once JCP is approved"
    elif total >= 70:
        rec = "Bid"
    elif total >= 50:
        rec = "Consider"
    else:
        rec = "Probably pass"
    return {"score": total, "recommendation": rec, "factors": factors, "jcp_note": jcp, "export_control": flags}


# ------------------------------------------------------------------ amendment watch
WATCH_FIELDS = [("title", "Title"), ("response_deadline", "Response deadline"), ("notice_type", "Notice type"),
                ("set_aside_code", "Set-aside"), ("description_url", "Description")]


def watch_candidates(db: Session) -> list[Opportunity]:
    rows = db.scalars(select(Opportunity).join(PipelineEntry).where(PipelineEntry.stage.in_(OPEN_STAGES), Opportunity.source == "sam")).all()
    return [o for o in rows if o.solicitation_number]


def check_amendments(db: Session, *, client=None, api_key: str | None = None, max_requests: int = 20) -> dict:
    """Re-check tracked SAM.gov opportunities by solicitation number and log what changed. One request each."""
    from .connectors import sam_gov

    checked, changes, errors, used = 0, [], [], 0
    for o in watch_candidates(db)[:max_requests]:
        try:
            raw, n = sam_gov.search(days_back=364, solicitation_number=o.solicitation_number, ptypes=["o", "k", "p", "r", "s", "a", "u"],
                                    max_pages=1, client=client, api_key=api_key)
            used += n
        except sam_gov.SamApiError as exc:
            errors.append(str(exc))
            break
        checked += 1
        same = [r for r in raw if (r.get("solicitationNumber") or "").strip().lower() == o.solicitation_number.strip().lower()]
        if not same:
            continue
        latest = max(same, key=lambda r: (r.get("postedDate") or "", r.get("noticeId") or ""))
        rec = sam_gov.normalize(latest)
        found = []
        for f, label in WATCH_FIELDS:
            old, new = (getattr(o, f) or "").strip(), (rec.get(f) or "").strip()
            if new and old != new:
                found.append((label, old, new))
                setattr(o, f, rec[f])
                if f == "description_url":
                    o.description = ""  # reload the new text on next view
        old_att, new_att = set(o.attachments or []), set(rec.get("attachments") or [])
        added = sorted(new_att - old_att)
        if added:
            found.append(("Attachments", f"{len(old_att)} file(s)", f"{len(added)} new file(s)"))
            o.attachments = sorted(old_att | new_att)
        latest_id = rec.get("external_id", "")
        known = (o.raw or {}).get("latest_notice_id") or o.external_id
        if latest_id and latest_id != known:
            label = "Award notice" if "award" in (rec.get("notice_type") or "").lower() else "New notice version (amendment)"
            found.append((label, known, latest_id))
            o.raw = {**(o.raw or {}), "latest_notice_id": latest_id}
            o.url = rec.get("url") or o.url
        for label, old, new in found:
            ch = OpportunityChange(opportunity_id=o.id, field=label, old=str(old)[:2000], new=str(new)[:2000], notice_id=latest_id)
            db.add(ch)
            changes.append({"opportunity_id": o.id, "title": o.title, "field": label, "old": old, "new": new})
    db.commit()
    return {"checked": checked, "requests_used": used, "changes": changes, "errors": errors}


def change_dict(c: OpportunityChange, o: Opportunity | None = None) -> dict:
    return {"id": c.id, "opportunity_id": c.opportunity_id, "title": o.title if o else None,
            "solicitation_number": o.solicitation_number if o else None, "field": c.field, "old": c.old, "new": c.new,
            "detected_at": c.detected_at.isoformat() if c.detected_at else None, "seen": c.seen}


# ------------------------------------------------------------------ calendar feed
def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, b = [], line.encode()
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:  # never split a UTF-8 character
            cut -= 1
        out.append(b[:cut].decode())
        b = b" " + b[cut:]
    out.append(b.decode())
    return "\r\n".join(out)


def _ics_date(s: str) -> date | None:
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        y = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
        try:
            return date(y, int(m[1]), int(m[2]))
        except ValueError:
            return None
    return None


def calendar_events(db: Session, profile) -> list[dict]:
    """Every dated item worth a calendar entry: due dates, package deadlines, follow-ups, renewals, POA&M dates."""
    ev: list[dict] = []
    for p in db.scalars(select(PipelineEntry).where(PipelineEntry.stage.in_(OPEN_STAGES))).all():
        o = p.opportunity
        d = _ics_date(o.response_deadline)
        if d:
            ev.append({"uid": f"opp-{o.id}", "date": d, "summary": f"DUE: {o.title[:90]}",
                       "description": f"{o.solicitation_number} {o.agency}\nStage: {p.stage}\n{o.url}", "url": o.url})
        if o.analysis:
            for i, line in enumerate((o.analysis.breakdown or {}).get("deadlines") or []):
                if "question" in line.lower():
                    m = re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", line)
                    qd = _ics_date(m.group(0)) if m else None
                    if qd:
                        ev.append({"uid": f"oppq-{o.id}-{i}", "date": qd, "summary": f"Questions due: {o.title[:80]}", "description": line, "url": o.url})
    for pk in db.scalars(select(Package).where(Package.status.in_(["draft", "in_review"]))).all():
        d = _ics_date(pk.due_date)
        if d:
            ev.append({"uid": f"pkg-{pk.id}", "date": d, "summary": f"Package due: {pk.name[:90]}", "description": f"Status: {pk.status}", "url": ""})
    try:
        from .crm_api import open_follow_ups
        for f in open_follow_ups(db, None):
            d = _ics_date(f["follow_up_date"])
            if d:
                ev.append({"uid": f"fu-{f['id']}", "date": d, "summary": f"Follow up: {f['organization']}",
                           "description": f"{f.get('next_step') or ''}\n{f.get('summary') or ''}".strip(), "url": ""})
    except Exception:  # noqa: BLE001
        pass
    try:
        from .models_cmmc import CmmcControl  # type: ignore
        for c in db.scalars(select(CmmcControl)).all():
            due = getattr(c, "poam_due", "")
            if due and getattr(c, "status", "") not in ("implemented", "not_applicable"):
                d = _ics_date(due)
                if d:
                    ev.append({"uid": f"poam-{c.framework}-{c.control_id}", "date": d, "summary": f"POA&M due: {c.control_id}", "description": "CMMC / NIST 800-171 plan of action item", "url": ""})
    except Exception:  # noqa: BLE001
        pass
    for label, val, lead in (("SAM.gov registration expires", getattr(profile, "sam_expiration", ""), 60),
                             ("JCP certification expires", getattr(profile, "jcp_expiration", ""), 60)):
        d = _ics_date(val)
        if d:
            ev.append({"uid": f"renew-{label}", "date": d, "summary": label, "description": "Renew before this date.", "url": ""})
            ev.append({"uid": f"renew60-{label}", "date": d - timedelta(days=lead), "summary": f"Start renewal: {label.lower()}",
                       "description": f"{label} on {d.isoformat()}.", "url": ""})
    import importlib
    for mod in ("jobs_api", "quality_api", "finance_api", "sar_api"):
        try:  # each module adds its own dated items; one failing never breaks the feed
            for e in importlib.import_module(f"{__package__}.{mod}").calendar_items(db):
                if isinstance(e.get("date"), date):
                    ev.append({"uid": str(e.get("uid") or f"{mod}-{len(ev)}"), "date": e["date"], "summary": e.get("summary", ""),
                               "description": e.get("description", ""), "url": e.get("url", "")})
        except Exception:  # noqa: BLE001
            pass
    ev.sort(key=lambda e: e["date"])
    return ev


def to_ics(events: list[dict]) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GovBid Pro//Deadlines//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:GovBid Pro deadlines", "REFRESH-INTERVAL;VALUE=DURATION:PT6H"]
    for e in events:
        d = e["date"]
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@govbid-pro", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_ics_escape(e['summary'])}"]
        if e.get("description"):
            lines.append(f"DESCRIPTION:{_ics_escape(e['description'])}")
        if e.get("url"):
            lines.append(f"URL:{e['url']}")
        if e["summary"].startswith("DUE"):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Response due in 3 days", "TRIGGER:-P3D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
