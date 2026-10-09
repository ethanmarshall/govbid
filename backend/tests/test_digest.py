"""Daily digest: content of the text and HTML versions, module alerts, CLI and preview endpoint."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import cli, digest
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Opportunity, OpportunityChange, PipelineEntry
from app.models_crm import Interaction, Organization
from app.models_sar import SourceApproval
from app.services import get_profile


@pytest.fixture(scope="module")
def seeded():
    init_db()
    db = SessionLocal()
    prof = get_profile(db)
    saved = (dict(prof.certifications or {}), dict(prof.small_under_naics or {}))
    prof.certifications = {**(prof.certifications or {}), "SDVOSB": "pending"}
    prof.small_under_naics = {**(prof.small_under_naics or {}), "336413": True}
    now = datetime.utcnow()
    soon = (date.today() + timedelta(days=3)).isoformat()
    later = (date.today() + timedelta(days=30)).isoformat()
    open_now = Opportunity(source="manual", external_id="dg-1", title="Digest open buy <fittings>", solicitation_number="DG-001",
                           agency="DLA Land and Maritime", set_aside_code="", response_deadline=later, fetched_at=now)
    vet = Opportunity(source="manual", external_id="dg-2", title="Digest veteran set-aside panel", solicitation_number="DG-002",
                      agency="NAVSEA", set_aside_code="SDVOSBC", naics="336413", response_deadline=later, fetched_at=now)
    old = Opportunity(source="manual", external_id="dg-3", title="Digest old notice", solicitation_number="DG-003",
                      fetched_at=now - timedelta(days=10))
    due = Opportunity(source="manual", external_id="dg-4", title="Digest due this week", solicitation_number="DG-004",
                      response_deadline=soon, fetched_at=now - timedelta(days=10))
    db.add_all([open_now, vet, old, due])
    db.flush()
    db.add(PipelineEntry(opportunity_id=due.id, stage="bidding"))
    db.add(OpportunityChange(opportunity_id=due.id, field="Response deadline", old="2026-01-01", new=soon))
    db.add(OpportunityChange(opportunity_id=due.id, field="Title", old="a", new="b", seen=True))
    org = Organization(name="Digest Prime Co", kind="prime")
    db.add(org)
    db.flush()
    db.add(Interaction(organization_id=org.id, summary="Met at industry day", next_step="Send capability statement",
                       follow_up_date=(date.today() - timedelta(days=1)).isoformat()))
    db.add(SourceApproval(nsn="5340-01-666-0001", niin="016660001", status="under_review", dla_activity="Aviation",
                          submitted_date=(date.today() - timedelta(days=400)).isoformat()))
    db.commit()
    ids = {"open": open_now.id, "vet": vet.id, "old": old.id, "due": due.id, "org": org.id}
    yield ids
    prof = get_profile(db)
    prof.certifications, prof.small_under_naics = saved
    for s in db.query(SourceApproval).filter(SourceApproval.nsn == "5340-01-666-0001").all():
        db.delete(s)
    db.commit()
    db.close()


def test_build_digest_sections(seeded):
    db = SessionLocal()
    try:
        d = digest.build_digest(db, days=1)
    finally:
        db.close()
    new = {o["id"]: o for o in d["new_opportunities"]}
    assert seeded["open"] in new and seeded["vet"] in new and seeded["old"] not in new
    assert new[seeded["open"]]["eligibility"] == "eligible_now"
    assert new[seeded["vet"]]["eligibility"] == "eligible_once_certified"
    assert isinstance(new[seeded["open"]]["score"], int) and new[seeded["open"]]["recommendation"]
    # eligible-now items are listed before eligible-once-certified ones
    order = [o["id"] for o in d["new_opportunities"]]
    assert order.index(seeded["open"]) < order.index(seeded["vet"])

    due = {o["id"]: o for o in d["due_soon"]}
    assert due[seeded["due"]]["days_left"] == 3
    fields = [c["field"] for c in d["changes"] if c["opportunity_id"] == seeded["due"]]
    assert fields == ["Response deadline"]  # the seen change is left out
    assert any(f["organization"] == "Digest Prime Co" and f["overdue"] for f in d["follow_ups"])
    assert any(a["source"] == "sar" and "5340-01-666-0001" in a["text"] for a in d["alerts"])


def test_text_and_html(seeded):
    db = SessionLocal()
    try:
        d = digest.build_digest(db, days=1)
    finally:
        db.close()
    t = digest.render_text(d)
    assert "New matching opportunities" in t and "Digest open buy <fittings>" in t
    assert "Eligible once certified" in t and "Due within 7 days" in t and "due in 3 days" in t
    assert "Response deadline" in t and "OVERDUE" in t and "Send capability statement" in t
    assert f"/opportunities/{seeded['open']}" in t
    assert "\u2014" not in t  # no em dashes

    h = digest.render_html(d)
    assert h.startswith("<!doctype html>") and "<style" not in h and "class=" not in h
    assert "Digest open buy &lt;fittings&gt;" in h  # escaped
    assert f"/opportunities/{seeded['due']}" in h and f"/contacts?id={seeded['org']}" in h
    assert "Alerts" in h and "5340-01-666-0001" in h
    assert digest.subject(d).startswith("GovBid Pro digest: ")


def test_module_alerts_skip_missing_and_broken():
    db = SessionLocal()
    try:
        assert digest.module_alerts(db, ["does_not_exist_api"]) == []
        assert isinstance(digest.module_alerts(db), list)
    finally:
        db.close()


def test_preview_endpoint_and_cli(seeded, capsys, monkeypatch):
    with TestClient(app) as c:
        r = c.get("/api/search/digest-preview", params={"days": 1})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert "GovBid Pro digest" in r.text and "Digest veteran set-aside panel" in r.text

    monkeypatch.setattr("sys.argv", ["govbid", "digest", "--days", "1"])
    cli.main()
    out = capsys.readouterr().out
    assert "GovBid Pro digest" in out and "Digest due this week" in out

    sent = {}

    def fake_send(subject, text_body, html_body=None):
        sent.update(subject=subject, text=text_body, html=html_body)
        return "me@example.com"

    calls = []
    monkeypatch.setattr(cli, "send_email", fake_send)
    monkeypatch.setattr(cli, "cmd_watch", lambda args: calls.append(args.max))
    monkeypatch.setattr("sys.argv", ["govbid", "digest", "--days", "1", "--email", "--watch", "--max", "5"])
    cli.main()
    assert calls == [5]
    assert sent["subject"].startswith("GovBid Pro digest") and "<html>" in sent["html"] and "Digest due this week" in sent["text"]
    assert "Digest emailed to me@example.com" in capsys.readouterr().out
