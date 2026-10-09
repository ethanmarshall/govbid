import httpx
from fastapi.testclient import TestClient

from app import presets
from app.connectors import sam_gov
from app.main import app


def test_meta_exposes_presets():
    with TestClient(app) as c:
        m = c.get("/api/meta").json()
        assert m["primary_naics"] == "335314"
        assert "334513" in m["recommended_naics"] and "6685" in m["recommended_fsc"]
        ids = [p["id"] for p in m["search_presets"]]
        assert ids[0] == "target" and "navy-nuclear" in ids
        assert m["naics_titles"]["332710"] == "Machine Shops"


def test_apply_recommended_merges_and_sets_primary():
    with TestClient(app) as c:
        c.put("/api/profile", json={"name": "Shop", "naics_codes": ["541511"], "nsn_watchlist": ["5340"], "small_under_naics": {"541511": True}})
        p = c.post("/api/profile/apply-recommended", json={}).json()
        assert p["naics_codes"][0] == "335314"
        assert "541511" in p["naics_codes"]  # existing code kept
        assert set(presets.RECOMMENDED_NAICS) <= set(p["naics_codes"])
        assert len(p["naics_codes"]) == len(set(p["naics_codes"]))
        assert p["nsn_watchlist"][0] == "5340" and "6110" in p["nsn_watchlist"]
        assert all(p["small_under_naics"][c] for c in presets.RECOMMENDED_NAICS)
        # running it twice changes nothing
        assert c.post("/api/profile/apply-recommended", json={}).json()["naics_codes"] == p["naics_codes"]


def test_keyword_filter_and_presets_return_matches():
    with TestClient(app) as c:
        a = c.post("/api/opportunities", json={"title": "NPTU Ballston Spa electrical trainer panels", "naics": "999999", "solicitation_number": "KW-1"}).json()["id"]
        b = c.post("/api/opportunities", json={"title": "Custom control panel", "naics": "335314", "solicitation_number": "KW-2"}).json()["id"]
        c.post("/api/opportunities", json={"title": "Janitorial services", "naics": "561720", "solicitation_number": "KW-3"})
        navy = next(p for p in c.get("/api/meta").json()["search_presets"] if p["id"] == "navy-nuclear")
        ids = [r["id"] for r in c.get("/api/opportunities", params=navy["params"]).json()["results"]]
        assert a in ids and b not in ids
        mfg = next(p for p in c.get("/api/meta").json()["search_presets"] if p["id"] == "manufacturing")
        ids = [r["id"] for r in c.get("/api/opportunities", params={**mfg["params"], "eligibility": ""}).json()["results"]]
        assert b in ids and a not in ids


def test_sync_option_uses_titles(monkeypatch):
    seen = []
    real = httpx.Client

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"totalRecords": 0, "opportunitiesData": []})

    monkeypatch.setattr(sam_gov.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
    with TestClient(app) as c:
        r = c.post("/api/sync/sam", json={"days_back": 3, "option": "navy-nuclear"}).json()
        assert r["queries"] == len(presets.NAVY_NUCLEAR_SYNC_TITLES)
        assert [s.get("title") for s in seen] == presets.NAVY_NUCLEAR_SYNC_TITLES
        assert all("ncode" not in s for s in seen)
        seen.clear()
        r = c.post("/api/sync/sam", json={"days_back": 3, "option": "services"}).json()
        assert [s["ncode"] for s in seen] == presets.NAICS_GROUPS["services"]["codes"]
        assert c.post("/api/sync/sam", json={"option": "nope"}).status_code == 400
