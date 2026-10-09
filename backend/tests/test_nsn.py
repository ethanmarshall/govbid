"""NSN award history: normalization, records, dedupe, stats, import, quote outcomes, API."""
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import nsn_history
from app.db import SessionLocal, init_db
from app.main import app
from app.models import CompanyProfile, PartQuote
from app.models_nsn import AwardRecord

NSN = "5340-01-480-5627"


@pytest.fixture
def db():
    init_db()
    s = SessionLocal()
    s.execute(delete(AwardRecord))
    s.execute(delete(PartQuote))
    s.commit()
    yield s
    s.close()


# ---------------------------------------------------------------- normalize
@pytest.mark.parametrize("raw,nsn,niin,fsc", [
    ("5340-01-480-5627", "5340-01-480-5627", "014805627", "5340"),
    ("5340014805627", "5340-01-480-5627", "014805627", "5340"),
    (" 5340 01 480 5627 ", "5340-01-480-5627", "014805627", "5340"),
    ("NSN: 5340-01-480-5627", "5340-01-480-5627", "014805627", "5340"),
    ("01-480-5627", "01-480-5627", "014805627", ""),
    ("014805627", "01-480-5627", "014805627", ""),
])
def test_normalize(raw, nsn, niin, fsc):
    assert nsn_history.normalize_nsn(raw) == {"nsn": nsn, "niin": niin, "fsc": fsc}


@pytest.mark.parametrize("raw", ["", "5340-01-480", "ABCD-01-480-5627", "53400148056271"])
def test_normalize_rejects(raw):
    with pytest.raises(ValueError):
        nsn_history.normalize_nsn(raw)


def test_parse_values():
    assert nsn_history.parse_date("05-10-2016") == "2016-05-10"  # DIBBS format
    assert nsn_history.parse_date("5/10/16") == "2016-05-10"
    assert nsn_history.parse_date("2016-05-10 00:00:00") == "2016-05-10"
    assert nsn_history.parse_date("May 10, 2016") == "2016-05-10"
    assert nsn_history.parse_date("13-45-2016") == ""
    assert nsn_history.parse_money("$1,250.50") == 1250.5
    assert nsn_history.parse_int("1,000") == 1000


# ---------------------------------------------------------------- records and stats
def test_history_stats_and_dedupe(db):
    rows = [
        {"nsn": NSN, "contract_number": "SPE7M1-22-P-1111", "award_date": "2022-03-01", "quantity": 10, "unit_price": 40.0, "awardee": "Alpha Mfg", "cage": "1AAA1"},
        {"nsn": "5340014805627", "contract_number": "SPE7M1-24-P-2222", "award_date": "2024-06-15", "quantity": 25, "total": 1250.0, "awardee": "Bravo Machine"},
        {"nsn": "01-480-5627", "contract_number": "SPE7M1-23-P-3333", "award_date": "2023-01-20", "quantity": 5, "unit_price": 62.0, "cage": "3CCC3"},
        {"nsn": NSN, "contract_number": "SPE4A1-25-D-0001", "award_date": "2025-02-01", "total": 500000.0, "cage": "4DDD4"},  # IDC: no unit price
    ]
    for r in rows:
        rec, created = nsn_history.add_record(db, r)
        assert created
    dup, created = nsn_history.add_record(db, rows[0])
    assert not created and dup.contract_number == "SPE7M1-22-P-1111"

    h = nsn_history.history(db, NSN)
    s = h["stats"]
    assert h["nsn"] == NSN and s["count"] == 4 and s["priced_count"] == 3
    assert [r["award_date"] for r in h["records"]] == ["2025-02-01", "2024-06-15", "2023-01-20", "2022-03-01"]
    assert s["last_award_date"] == "2025-02-01" and s["last_awardee"] == "4DDD4"
    assert s["last_unit_price"] == 50.0 and s["last_price_date"] == "2024-06-15" and s["last_priced_awardee"] == "Bravo Machine"
    assert (s["min"], s["max"], s["median_unit_price"]) == (40.0, 62.0, 50.0)
    assert h["records"][1]["unit_price"] == 50.0  # derived from total / quantity
    assert nsn_history.reference_price(db, "014805627") == 50.0
    assert nsn_history.reference_price(db, "9999-99-999-9999") is None
    assert nsn_history.reference_price(db, "junk") is None


def test_record_quote_outcome(db):
    if not db.get(CompanyProfile, 1):
        db.add(CompanyProfile(id=1, name="Marshall Precision LLC", cage="7ABC1"))
        db.commit()
    nsn_history.add_record(db, {"nsn": NSN, "contract_number": "C-1", "award_date": "2020-01-01", "unit_price": 80.0, "quantity": 5})
    q = PartQuote(name="Bracket", nsn="5340014805627", status="lost", quoted_quantity=10, quoted_unit_price=95.0)
    db.add(q)
    db.commit()

    rec = nsn_history.record_quote_outcome(db, q)
    assert rec.source == "quote_lost" and rec.unit_price == 95.0 and "our losing price" in rec.notes.lower()
    h = nsn_history.history(db, NSN)
    assert h["stats"]["last_unit_price"] == 80.0  # a losing quote is not an award price
    assert h["stats"]["our_last_losing_price"] == 95.0

    q.status = "won"
    q.quoted_unit_price = 78.0
    db.commit()
    rec = nsn_history.record_quote_outcome(db, q)
    assert rec.source == "quote_won" and rec.cage == db.get(CompanyProfile, 1).cage
    assert db.query(AwardRecord).filter(AwardRecord.quote_id == q.id).count() == 1
    assert nsn_history.reference_price(db, NSN) == 78.0

    q.status = "submitted"
    db.commit()
    assert nsn_history.record_quote_outcome(db, q) is None
    assert db.query(AwardRecord).filter(AwardRecord.quote_id == q.id).count() == 0


def test_history_syncs_quotes(db):
    db.add(PartQuote(name="Pin", nsn="5340-01-480-5627", status="won", quoted_quantity=4, quoted_unit_price=12.5))
    db.add(PartQuote(name="Other", nsn="", status="won", quoted_quantity=4, quoted_unit_price=1.0))
    db.add(PartQuote(name="Draft", nsn=NSN, status="draft", quoted_quantity=4, quoted_unit_price=9.0))
    db.commit()
    h = nsn_history.history(db, NSN)
    assert [r["source"] for r in h["records"]] == ["quote_won"]
    assert h["stats"]["last_unit_price"] == 12.5


# ---------------------------------------------------------------- import
DIBBS_CSV = """DIBBS Award Search Results
#,Award/Basic Number,Delivery Order Number,Delivery Order Counter,Last Mod Posting Date,Awardee CAGE Code,Total Contract Price,Award Date,Posted Date,NSN/Part Number,Nomenclature,Purchase Request,Solicitation
1,SPE1C116D1056,,,05-07-2019,80298,"$500,000.00",05-10-2016,05-10-2016,5340014805627,"HANDLE, CRANK",,
2,SPE7M124P0001,SPE7M124F0002,,,1ABC5,"$1,200.00",06-17-2024,06-17-2024,5340014805627,"HANDLE, CRANK",1000055465,SPE7M124Q0001
3,SPE7M124P0009,,,,1ABC5,$900.00,06-18-2024,06-18-2024,ABC-123-PN,"HANDLE, CRANK",,
"""


def test_import_dibbs_award_results(db):
    out = nsn_history.import_awards(db, DIBBS_CSV.encode(), "awards.csv")
    assert out["rows"] == 3 and out["imported"] == 2 and out["skipped"] == 1 and out["nsns"] == [NSN]
    h = nsn_history.history(db, NSN)
    recs = {r["contract_number"]: r for r in h["records"]}
    assert set(recs) == {"SPE1C116D1056", "SPE7M124P0001/SPE7M124F0002"}
    r = recs["SPE7M124P0001/SPE7M124F0002"]
    assert r["cage"] == "1ABC5" and r["total"] == 1200.0 and r["award_date"] == "2024-06-17" and r["unit_price"] is None
    assert r["nomenclature"] == "HANDLE, CRANK" and r["source"] == "dibbs_import"
    again = nsn_history.import_awards(db, DIBBS_CSV.encode(), "awards.csv")
    assert again["imported"] == 0 and again["duplicates"] == 2


def test_import_generic_xlsx_with_default_nsn(db):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Procurement history for bracket"])
    ws.append(["CAGE", "Vendor", "PIID", "Qty", "Unit Cost", "Extended Price", "U/I", "Award Date"])
    ws.append(["1AAA1", "Alpha Mfg", "SPE7M1-21-P-0001", 20, 31.5, 630, "EA", "2021-08-02"])
    ws.append(["2BBB2", "Bravo", "SPE7M1-23-P-0002", "10", "$45.00", "", "ea", "3/4/2023"])
    buf = io.BytesIO()
    wb.save(buf)
    out = nsn_history.import_awards(db, buf.getvalue(), "history.xlsx", default_nsn="5340014805627")
    assert out["imported"] == 2
    h = nsn_history.history(db, NSN)
    assert h["stats"]["last_unit_price"] == 45.0 and h["stats"]["last_awardee"] == "Bravo"
    assert h["records"][0]["total"] == 450.0 and h["records"][0]["unit_of_issue"] == "EA"


def test_import_errors(db):
    with pytest.raises(ValueError):
        nsn_history.import_awards(db, b"a,b\n1,2\n", "x.csv")


@pytest.mark.parametrize("header,field", [
    ("NSN", "nsn"), ("National Stock Number", "nsn"), ("Part Number", "part_number"), ("Awardee CAGE Code", "cage"),
    ("Awardee", "awardee"), ("Vendor Name", "awardee"), ("Contract Number", "contract_number"), ("PIID", "contract_number"),
    ("Award/Basic Number", "contract_number"), ("Delivery Order Number", "order_number"), ("Order Number", "order_number"),
    ("Award Date", "award_date"), ("Qty", "quantity"), ("Quantity", "quantity"), ("Unit Price", "unit_price"),
    ("Unit Cost", "unit_price"), ("Total", "total"), ("Extended Price", "total"), ("Total Contract Price", "total"),
    ("U/I", "unit_of_issue"), ("Posted Date", None), ("Solicitation", None),
])
def test_classify_header(header, field):
    assert nsn_history.classify_header(header) == field


# ---------------------------------------------------------------- links
def test_links():
    out = nsn_history.lookup_links("5340014805627")
    urls = [l["url"] for l in out["links"]]
    assert "https://www.dibbs.bsm.dla.mil/Awards/AwdRecs.aspx?Category=nsn&TypeSrch=cq&Value=5340014805627" in urls
    assert any(u.startswith("https://www.dibbs.bsm.dla.mil/RFQ/RfqRecs.aspx") for u in urls)
    assert all(u.startswith("https://") for u in urls)
    niin_only = nsn_history.lookup_links("014805627")
    assert not any("dibbs" in l["url"] for l in niin_only["links"])


# ---------------------------------------------------------------- API
def test_api_flow(db):
    with TestClient(app) as c:
        r = c.post("/api/nsn/records", json={"nsn": "5340014805627", "contract_number": "X-1", "award_date": "2024-01-02", "quantity": 3, "unit_price": 19.99, "awardee": "Acme"})
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["nsn"] == NSN and not rec["duplicate"]
        assert c.post("/api/nsn/records", json={"nsn": NSN, "contract_number": "x-1", "award_date": "01/02/2024", "unit_price": 19.99}).json()["duplicate"]
        assert c.post("/api/nsn/records", json={"nsn": "123"}).status_code == 400
        assert c.post("/api/nsn/records", json={"nsn": NSN, "source": "quote_won"}).status_code == 400

        h = c.get(f"/api/nsn/{NSN}/history").json()
        assert h["stats"]["count"] == 1 and h["stats"]["last_unit_price"] == 19.99 and h["stats"]["last_awardee"] == "Acme"
        assert c.get("/api/nsn/bad/history").status_code == 400

        imp = c.post("/api/nsn/import", files={"file": ("awards.csv", DIBBS_CSV.encode(), "text/csv")})
        assert imp.status_code == 200 and imp.json()["imported"] == 2
        assert c.post("/api/nsn/import", files={"file": ("awards.pdf", b"%PDF", "application/pdf")}).status_code == 400
        assert c.get("/api/nsn/5340014805627/history").json()["stats"]["count"] == 3

        links = c.get(f"/api/nsn/{NSN}/links").json()
        assert links["links"] and links["notes"]

        assert c.delete(f"/api/nsn/records/{rec['id']}").json() == {"ok": True}
        assert c.delete(f"/api/nsn/records/{rec['id']}").status_code == 404

        db.add(PartQuote(name="Pin", nsn=NSN, status="lost", quoted_quantity=2, quoted_unit_price=33.0))
        db.commit()
        assert c.post("/api/nsn/sync-quotes").json()["touched"] == 1
        h = c.get(f"/api/nsn/{NSN}/history").json()
        assert h["stats"]["our_last_losing_price"] == 33.0
