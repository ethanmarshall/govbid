"""Customer quote portal: instant vs estimate vs manual, what customers can and cannot see, limits and the internal review."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import portal
from app.main import app

FIX = Path(__file__).parent / "fixtures"
SECRET_WORDS = ("unit_cost", "margin", "placeholder", "rate", "per_part_lines", "internal", "spec")


@pytest.fixture
def client():
    portal.QUOTE_LIMIT.clear()
    portal.REPRICE_LIMIT.clear()
    portal.SUBMIT_LIMIT.clear()
    with TestClient(app) as c:
        assert c.put("/api/portal/settings", json={"enabled": True, "review_days": 2}).status_code == 200
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


def _quote(c, files, **form):
    data = {"quantity": "1", **{k: str(v) for k, v in form.items()}}
    up = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in files]
    return c.post("/api/public/quote", data=data, files=up or None)


def _no_secrets(payload: dict):
    text = json.dumps(payload).lower()
    for w in SECRET_WORDS:
        assert f'"{w}' not in text, w


def test_closed_until_enabled():
    with TestClient(app) as c:
        c.put("/api/portal/settings", json={"enabled": False})
        portal.QUOTE_LIMIT.clear()
        r = _quote(c, [FIX / "cad" / "machined_block.step"])
        assert r.status_code == 400 and "not open" in r.json()["detail"]
        assert c.get("/api/public/info").json()["enabled"] is False


def test_step_part_is_an_instant_quote_and_reprices(client):
    r = _quote(client, [FIX / "cad" / "machined_block.step"], quantity=1, material="6061-T6 aluminum")
    assert r.status_code == 200, r.text
    q = r.json()
    res = q["result"]
    assert q["ref"].startswith("RQ-") and q["token"] and res["kind"] == "instant"
    assert res["unit_price"] > 0 and res["total"] == pytest.approx(res["unit_price"], abs=0.01) and res["lead_days"] > 0
    _no_secrets(q)
    r60 = client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 60}).json()
    assert r60["result"]["quantity"] == 60 and r60["result"]["unit_price"] < res["unit_price"]
    assert r60["result"]["total"] == pytest.approx(r60["result"]["unit_price"] * 60, abs=0.6)
    # a wrong token sees nothing
    assert client.get(f"/api/public/quote/{q['ref']}?token=nope").status_code == 400


def test_multi_body_step_is_an_estimate_range(client):
    q = _quote(client, [FIX / "cad" / "weldment.step"], quantity=10).json()
    res = q["result"]
    assert res["kind"] == "estimate" and res["unit_low"] < res["unit_high"]
    assert "engineer" in res["message"] and "confirm" in res["message"]
    _no_secrets(q)


def test_unsure_drawing_is_an_estimate_and_confident_drawing_instant(client):
    unsure = _quote(client, [FIX / "drawings" / "shaft_304.pdf"]).json()
    assert unsure["result"]["kind"] == "estimate" and "confirmed by an engineer" in unsure["result"]["items"][0]["note"]
    sure = _quote(client, [FIX / "drawings" / "sheet_cover.pdf"]).json()
    assert sure["result"]["kind"] == "instant"


def test_dxf_needs_thickness_then_prices(client):
    q = _quote(client, [FIX / "flat" / "plate_holes_slot.dxf"]).json()
    assert q["result"]["kind"] == "needs_input"
    r = client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "thickness": 0.125}).json()
    assert r["result"]["kind"] == "instant" and r["result"]["unit_price"] > 0


def test_pcb_files_are_an_estimate(client):
    q = _quote(client, [FIX / "pcb" / "kicad_fab.zip"], quantity=25).json()
    assert q["result"]["kind"] == "estimate" and "Circuit boards" in q["result"]["items"][0]["note"]


def test_export_controlled_is_not_stored(client, tmp_path):
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "itar.pdf"
    c = canvas.Canvas(str(pdf))
    for i, ln in enumerate(["BRACKET, MOUNTING", "MATERIAL: 6061-T6 ALUMINUM", "WARNING - This document contains technical data whose export is restricted",
                            "by the Arms Export Control Act (Title 22, U.S.C., Sec 2751, et seq.)", "DISTRIBUTION STATEMENT D. Distribution authorized to DoD and U.S. DoD contractors only."]):
        c.drawString(40, 700 - 16 * i, ln)
    c.save()
    q = _quote(client, [pdf]).json()
    assert q["export_controlled"] and q["result"]["kind"] == "manual" and "deleted" in q["result"]["message"]
    assert q["files"][0]["removed"]
    req = client.get("/api/portal/requests?include_drafts=true").json()
    rid = next(r["id"] for r in req if r["ref"] == q["ref"])
    assert client.get(f"/api/portal/requests/{rid}/files/0").status_code == 404
    flagged = _quote(client, [FIX / "cad" / "machined_block.step"], export_controlled="true").json()
    assert flagged["files"] == [] and flagged["result"]["kind"] == "manual"


def test_bad_files_and_honeypot(client, tmp_path):
    exe = tmp_path / "virus.exe"
    exe.write_bytes(b"MZ")
    assert _quote(client, [exe]).status_code == 400
    assert client.post("/api/public/quote", data={"quantity": "1", "website": "spam"}).status_code == 400
    assert _quote(client, [FIX / "cad" / "machined_block.step"], quantity=0).status_code == 400


def test_submit_review_and_internal_quotes(client):
    q = _quote(client, [FIX / "cad" / "machined_block.step"], quantity=5).json()
    bad = client.post(f"/api/public/quote/{q['ref']}/submit", json={"token": q["token"], "name": "Pat", "email": "nope", "accept_terms": True})
    assert bad.status_code == 400
    s = client.post(f"/api/public/quote/{q['ref']}/submit", json={"token": q["token"], "name": "Pat Buyer", "company": "Acme",
                                                                  "email": "pat@example.com", "accept_terms": True, "needed_by": "2026-12-01"}).json()
    assert s["submitted"] and s["status"] == "submitted"
    again = client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 9})
    assert again.status_code == 400  # locked once submitted
    lst = client.get("/api/portal/requests").json()
    row = next(r for r in lst if r["ref"] == q["ref"])
    full = client.get(f"/api/portal/requests/{row['id']}").json()
    assert full["internal"]["items"][0]["unit_cost"] is not None  # you see cost and margin, the customer does not
    made = client.post(f"/api/portal/requests/{row['id']}/to-quotes").json()
    assert made["quote_ids"] and "instant" in made["tabs"]
    pq = client.get(f"/api/pricing/quotes/{made['quote_ids'][0]}").json()
    assert pq["quoted_quantity"] == 5 and q["ref"] in pq["notes"]
    assert client.put(f"/api/portal/requests/{row['id']}", json={"status": "confirmed"}).json()["status"] == "confirmed"
    assert client.get(f"/api/public/quote/{q['ref']}?token={q['token']}").json()["status_label"] == "Confirmed"


def test_internal_routes_need_login(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    with TestClient(app) as c:
        assert c.get("/api/portal/requests").status_code == 401
        assert c.get("/api/portal/settings").status_code == 401
        assert c.get("/api/public/info").status_code == 200  # the customer page works without a login


def test_rate_limit(client):
    portal.QUOTE_LIMIT.per_ip, old = 2, portal.QUOTE_LIMIT.per_ip
    try:
        portal.QUOTE_LIMIT.clear()
        codes = [_quote(client, [], notes="hi").status_code for _ in range(3)]
        assert codes[:2] == [200, 200] and codes[2] == 429
    finally:
        portal.QUOTE_LIMIT.per_ip = old
        portal.QUOTE_LIMIT.clear()


def test_site_content_defaults_and_edits(client):
    info = client.get("/api/public/info").json()
    assert info["site"]["capabilities"] and info["site"]["faq"] and info["owner"] is False
    s = client.put("/api/portal/settings", json={"site": {"about": "We build test stands.", "capabilities": [{"title": "Harnesses", "text": "To print"}, {"title": ""}],
                                                          "experience": ["Ten years of panels", "  "]}}).json()
    assert s["site"]["about"] == "We build test stands." and s["site"]["capabilities"] == [{"title": "Harnesses", "text": "To print"}]
    assert s["site"]["experience"] == ["Ten years of panels"] and s["site"]["faq"]  # untouched keys keep the defaults
    info = client.get("/api/public/info").json()
    assert info["site"]["about"] == "We build test stands."
    client.put("/api/portal/settings", json={"site": {k: v for k, v in portal.DEFAULT_SITE.items()}})


def test_only_held_certifications_are_shown(client):
    from app.db import SessionLocal
    from app.models import CompanyProfile

    db = SessionLocal()
    prof = db.query(CompanyProfile).first() or CompanyProfile(name="Test Co")
    old = (prof.uei or "", prof.cage or "", dict(prof.certifications or {}))
    prof.uei, prof.cage, prof.certifications = "ABC123DEF456", "1A2B3", {"SDVOSB": "pending", "SB": "certified", "HUBZONE": "certified"}
    db.add(prof); db.commit()
    try:
        c = client.get("/api/public/info").json()["company"]
        assert c["uei"] == "ABC123DEF456" and "Small business" in c["certifications"] and "HUBZone" in c["certifications"]
        assert not any("SDVOSB" in x for x in c["certifications"])  # pending is not claimed
        client.put("/api/portal/settings", json={"show_codes": False})
        assert client.get("/api/public/info").json()["company"] is None
    finally:
        client.put("/api/portal/settings", json={"show_codes": True})
        prof.uei, prof.cage, prof.certifications = old
        db.commit(); db.close()


def test_customer_can_download_their_quote_as_pdf(client):
    q = _quote(client, [FIX / "cad" / "machined_block.step"], quantity=3).json()
    r = client.get(f"/api/public/quote/{q['ref']}/pdf?token={q['token']}")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and q["ref"] in r.headers["content-disposition"]
    from pypdf import PdfReader
    import io

    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert q["ref"] in text and "each" in text and "margin" not in text.lower()
    bad = client.get(f"/api/public/quote/{q['ref']}/pdf?token=wrong")
    assert bad.status_code == 404 and "text/html" in bad.headers["content-type"]


def test_owner_can_preview_a_closed_page(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("APP_USERNAME", "owner")
    portal.QUOTE_LIMIT.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "owner", "password": "pw"}).status_code == 200
        c.put("/api/portal/settings", json={"enabled": False})
        assert c.get("/api/public/info").json()["owner"] is True
        r = _quote(c, [FIX / "cad" / "machined_block.step"], preview="true")
        assert r.status_code == 200 and r.json()["result"]["kind"] == "instant"
        c.cookies.clear()
        r = _quote(c, [FIX / "cad" / "machined_block.step"], preview="true")  # a visitor cannot use the preview flag
        assert r.status_code == 400


def test_quote_shows_what_we_read_and_three_views(client):
    q = _quote(client, [FIX / "cad" / "machined_block.step"]).json()
    it = q["result"]["items"][0]
    facts = {f["label"]: f for f in it["facts"]}
    assert facts["Overall size"]["value"].startswith("4.000 x 3.000 x 0.500")
    assert facts["Material"]["flag"] == "assumed"  # nothing in the files said 6061, so the customer is asked to check
    assert "Ø" in facts["Holes"]["value"]
    assert it["view"]["kind"] == "model"
    svg = client.get(f"/api/public/quote/{q['ref']}/views/{it['view']['key']}.svg?token={q['token']}")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml") and "<path" in svg.text and "4.000" in svg.text
    assert "script" not in svg.text.lower() and "default-src 'none'" in svg.headers["content-security-policy"]
    assert client.get(f"/api/public/quote/{q['ref']}/views/{it['view']['key']}.svg?token=nope").status_code == 400
    assert client.get(f"/api/public/quote/{q['ref']}/views/notakey.svg?token={q['token']}").status_code == 404
    # repricing reuses the drawing
    r = client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 10}).json()
    assert r["result"]["items"][0]["view"]["key"] == it["view"]["key"]
    pdf = client.get(f"/api/public/quote/{q['ref']}/pdf?token={q['token']}")
    from pypdf import PdfReader
    import io

    text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages).split())
    assert "What we read" in text and "Isometric" in text and "assumed, please check" in text, text[-600:]


def test_drawing_dxf_and_board_reads(client):
    d = _quote(client, [FIX / "drawings" / "sheet_cover.pdf"]).json()["result"]["items"][0]
    labels = {f["label"]: f["value"] for f in d["facts"]}
    assert "55120-1" in labels["Part"] and labels["Sheet thickness"] == "0.063 in" and "5052" in labels["Material"]
    assert d["view"]["kind"] == "envelope"
    f = _quote(client, [FIX / "flat" / "plate_holes_slot.dxf"], thickness="0.125").json()["result"]["items"][0]
    assert f["view"]["kind"] == "flat" and any("6.000 x 4.000" in x["value"] for x in f["facts"])
    b = _quote(client, [FIX / "pcb" / "kicad_fab.zip"]).json()["result"]["items"][0]
    assert any(x["label"] == "Board" and "4 layers" in x["value"] for x in b["facts"])


def test_big_model_is_read_in_the_background(client, monkeypatch):
    import time

    from app import isolate

    monkeypatch.setattr(isolate, "BIG_FILE", 10 * 1024)  # treat the 47 KB test model as "big"
    q = _quote(client, [FIX / "cad" / "machined_block.step"], quantity=2).json()
    assert q["result"]["kind"] == "processing" and "reading it now" in q["result"]["message"]
    for _ in range(120):
        time.sleep(1)
        v = client.get(f"/api/public/quote/{q['ref']}?token={q['token']}").json()
        if v["result"]["kind"] != "processing":
            break
    assert v["result"]["kind"] == "instant" and v["result"]["unit_price"] > 0 and v["result"]["quantity"] == 2
    assert v["result"]["items"][0]["view"]["kind"] == "model"


def test_size_limits_allow_large_models():
    assert portal.MAX_FILE >= 150 * 1024 * 1024 and portal.MAX_TOTAL > portal.MAX_FILE
