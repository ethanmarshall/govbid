"""Source Approval Request tracker: CRUD, checklist by category, document upload, candidates, hooks."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import config, nsn_history
from app.db import SessionLocal
from app.main import app
from app.models import Opportunity, PartQuote


def test_meta_has_verified_categories_and_checklist():
    with TestClient(app) as c:
        m = c.get("/api/sar/meta").json()
    assert [x["key"] for x in m["categories"]] == ["I", "II", "III", "IV"]
    keys = {x["key"]: x for x in m["checklist"]}
    assert keys["J"]["categories"] == ["II"]  # comparative analysis: Category II only
    assert keys["T"]["categories"] == ["IV"]  # reverse engineering plan: Category IV only
    assert m["review_min_days"] == 90 and m["review_long_days"] == 180
    assert m["contacts"]["Land and Maritime"]["sar_email"] == "dsccao-sar@dla.mil"


def test_sar_crud_checklist_and_value():
    with TestClient(app) as c:
        db = SessionLocal()
        nsn_history.add_record(db, {"nsn": "5340-01-777-0001", "nomenclature": "BRACKET, MOUNTING", "cage": "1ABC2",
                                    "contract_number": "SPE7M1-25-P-0001", "award_date": "2025-06-01", "quantity": 40,
                                    "unit_price": 25.0, "source": "manual"})
        db.close()
        r = c.post("/api/sar", json={"nsn": "5340017770001", "part_number": "A123-4", "dla_activity": "Land and Maritime",
                                     "category": "IV", "approved_sources": [{"cage": "1abc2", "part_number": "A123-4"}, "9XYZ1"],
                                     "annual_demand": 200})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["nsn"] == "5340-01-777-0001" and s["nomenclature"] == "BRACKET, MOUNTING"
        assert [a["cage"] for a in s["approved_sources"]] == ["1ABC2", "9XYZ1"]
        assert s["last_award_price"] == 25.0 and s["estimated_annual_value"] == 5000.0
        req = {row["key"] for row in s["checklist"] if row["required"]}
        assert "T" in req and "J" not in req and "G" not in req
        assert s["contact"]["sar_email"] == "dsccao-sar@dla.mil"

        sid = s["id"]
        bad = c.put(f"/api/sar/{sid}", json={"status": "bogus"})
        assert bad.status_code == 400
        assert c.put(f"/api/sar/{sid}", json={"category": "V"}).status_code == 400
        assert c.post("/api/sar", json={"nsn": "12345"}).status_code == 400

        u = c.put(f"/api/sar/{sid}", json={"status": "submitted", "checklist": {"A": {"status": "done"}, "N": {"status": "na", "note": "No license"}},
                                           "re_measurements": "OD 1.250 +/- .002 (3 samples)"}).json()
        assert u["submitted_date"] == date.today().isoformat()
        assert u["checklist_done"] == 2
        assert next(r for r in u["checklist"] if r["key"] == "N")["note"] == "No license"

        listed = c.get("/api/sar", params={"status": "submitted"}).json()
        assert any(x["id"] == sid for x in listed)

        assert c.delete(f"/api/sar/{sid}").json() == {"ok": True}
        assert c.get(f"/api/sar/{sid}").status_code == 404


def test_document_upload_download_delete():
    with TestClient(app) as c:
        sid = c.post("/api/sar", json={"nsn": "5340-01-777-0002", "category": "II"}).json()["id"]
        files = [("files", ("comparison.pdf", b"%PDF-1.4 test", "application/pdf")), ("files", ("comparison.pdf", b"second", "application/pdf"))]
        r = c.post(f"/api/sar/{sid}/documents", data={"section": "J"}, files=files)
        assert r.status_code == 200, r.text
        added = r.json()["added"]
        assert [a["name"] for a in added] == ["J-comparison.pdf", "J-comparison (2).pdf"]
        assert (config.UPLOAD_DIR / "sar" / str(sid) / "J-comparison.pdf").exists()
        sar = r.json()["sar"]
        row = next(x for x in sar["checklist"] if x["key"] == "J")
        assert row["status"] == "in_progress" and len(row["files"]) == 2

        d = c.get(f"/api/sar/{sid}/documents/J-comparison.pdf")
        assert d.status_code == 200 and d.content == b"%PDF-1.4 test"
        assert c.post(f"/api/sar/{sid}/documents", data={"section": "ZZ"}, files=files[:1]).status_code == 400

        after = c.delete(f"/api/sar/{sid}/documents/J-comparison.pdf").json()
        assert [f["name"] for f in after["files"]] == ["J-comparison (2).pdf"]
        assert c.get(f"/api/sar/{sid}/documents/J-comparison.pdf").status_code == 404
        # photos for reverse engineering go to the RE section
        assert c.post(f"/api/sar/{sid}/documents", data={"section": "RE"}, files=[("files", ("p1.jpg", b"jpg", "image/jpeg"))]).status_code == 200
        c.delete(f"/api/sar/{sid}")
        assert not (config.UPLOAD_DIR / "sar" / str(sid)).exists()


def test_candidates_ranked_by_solicitations_and_award_value():
    db = SessionLocal()
    for i, (nsn, sol) in enumerate([("5935-01-888-0001", "SPE7L1-26-T-1001"), ("5935-01-888-0001", "SPE7L1-26-T-1002"),
                                    ("5935-01-888-0002", "SPE7L1-26-T-2001"), ("5935-01-888-0003", "SPE7L1-26-T-3001")]):
        db.add(Opportunity(source="dibbs", external_id=f"sar-cand-{i}", solicitation_number=sol, title=f"CONNECTOR {nsn[-4:]}", nsn=nsn,
                           quantity="25"))
    db.add(PartQuote(name="Spacer", nsn="5935-01-888-0004", spec={"approved_source_required": True}))
    db.add(PartQuote(name="Open source part", nsn="5935-01-888-0005", spec={"approved_source_required": False}))
    db.commit()
    nsn_history.add_record(db, {"nsn": "5935-01-888-0003", "cage": "7Q123", "contract_number": "SPE7L1-25-P-9", "award_date": "2025-01-10",
                                "quantity": 100, "unit_price": 80.0, "source": "manual"})
    nsn_history.add_record(db, {"nsn": "5935-01-888-0002", "cage": "7Q124", "contract_number": "SPE7L1-25-P-8", "award_date": "2025-01-10",
                                "quantity": 10, "unit_price": 5.0, "source": "manual"})
    db.close()
    with TestClient(app) as c:
        rows = [r for r in c.get("/api/sar/candidates", params={"limit": 500}).json() if r["nsn"].startswith("5935-01-888")]
    order = [r["nsn"][-4:] for r in rows]
    assert order[:3] == ["0001", "0003", "0002"], order  # 2 solicitations first, then larger last award value
    assert "0004" in order and "0005" not in order
    top = rows[0]
    assert top["solicitation_count"] == 2 and len(top["opportunity_ids"]) == 2
    r3 = next(r for r in rows if r["nsn"].endswith("0003"))
    assert r3["last_award_value"] == 8000.0 and r3["last_unit_price"] == 80.0 and r3["last_awardee_cage"] == "7Q123"


def test_calendar_and_dashboard_hooks():
    from app import sar_api

    with TestClient(app) as c:
        old = (date.today() - timedelta(days=200)).isoformat()
        sid = c.post("/api/sar", json={"nsn": "5340-01-777-0003", "dla_activity": "Troop Support", "status": "under_review",
                                       "submitted_date": old}).json()["id"]
        db = SessionLocal()
        alerts = sar_api.dashboard_items(db)
        cal = sar_api.calendar_items(db)
        db.close()
        assert any("5340-01-777-0003" in a and "200 days" in a and "TrpSptCandE-sar@dla.mil" in a for a in alerts)
        mine = [e for e in cal if e["uid"].startswith(f"sar-{sid}-")]
        assert {e["date"] for e in mine} == {date.today() - timedelta(days=110), date.today() - timedelta(days=20)}
        c.delete(f"/api/sar/{sid}")
