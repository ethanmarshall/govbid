"""Bid score, JCP detection, amendment watch, calendar feed, make-or-buy and the column migration."""
import json
from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import bidding, pricing
from app.main import app


def _opp(c, **kw):
    body = {"title": "Trainer power distribution panel", "solicitation_number": kw.pop("sol", "N0000-26-Q-0001"),
            "agency": "NAVSEA", "set_aside_code": "SDVOSBC", "naics": "335314",
            "response_deadline": (date.today() + timedelta(days=20)).isoformat(),
            "description": "Build a power distribution panel per MIL-STD-130N marking.", **kw}
    oid = c.post("/api/opportunities", json=body).json()["id"]
    return oid


def test_export_control_detection():
    t = "Drawings are Distribution Statement D. WARNING - This document contains technical data whose export is restricted by the ITAR."
    ec = bidding.export_control(t)
    assert ec["flagged"] and {"distribution", "itar", "export"} <= set(ec["hits"])
    assert not bidding.export_control("Drawings are in cFolders.")["flagged"]
    assert not bidding.export_control("Distribution Statement A: approved for public release.")["flagged"]


def test_profile_jcp_and_opportunity_flags_and_standards():
    with TestClient(app) as c:
        prof = c.get("/api/profile").json()
        prof.update({"name": "Test LLC", "naics_codes": ["335314"], "certifications": {"SB": "certified", "SDVOSB": "certified"},
                     "small_under_naics": {"335314": True}, "sam_status": "active", "jcp_status": "none"})
        r = c.put("/api/profile", json=prof).json()
        assert r["jcp_status"] == "none" and "jcp_expiration" in r
        oid = _opp(c, sol="N0000-26-Q-0100", description="Panel per MIL-STD-130N and MIL-DTL-5541F. Drawings are Distribution Statement D, export controlled; JCP certification required.")
        d = c.post(f"/api/opportunities/{oid}/analyze").json()
        assert d["export_control"]["flagged"] and "JCP" in d["jcp_note"]
        assert any("JCP" in r for r in d["analysis"]["breakdown"]["red_flags"])
        lst = c.get("/api/opportunities", params={"my_naics_only": "false", "limit": 200}).json()["results"]
        assert next(x for x in lst if x["id"] == oid)["export_controlled"] is True
        std = c.get("/api/standards/MIL-STD-130").json()
        assert any(ci["opportunity_id"] == oid for ci in std["citations"])
        assert any(s["base_id"] == "MIL-STD-130" for s in d["standards_check"])
        # the matrix export still works with the new breakdown field
        assert c.get(f"/api/opportunities/{oid}/matrix.xlsx").status_code == 200
        prof["jcp_status"] = "approved"
        c.put("/api/profile", json=prof)
        assert c.get(f"/api/opportunities/{oid}").json()["jcp_note"] is None


def test_bid_score_shape_and_order():
    with TestClient(app) as c:
        prof = c.get("/api/profile").json()
        prof.update({"naics_codes": ["335314"], "certifications": {"SB": "certified", "SDVOSB": "certified"}, "small_under_naics": {"335314": True}, "sam_status": "active"})
        c.put("/api/profile", json=prof)
        good = _opp(c, sol="S-GOOD", set_aside_code="SDVOSBS")
        bad = _opp(c, sol="S-BAD", set_aside_code="", naics="236220", response_deadline=(date.today() + timedelta(days=1)).isoformat())
        g = c.get(f"/api/opportunities/{good}/score").json()
        b = c.get(f"/api/opportunities/{bad}/score").json()
        assert g["score"] > b["score"]
        assert {f["factor"] for f in g["factors"]} == {"Eligibility", "Fit", "Time", "Competition", "Size", "Price", "Risk"}
        assert sum(f["out_of"] for f in g["factors"]) == 100
        assert 0 <= b["score"] <= 100 and g["recommendation"].startswith(("Bid", "Consider"))


def test_amendment_watch(monkeypatch):
    from app.connectors import sam_gov
    with TestClient(app) as c:
        oid = _opp(c, sol="W912-26-R-7777")
        c.put(f"/api/opportunities/{oid}/pipeline", json={"stage": "bidding"})
        # make it look like a SAM record
        from app.db import SessionLocal
        from app.models import Opportunity
        with SessionLocal() as db:
            o = db.get(Opportunity, oid)
            o.source, o.external_id, o.attachments = "sam", "abc111", ["https://x/a.pdf"]
            db.commit()
        new_deadline = (date.today() + timedelta(days=30)).isoformat() + "T14:00:00-04:00"
        seen = []

        def handler(req):
            seen.append(dict(req.url.params))
            return httpx.Response(200, json={"totalRecords": 2, "opportunitiesData": [
                {"noticeId": "abc111", "solicitationNumber": "W912-26-R-7777", "title": "Trainer power distribution panel", "postedDate": "2026-09-01", "type": "Solicitation"},
                {"noticeId": "abc222", "solicitationNumber": "W912-26-R-7777", "title": "Trainer power distribution panel", "postedDate": "2026-10-01",
                 "type": "Solicitation", "responseDeadLine": new_deadline, "resourceLinks": ["https://x/a.pdf", "https://x/amendment1.pdf"]},
            ]})
        real = httpx.Client
        monkeypatch.setattr(sam_gov.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
        r = c.post("/api/watch/check").json()
        assert r["checked"] >= 1 and any(q.get("solnum") == "W912-26-R-7777" for q in seen)
        fields = {ch["field"] for ch in r["changes"] if ch["opportunity_id"] == oid}
        assert {"Response deadline", "Attachments", "New notice version (amendment)"} <= fields
        w = c.get("/api/watch", params={"unseen_only": True}).json()
        assert w["unseen"] >= 3
        assert c.get("/api/dashboard").json()["changes_unseen"] >= 3
        # second run finds nothing new
        assert not [ch for ch in c.post("/api/watch/check").json()["changes"] if ch["opportunity_id"] == oid]
        c.post("/api/watch/seen", params={"opportunity_id": oid})
        assert all(ch["seen"] for ch in c.get(f"/api/opportunities/{oid}").json()["changes"])


def test_calendar_feed():
    with TestClient(app) as c:
        oid = _opp(c, sol="CAL-1", title="Calendar, test; panel")
        c.put(f"/api/opportunities/{oid}/pipeline", json={"stage": "tracking"})
        prof = c.get("/api/profile").json()
        prof["jcp_expiration"] = (date.today() + timedelta(days=90)).isoformat()
        c.put("/api/profile", json=prof)
        r = c.get("/api/calendar.ics")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
        body = r.text
        assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
        assert "SUMMARY:DUE: Calendar\\, test\\; panel" in body
        assert "JCP certification expires" in body
        assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
        assert any(e["uid"] == f"opp-{oid}" for e in c.get("/api/calendar").json())


def test_make_or_buy_and_nonmanufacturer_rule():
    with TestClient(app) as c:
        oid = _opp(c, sol="MOB-1", set_aside_code="SDVOSBC", naics="332710")
        spec = dict(pricing.EXAMPLE_SPEC, quantities=[10, 100])
        q = c.post("/api/pricing/quotes", json={"spec": spec, "opportunity_id": oid, "quoted_quantity": 100}).json()
        shop = c.post("/api/crm/organizations", json={"name": "Small Shop Machining", "kind": "vendor"}).json()
        c.put(f"/api/crm/organizations/{shop['id']}", json={"business_types": {"SB": True}, "is_manufacturer": True})
        r = c.post(f"/api/pricing/quotes/{q['id']}/vendor-quotes", json={"organization_id": shop["id"], "prices": [{"quantity": 10, "unit_price": 30}, {"quantity": 100, "unit_price": 12}], "lead_days": 15})
        assert r.status_code == 200, r.text
        d = r.json()
        row10, row100 = d["comparison"]
        assert row100["best_buy"]["vendor_unit"] == 12 and row10["best_buy"]["vendor_unit"] == 30
        assert row100["best_buy"]["unit_price"] > 12  # markup and handling on top of the vendor price
        nmr = d["nmr"][str(d["vendor_quotes"][0]["id"])]  # JSON object keys are strings
        assert any(n["level"] in ("ok", "info") for n in nmr)
        # a large vendor gets a clear warning
        r = c.post(f"/api/pricing/quotes/{q['id']}/vendor-quotes", json={"vendor_name": "Big Corp", "prices": [{"quantity": 1, "unit_price": 5}]}).json()
        big = r["vendor_quotes"][-1]["id"]
        assert any(n["level"] == "warn" for n in r["nmr"][str(big)])
        assert c.post(f"/api/pricing/quotes/{q['id']}/vendor-quotes", json={"vendor_name": "", "prices": [{"quantity": 1, "unit_price": 5}]}).status_code == 400
        assert c.delete(f"/api/pricing/quotes/{q['id']}/vendor-quotes/{big}").status_code == 200
        assert c.delete(f"/api/pricing/quotes/{q['id']}").status_code == 200


def test_nmr_exemption_under_sat():
    from types import SimpleNamespace
    from app.make_or_buy import nonmanufacturer_check
    opp = SimpleNamespace(set_aside_code="SBA", naics="332710", estimated_value=80_000)
    assert nonmanufacturer_check(opp, None, None)[0]["level"] == "ok"
    opp.estimated_value = 2_000_000
    assert any(n["level"] == "warn" for n in nonmanufacturer_check(opp, None, None))
    opp.set_aside_code = ""
    assert nonmanufacturer_check(opp, None, None)[0]["text"].startswith("Not a small business set-aside")


def test_won_quote_feeds_nsn_history():
    with TestClient(app) as c:
        spec = dict(pricing.EXAMPLE_SPEC, nsn="5340-01-555-1234", quantities=[25])
        q = c.post("/api/pricing/quotes", json={"spec": spec, "quoted_quantity": 25, "status": "won"}).json()
        h = c.get("/api/nsn/5340-01-555-1234/history").json()
        assert any(r["source"] == "quote_won" for r in h["records"])
        c.delete(f"/api/pricing/quotes/{q['id']}")


def test_migration_adds_missing_columns(tmp_path, monkeypatch):
    from app import db as dbmod
    url = f"sqlite:///{tmp_path}/old.db"
    eng = create_engine(url)
    with eng.begin() as conn:  # an older database: profile table without the JCP columns
        conn.execute(text("CREATE TABLE company_profile (id INTEGER PRIMARY KEY, name VARCHAR(200))"))
        conn.execute(text("INSERT INTO company_profile (id, name) VALUES (1, 'Old Co')"))
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.init_db()
    with eng.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(company_profile)"))}
        row = conn.execute(text("SELECT name, jcp_status, naics_codes FROM company_profile")).one()
    assert {"jcp_status", "jcp_cert_number", "naics_codes"} <= cols
    assert row[0] == "Old Co" and row[1] == "none" and json.loads(row[2]) == []


def test_mcp_new_tools(tmp_path):
    import anyio
    from pathlib import Path
    from app import mcp_server

    fix = Path(__file__).parent / "fixtures" / "drawings" / "bracket_6061.pdf"

    async def run():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        assert {"read_drawing_pdf", "nsn_award_history", "opportunity_bid_score", "add_vendor_quote"} <= names
        d = json.loads((await mcp_server.mcp.call_tool("read_drawing_pdf", {"file_path": str(fix)})).content[0].text)
        assert d["text_found"] and "quote_options" in d
        h = json.loads((await mcp_server.mcp.call_tool("nsn_award_history", {"nsn": "5340-01-555-9999"})).content[0].text)
        assert h["stats"]["count"] == 0
        sc = json.loads((await mcp_server.mcp.call_tool("opportunity_bid_score", {"opportunity_id": 999999})).content[0].text)
        assert "error" in sc

    anyio.run(run)
