import io
from collections import Counter
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.analysis import cited_standards
from app.main import app
from app.standards import parse_doc_id, parse_doc_id_full, revisions_differ
from app.standards_catalog import CATALOG, CATEGORIES


@pytest.mark.parametrize("text,expected", [
    ("MIL-STD-130N", ("MIL-STD-130", "N")),
    ("MIL-STD-130N(1)", ("MIL-STD-130", "N")),
    ("MIL-STD-130N w/CHANGE 1", ("MIL-STD-130", "N")),
    ("MIL-DTL-5541F", ("MIL-DTL-5541", "F")),
    ("MIL-STD-2073-1E", ("MIL-STD-2073-1", "E")),
    ("MIL-PRF-38534", ("MIL-PRF-38534", "")),
    ("DI-MISC-80508B", ("DI-MISC-80508", "B")),
    ("ASME Y14.5-2018", ("ASME Y14.5", "2018")),
    ("ASME Y14.5M-1994", ("ASME Y14.5", "1994")),
    ("IPC-A-610H", ("IPC-A-610", "H")),
    ("AS9100D", ("AS9100", "D")),
    ("J-STD-001H", ("J-STD-001", "H")),
    ("IPC J-STD-001H", ("J-STD-001", "H")),
    ("NIST SP 800-171", ("NIST SP 800-171", "")),
    ("NIST SP 800-171 Rev 2", ("NIST SP 800-171", "Rev 2")),
    ("NIST SP 800-171r3", ("NIST SP 800-171", "Rev 3")),
    ("NIST SP 800-171A", ("NIST SP 800-171A", "")),
    ("ISO 9001:2015", ("ISO 9001", "2015")),
    ("iso 9001:2015", ("ISO 9001", "2015")),
    ("mil std 461 g", ("MIL-STD-461", "G")),
    ("MIL-STD-461G (NOTICE 1)", ("MIL-STD-461", "G")),
    ("ASTM A276/A276M-24", ("ASTM A276", "24")),
    ("AWS D1.1/D1.1M:2020", ("AWS D1.1", "2020")),
    ("NFPA 70E-2024", ("NFPA 70E", "2024")),
    ("ANSI/ESD S20.20-2021", ("ANSI/ESD S20.20", "2021")),
    ("IPC/WHMA-A-620D", ("IPC/WHMA-A-620", "D")),
    ("AMS 2700F", ("AMS2700", "F")),
    ("EIA-649C", ("EIA-649", "C")),
    ("MIL-DTL-0053030B", ("MIL-DTL-53030", "B")),
    ("MIL-STD-1399-300B", ("MIL-STD-1399-300", "B")),
])
def test_parse_doc_id(text, expected):
    assert parse_doc_id(text) == expected


def test_parse_change_noted():
    assert parse_doc_id_full("MIL-STD-130N(1)")["change"] == "Change 1"
    assert parse_doc_id_full("MIL-STD-130N w/CHANGE 1")["change"] == "Change 1"
    assert parse_doc_id_full("MIL-STD-461G (NOTICE 1)")["change"] == "Notice 1"


def test_revisions_differ():
    assert revisions_differ("N", "M")
    assert not revisions_differ("N", "n")
    assert not revisions_differ("", "N")
    assert not revisions_differ("Rev 2", "2")


def test_catalog_integrity():
    assert len(CATALOG) >= 300
    ids = [e["id"] for e in CATALOG]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    assert not dupes, dupes
    for e in CATALOG:
        assert e["title"].strip() and e["summary"].strip(), e["id"]
        assert e["category"] in CATEGORIES, e["id"]
        assert e["publisher"], e["id"]
        assert isinstance(e["free"], bool)
        assert "—" not in e["title"] + e["summary"], e["id"]
        # base IDs carry no revision: parsing the ID gives the ID back
        base, rev = parse_doc_id(e["id"])
        assert base == e["id"], (e["id"], base, rev)
    assert {e["category"] for e in CATALOG} == set(CATEGORIES)


def _q(base_id):
    return quote(base_id, safe="")


def test_list_filter_and_lookup():
    with TestClient(app) as c:
        r = c.get("/api/standards", params={"limit": 500})
        body = r.json()
        assert r.status_code == 200 and body["total"] >= 300

        r = c.get("/api/standards", params={"category": "Shipboard equipment (Navy)"})
        assert all(i["category"] == "Shipboard equipment (Navy)" for i in r.json()["items"])

        r = c.get("/api/standards", params={"q": "MIL-STD-130N"})
        items = r.json()["items"]
        assert items[0]["base_id"] == "MIL-STD-130"
        assert r.json()["lookup"] is None

        r = c.get("/api/standards", params={"q": "harness"})
        assert any(i["base_id"] == "IPC/WHMA-A-620" for i in r.json()["items"])

        r = c.get("/api/standards", params={"free": "false", "limit": 500})
        assert all(not i["free"] for i in r.json()["items"])

        # an ID not in the catalog still gets links
        r = c.get("/api/standards/lookup", params={"id": "MIL-DTL-12345C"})
        lk = r.json()
        assert lk["parsed"]["base_id"] == "MIL-DTL-12345" and lk["parsed"]["revision"] == "C"
        assert lk["known"] is False
        assert lk["entry"]["assist_url"].startswith("https://quicksearch.dla.mil")
        assert "everyspec.com" in lk["entry"]["everyspec_url"]
        assert lk["entry"]["free"] is True
        r = c.get("/api/standards", params={"q": "MIL-DTL-12345C"})
        assert r.json()["lookup"]["parsed"]["base_id"] == "MIL-DTL-12345"

        # slash sheet resolves its parent
        lk = c.get("/api/standards/lookup", params={"id": "MIL-DTL-38999/20"}).json()
        assert lk["entry"]["parent_id"] == "MIL-DTL-38999"

        r = c.get("/api/standards/categories")
        cats = {x["category"]: x["count"] for x in r.json()["categories"]}
        assert cats["Data item descriptions (DIDs)"] > 10

        # save to library with a revision, then the library scope shows it
        r = c.put(f"/api/standards/{_q('IPC-7711/7721')}", json={"in_library": True, "revision_on_file": "C", "notes": "bought 2026"})
        assert r.status_code == 200 and r.json()["revision_on_file"] == "C"
        r = c.get("/api/standards", params={"scope": "library"})
        assert "IPC-7711/7721" in [i["base_id"] for i in r.json()["items"]]
        r = c.get(f"/api/standards/{_q('IPC-7711/7721')}")
        assert r.json()["notes"] == "bought 2026" and r.json()["in_catalog"]


def test_record_cited_and_mismatch():
    from app.db import SessionLocal
    from app.models import Opportunity
    from app.standards import record_cited_standards, revision_check

    with TestClient(app) as c:
        db = SessionLocal()
        opp = Opportunity(source="manual", external_id="std-test-1", solicitation_number="N00104-26-Q-0001", title="Cable assemblies")
        db.add(opp)
        db.commit()

        c.put("/api/standards/MIL-STD-130", json={"revision_on_file": "M"})
        text = "Mark per MIL-STD-130N. Solder per J-STD-001. Report per DI-NDTI-80809B. Drawings to ASME Y14.5. Also MIL-STD-130N."
        cited = cited_standards(text)
        out = record_cited_standards(db, opp, cited)
        by = {o["base_id"]: o for o in out}
        assert by["MIL-STD-130"]["cited_revision"] == "N"
        assert by["MIL-STD-130"]["revision_on_file"] == "M"
        assert by["MIL-STD-130"]["mismatch"] is True
        assert by["J-STD-001"]["mismatch"] is False
        assert by["DI-NDTI-80809"]["in_catalog"] is True

        # re-running for the same opportunity replaces, not duplicates, the citation
        record_cited_standards(db, opp, cited)
        entry = c.get("/api/standards/MIL-STD-130").json()
        assert len([x for x in entry["citations"] if x["opportunity_id"] == opp.id]) == 1
        assert entry["cited_count"] >= 1 and entry["mismatch"] is True  # other tests may cite it too (shared test DB)
        mine = next(x for x in entry["citations"] if x["opportunity_id"] == opp.id)
        assert mine["solicitation_number"] == "N00104-26-Q-0001"

        r = c.get("/api/standards", params={"scope": "cited"})
        assert "MIL-STD-130" in [i["base_id"] for i in r.json()["items"]]

        # read-only check through the API
        r = c.post("/api/standards/revision-check", json={"cited": [{"standard": "MIL-STD-130M"}, "IPC-A-610H"]})
        res = {x["base_id"]: x for x in r.json()["results"]}
        assert res["MIL-STD-130"]["mismatch"] is False
        assert res["IPC-A-610"]["revision_on_file"] == ""
        assert revision_check(db, []) == []
        db.close()


def test_file_upload_download_delete():
    pdf = b"%PDF-1.4\n%test\n"
    with TestClient(app) as c:
        r = c.post(f"/api/standards/{_q('MIL-DTL-5541')}/file",
                   files={"file": ("mil-dtl-5541f.pdf", io.BytesIO(pdf), "application/pdf")}, data={"revision": "F"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_file"] and body["in_library"] and body["revision_on_file"] == "F"
        r = c.get(f"/api/standards/{_q('MIL-DTL-5541')}/file")
        assert r.status_code == 200 and r.content == pdf
        r = c.post(f"/api/standards/{_q('MIL-DTL-5541')}/file", files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
        assert r.status_code == 400
        r = c.delete(f"/api/standards/{_q('MIL-DTL-5541')}/file")
        assert r.status_code == 200 and not r.json()["has_file"]
        assert c.get(f"/api/standards/{_q('MIL-DTL-5541')}/file").status_code == 404


def test_import_csv():
    csv_text = (
        "Exported from ASSIST\n"
        "Document ID,Title,Status,Doc Date\n"
        "MIL-STD-1234C,Some Interesting Standard,Active,2020-01-01\n"
        "MIL-STD-130N,Identification Marking of U.S. Military Property,Active,2012-11-16\n"
        ",,,\n"
        "Notes only,no id here,,\n"
    )
    with TestClient(app) as c:
        r = c.post("/api/standards/import", files={"file": ("list.csv", io.BytesIO(csv_text.encode()), "text/csv")})
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["total"] == 2 and res["skipped"] == 2
        e = c.get("/api/standards/MIL-STD-1234").json()
        assert e["title"] == "Some Interesting Standard" and e["status"] == "Active" and e["listed_revision"] == "C"
        r = c.get("/api/standards", params={"q": "interesting"})
        assert r.json()["items"][0]["base_id"] == "MIL-STD-1234"
        r = c.post("/api/standards/import", files={"file": ("list.pdf", io.BytesIO(b"x"), "application/pdf")})
        assert r.status_code == 400
