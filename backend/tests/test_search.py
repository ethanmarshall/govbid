"""Search everything: FTS5 and fallback engines, phrases, AND semantics, ranking, links, index refresh."""
import pytest
from fastapi.testclient import TestClient

from app import search_api
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Analysis, LibraryEntry, Opportunity, Package, PackageSection, PartQuote
from app.models_crm import Contact, Interaction, Organization
from app.models_pp import PastPerformance


@pytest.fixture(scope="module")
def seeded():
    init_db()
    db = SessionLocal()
    pkg = Package(name="Zorblax hangar proposal")
    db.add(pkg)
    db.flush()
    sec = PackageSection(package_id=pkg.id, number="3.1", title="Quality approach",
                         content="Our quixotic inspection plan uses first article testing and calibrated gauges.")
    lib = LibraryEntry(title="Quixotic inspection boilerplate", category="Quality",
                       content="We apply quixotic inspection to every lot before shipment.")
    lib2 = LibraryEntry(title="Unrelated note", category="Boilerplate",
                        content="Inspection is quixotic here but the words are apart: quixotic people like plans of inspection.")
    opp = Opportunity(source="manual", external_id="search-1", title="Quixotic valve overhaul", solicitation_number="SPE4A0-26-Q-7777",
                      description="<p>Overhaul of <b>marmoset</b> valves.</p>")
    db.add_all([sec, lib, lib2, opp])
    db.flush()
    db.add(Analysis(opportunity_id=opp.id, summary="Valve work", compliance_matrix=[{"id": 1, "requirement": "Provide a marmoset certificate of conformance"}]))
    pp = PastPerformance(title="Hydraulic bench rebuild", description="Rebuilt marmoset test benches for a shipyard.")
    pq = PartQuote(name="Bracket", nsn="5340-01-555-1234", part_number="ZX-9001-A", notes="anodize per MIL-A-8625")
    org = Organization(name="Wombat Machining", kind="vendor", capabilities="Five-axis milling")
    db.add_all([pp, pq, org])
    db.flush()
    db.add(Contact(organization_id=org.id, name="Pat Wombatson", email="pat@wombat.example"))
    db.add(Interaction(organization_id=org.id, summary="Discussed marmoset fixtures", next_step="Send drawings"))
    db.commit()
    ids = {"pkg": pkg.id, "sec": sec.id, "lib": lib.id, "lib2": lib2.id, "opp": opp.id, "pp": pp.id, "pq": pq.id, "org": org.id}
    db.close()
    return ids


@pytest.mark.parametrize("engine", ["auto", "like"])
def test_phrase_and_and_semantics(seeded, engine):
    db = SessionLocal()
    try:
        res = search_api.search(db, '"quixotic inspection"', engine=engine)
        refs = {(r["type"], r["ref"]) for r in res["results"]}
        assert ("section", str(seeded["sec"])) in refs and ("library", str(seeded["lib"])) in refs
        assert ("library", str(seeded["lib2"])) not in refs  # words present but not as a phrase
        loose = {(r["type"], r["ref"]) for r in search_api.search(db, "quixotic inspection", engine=engine)["results"]}
        assert ("library", str(seeded["lib2"])) in loose  # all words, any order
        assert not search_api.search(db, "quixotic nonexistentword", engine=engine)["results"]  # AND
    finally:
        db.close()


@pytest.mark.parametrize("engine", ["auto", "like"])
def test_types_links_and_highlight(seeded, engine):
    db = SessionLocal()
    try:
        res = search_api.search(db, "marmoset", engine=engine)
        by_type = {r["type"]: r for r in res["results"]}
        assert {"opportunity", "analysis", "past_performance", "interaction"} <= set(by_type)
        assert by_type["opportunity"]["url"] == f"/opportunities/{seeded['opp']}"
        assert by_type["past_performance"]["url"] == f"/past-performance?id={seeded['pp']}"
        assert by_type["interaction"]["url"] == f"/contacts?id={seeded['org']}"
        hl = search_api.HL_START
        assert hl in by_type["opportunity"]["snippet"] and "<b>" not in by_type["opportunity"]["snippet"]
        only = search_api.search(db, "marmoset", types=["analysis"], engine=engine)["results"]
        assert only and all(r["type"] == "analysis" for r in only)
    finally:
        db.close()


def test_title_match_ranks_above_body_match(seeded):
    db = SessionLocal()
    try:
        for engine in ("auto", "like"):
            res = [r for r in search_api.search(db, "quixotic", engine=engine)["results"]]
            pos = {(r["type"], r["ref"]): i for i, r in enumerate(res)}
            # "Quixotic valve overhaul" and "Quixotic inspection boilerplate" have the word in the title
            assert pos[("opportunity", str(seeded["opp"]))] < pos[("section", str(seeded["sec"]))]
            assert pos[("library", str(seeded["lib"]))] < pos[("section", str(seeded["sec"]))]
    finally:
        db.close()


def test_api_part_numbers_reuse_and_index_refresh(seeded):
    with TestClient(app) as c:
        r = c.get("/api/search", params={"q": "ZX-9001"}).json()
        assert r["engine"] == "fts5"  # SQLite in CI and on macOS ships with FTS5
        assert any(x["type"] == "part_quote" and x["url"] == f"/part-quotes?id={seeded['pq']}" for x in r["results"])
        r = c.get("/api/search", params={"q": "5340-01-555-1234"}).json()
        assert any(x["type"] == "part_quote" for x in r["results"])
        r = c.get("/api/search", params={"q": "wombatson"}).json()
        assert any(x["type"] == "contact" for x in r["results"])

        lib = next(x for x in c.get("/api/search", params={"q": "quixotic boilerplate"}).json()["results"] if x["type"] == "library")
        assert lib["reusable"] and "every lot" in lib["copy"]
        opp = next(x for x in c.get("/api/search", params={"q": "valve overhaul"}).json()["results"] if x["type"] == "opportunity")
        assert not opp["reusable"] and "copy" not in opp

        # new data shows up without a manual reindex (signature changed)
        assert not c.get("/api/search", params={"q": "pangolin"}).json()["results"]
        db = SessionLocal()
        db.add(LibraryEntry(title="Pangolin plan", content="Scales"))
        db.commit()
        db.close()
        assert c.get("/api/search", params={"q": "pangolin"}).json()["results"]
        assert c.post("/api/search/reindex").json()["indexed"] > 0
        assert c.get("/api/search", params={"q": ""}).json()["results"] == []
        assert c.get("/api/search", params={"q": '"'}).status_code == 200


def test_parse_query():
    assert search_api.parse_query('"First Article"  test  test') == ["first article", "test"]
    assert search_api.parse_query("") == []
