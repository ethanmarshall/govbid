import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.connectors import sam_gov, usaspending
from app.main import app

FIX = Path(__file__).parent / "fixtures"


def _patch_sam(monkeypatch):
    payload = json.loads((FIX / "sam_response.json").read_text())
    real_client = httpx.Client

    def handler(request: httpx.Request):
        if "noticedesc" in str(request.url):
            return httpx.Response(200, json={"description": "<p>The contractor shall staff a help desk 8am-5pm.</p>"})
        if int(request.url.params.get("offset", "0")) > 0:
            return httpx.Response(200, json={"totalRecords": 3, "opportunitiesData": []})
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(sam_gov.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))


def test_full_flow(monkeypatch, tmp_path):
    _patch_sam(monkeypatch)
    with TestClient(app) as c:
        # profile
        r = c.put("/api/profile", json={
            "name": "Marshall Tech LLC", "sam_status": "active", "naics_codes": ["541519", "423490"],
            "certifications": {"SB": "certified", "SDVOSB": "pending"},
            "small_under_naics": {"541519": True, "423490": True}, "nsn_watchlist": ["5340"],
        })
        assert r.status_code == 200

        # sync (2 NAICS -> 2 queries, same fixture so second run updates)
        r = c.post("/api/sync/sam", json={"days_back": 7})
        body = r.json()
        assert body["added"] == 3 and body["queries"] == 2, body

        # list with eligibility counts
        r = c.get("/api/opportunities").json()
        assert r["total"] == 3
        assert r["counts"] == {"eligible_now": 1, "eligible_once_certified": 1, "not_eligible": 1}
        r = c.get("/api/opportunities", params={"eligibility": "eligible_once_certified"}).json()
        assert r["results"][0]["set_aside_code"] == "SDVOSBC"
        opp_id = r["results"][0]["id"]

        # detail pulls description lazily
        d = c.get(f"/api/opportunities/{opp_id}").json()
        assert "help desk" in d["description"]
        assert d["eligibility"]["status"] == "eligible_once_certified"

        # upload a document and analyze
        files = {"files": ("rfq.txt", b"Section L\nL.1 The offeror shall submit a quote not to exceed 5 pages.\nFAR 52.219-14 applies.", "text/plain")}
        assert c.post(f"/api/opportunities/{opp_id}/documents", files=files).status_code == 200
        a = c.post(f"/api/opportunities/{opp_id}/analyze").json()["analysis"]
        assert a["method"] == "heuristic"
        assert any("52.219-14" == k["clause"] for k in a["breakdown"]["key_clauses"])
        assert len(a["compliance_matrix"]) >= 2

        # matrix edit and export
        m = a["compliance_matrix"]
        m[0]["status"] = "done"
        assert c.put(f"/api/opportunities/{opp_id}/matrix", json={"compliance_matrix": m}).status_code == 200
        x = c.get(f"/api/opportunities/{opp_id}/matrix.xlsx")
        assert x.status_code == 200 and x.content[:2] == b"PK"

        # pipeline
        assert c.put(f"/api/opportunities/{opp_id}/pipeline", json={"stage": "evaluating", "notes": "wait on VetCert"}).status_code == 200
        p = c.get("/api/pipeline").json()
        assert p[0]["pipeline"]["stage"] == "evaluating"

        # DIBBS import with watchlist
        dibbs = b"SPE7M126T1234  5340013965472 CLAMP,LOOP 0025 EA 10/08/2026 10/20/2099\nSPE4A626U5678  2915012345678 NOZZLE 0004 EA 10/08/2026 10/22/2099\n"
        r = c.post("/api/import/dibbs", files={"file": ("in261008.txt", dibbs, "text/plain")}).json()
        assert r == {"parsed": 2, "kept": 1, "added": 1, "updated": 0}

        # dashboard
        dash = c.get("/api/dashboard").json()
        assert dash["veteran_set_asides"] == 1
        assert dash["by_source"]["dibbs"] == 1


def test_competitors(monkeypatch):
    def fake(**kw):
        return [
            {"recipient": "Acme", "recipient_uei": "U1", "amount": 100.0, "agency": "VA", "award_id": "1"},
            {"recipient": "Acme", "recipient_uei": "U1", "amount": 50.0, "agency": "DoD", "award_id": "2"},
            {"recipient": "Beta", "recipient_uei": "U2", "amount": 80.0, "agency": "VA", "award_id": "3"},
        ]

    monkeypatch.setattr(usaspending, "search_awards", fake)
    with TestClient(app) as c:
        r = c.get("/api/competitors", params={"naics": "541519"}).json()
        assert r["top_competitors"][0]["recipient"] == "Acme"
        assert r["top_competitors"][0]["total"] == 150.0
        assert r["total_value"] == 230.0
