from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient

from app import config
from app.connectors import sam_entity
from app.main import app

_REAL_CLIENT = httpx.Client


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


ENTITY = {
    "entityRegistration": {"ueiSAM": "ABCDEF123456", "cageCode": "1A2B3", "legalBusinessName": "Harbor Precision Machining LLC",
                           "dbaName": None, "registrationExpirationDate": "2027-05-01"},
    "coreData": {
        "entityInformation": {"entityURL": "http://harborprecision.example"},
        "physicalAddress": {"city": "Groton", "stateOrProvinceCode": "CT"},
        "generalInformation": {"organizationStructureCode": "MF"},
        "businessTypes": {
            "businessTypeList": [{"businessTypeCode": "2X"}, {"businessTypeCode": "QF"}, {"businessTypeCode": "A5"}],
            "sbaBusinessTypeList": [{"sbaBusinessTypeCode": "XX", "sbaBusinessTypeDesc": "HUBZone"}],
        },
    },
    "assertions": {"goodsAndServices": {"primaryNaics": "332710", "naicsList": [
        {"naicsCode": "332710", "sbaSmallBusiness": "Y"}, {"naicsCode": "335931", "sbaSmallBusiness": "Y"}]}},
    "pointsOfContact": {"governmentBusinessPOC": {"firstName": "Pat", "lastName": "Rivera", "title": "Owner"}},
}


def _client(calls, payload=None, status=200):
    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(status, json=payload if payload is not None else {
            "totalRecords": 11, "entityData": [ENTITY], "links": {"selfLink": "x", "nextLink": "y"}})
    return _REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_org_contact_interaction_crud():
    with TestClient(app) as c:
        r = c.post("/api/crm/organizations", json={"name": "CRUD Test Shop", "kind": "vendor", "state": "ct", "tags": ["machining"]})
        assert r.status_code == 200, r.text
        org = r.json()
        oid = org["id"]
        assert org["state"] == "CT" and org["stage"] == "identified"
        assert c.post("/api/crm/organizations", json={"name": "Bad", "kind": "nope"}).status_code == 422

        r = c.put(f"/api/crm/organizations/{oid}", json={"stage": "contacted", "notes": "Sent capability statement"})
        assert r.json()["stage"] == "contacted"

        assert any(o["id"] == oid for o in c.get("/api/crm/organizations", params={"kind": "vendor"}).json())
        assert not any(o["id"] == oid for o in c.get("/api/crm/organizations", params={"kind": "prime"}).json())
        assert any(o["id"] == oid for o in c.get("/api/crm/organizations", params={"q": "capability"}).json())
        assert any(o["id"] == oid for o in c.get("/api/crm/organizations", params={"tag": "Machining"}).json())
        assert not any(o["id"] == oid for o in c.get("/api/crm/organizations", params={"stage": "active"}).json())

        ct = c.post(f"/api/crm/organizations/{oid}/contacts", json={"name": "Dana Lee", "email": "dana@example.com"}).json()
        assert c.put(f"/api/crm/organizations/{oid}/contacts/{ct['id']}", json={"title": "Buyer"}).json()["title"] == "Buyer"

        it = c.post(f"/api/crm/organizations/{oid}/interactions", json={
            "kind": "call", "summary": "Intro call", "next_step": "Send quote", "follow_up_date": _d(3), "contact_id": ct["id"]}).json()
        assert it["date"] == date.today().isoformat() and it["contact_id"] == ct["id"]
        assert c.post(f"/api/crm/organizations/{oid}/interactions", json={"follow_up_date": "10/1/2026"}).status_code == 422

        full = c.get(f"/api/crm/organizations/{oid}").json()
        assert full["contacts"][0]["name"] == "Dana Lee"
        assert full["interactions"][0]["summary"] == "Intro call"
        assert full["next_follow_up"] == _d(3)

        assert c.put(f"/api/crm/interactions/{it['id']}", json={"done": True}).json()["done"] is True
        assert c.get(f"/api/crm/organizations/{oid}").json()["next_follow_up"] == ""

        assert c.delete(f"/api/crm/organizations/{oid}/contacts/{ct['id']}").status_code == 200
        assert c.get(f"/api/crm/interactions", params={"organization_id": oid}).json()[0]["contact_id"] is None
        assert c.delete(f"/api/crm/interactions/{it['id']}").status_code == 200
        assert c.delete(f"/api/crm/organizations/{oid}").status_code == 200
        assert c.get(f"/api/crm/organizations/{oid}").status_code == 404


def test_follow_ups_order_and_overdue():
    from app.crm_api import open_follow_ups
    from app.db import SessionLocal

    with TestClient(app) as c:
        oid = c.post("/api/crm/organizations", json={"name": "Follow Up Org"}).json()["id"]
        later = c.post(f"/api/crm/organizations/{oid}/interactions", json={"summary": "later", "follow_up_date": _d(10)}).json()
        far = c.post(f"/api/crm/organizations/{oid}/interactions", json={"summary": "far", "follow_up_date": _d(60)}).json()
        late = c.post(f"/api/crm/organizations/{oid}/interactions", json={"summary": "late", "follow_up_date": _d(-2)}).json()
        done = c.post(f"/api/crm/organizations/{oid}/interactions", json={"summary": "done", "follow_up_date": _d(-5), "done": True}).json()
        c.post(f"/api/crm/organizations/{oid}/interactions", json={"summary": "no date"})

        fu = [x for x in c.get("/api/crm/follow-ups", params={"within_days": 14}).json() if x["organization_id"] == oid]
        assert [x["id"] for x in fu] == [late["id"], later["id"]]
        assert fu[0]["overdue"] is True and fu[1]["overdue"] is False
        assert fu[0]["organization"] == "Follow Up Org"
        assert set(fu[0]) >= {"id", "organization_id", "organization", "summary", "next_step", "follow_up_date", "overdue"}

        db = SessionLocal()
        try:
            ids = [x["id"] for x in open_follow_ups(db) if x["organization_id"] == oid]
        finally:
            db.close()
        assert ids == [late["id"], later["id"], far["id"]]
        assert done["id"] not in ids
        c.delete(f"/api/crm/organizations/{oid}")


def test_seed_idempotent():
    with TestClient(app) as c:
        first = c.post("/api/crm/seed").json()
        second = c.post("/api/crm/seed").json()
        assert second["added"] == 0
        assert second["skipped"] == first["added"] + first["skipped"]
        orgs = c.get("/api/crm/organizations").json()
        names = [o["name"] for o in orgs]
        assert len(names) == len(set(names))
        nnl = next(o for o in orgs if o["name"].startswith("Naval Nuclear Laboratory"))
        assert nnl["kind"] == "prime" and "conflict" in nnl["notes"]
        assert any(o["kind"] == "apex_sbdc" and "napex.us" in o["website"] for o in orgs)


def test_entity_search_params_and_normalize():
    calls = []
    res = sam_entity.search(naics="332710", state="ct", business_type="sdvosb", q="harbor", page=1,
                            api_key="k", client=_client(calls))
    p = calls[0].url.params
    assert str(calls[0].url).startswith("https://api.sam.gov/entity-information/v3/entities")
    assert p["api_key"] == "k" and p["registrationStatus"] == "A"
    assert p["naicsCode"] == "332710" and p["physicalAddressProvinceOrStateCode"] == "CT"
    assert p["businessTypeCode"] == "QF" and p["legalBusinessName"] == "harbor"
    assert p["page"] == "1" and p["size"] == "10"
    assert "assertions" in p["includeSections"] and "pointsOfContact" in p["includeSections"]
    assert res["total"] == 11 and res["has_more"] is True

    n = res["results"][0]
    assert n["uei"] == "ABCDEF123456" and n["cage"] == "1A2B3" and n["name"] == "Harbor Precision Machining LLC"
    assert n["city"] == "Groton" and n["state"] == "CT" and n["website"] == "http://harborprecision.example"
    assert n["primary_naics"] == "332710" and n["naics_codes"] == ["332710", "335931"]
    assert n["business_types"] == {"SB": True, "SDVOSB": True, "VOSB": True, "WOSB": False, "HUBZone": True, "8A": False}
    assert n["is_manufacturer"] is True
    assert n["poc"]["name"] == "Pat Rivera" and n["poc"]["email"] == ""

    calls.clear()
    sam_entity.search(naics="332710", business_type="hubzone", api_key="k", client=_client(calls))
    assert calls[0].url.params["sbaBusinessTypeCode"] == "XX"
    calls.clear()
    sam_entity.search(naics="332710", business_type="8a", api_key="k", client=_client(calls))
    assert calls[0].url.params["sbaBusinessTypeCode"] == "A6"
    calls.clear()
    sam_entity.search(naics="332710", business_type="small", api_key="k", client=_client(calls))
    assert calls[0].url.params["naicsLimitedSB"] == "332710" and "naicsCode" not in calls[0].url.params

    try:
        sam_entity.search(business_type="small", state="CT", api_key="k", client=_client([]))
        assert False
    except sam_entity.EntityApiError:
        pass
    try:
        sam_entity.search(naics="332710", api_key="k", client=_client([], payload={"message": "limit"}, status=429))
        assert False
    except sam_entity.EntityApiError as e:
        assert "limit" in str(e)


def test_missing_key(monkeypatch):
    monkeypatch.setattr(config, "SAM_API_KEY", "")
    try:
        sam_entity.search(naics="332710")
        assert False, "should raise"
    except sam_entity.EntityApiError as e:
        assert "SAM_API_KEY" in str(e)
    with TestClient(app) as c:
        r = c.get("/api/crm/teaming/search", params={"naics": "332710"})
        assert r.status_code == 400 and "SAM_API_KEY" in r.json()["detail"]


def test_teaming_search_endpoint_and_save_upsert(monkeypatch):
    calls = []
    monkeypatch.setattr(sam_entity.httpx, "Client", lambda **kw: _client(calls))
    with TestClient(app) as c:
        r = c.get("/api/crm/teaming/search", params={"naics": "332710", "business_type": "sdvosb"})
        assert r.status_code == 200, r.text
        ent = r.json()["results"][0]
        assert "saved_id" not in ent

        s1 = c.post("/api/crm/teaming/save", json={"entity": ent}).json()
        assert s1["created"] is True
        org = s1["organization"]
        assert org["kind"] == "teaming_partner" and org["source"] == "sam_entity" and org["uei"] == "ABCDEF123456"
        assert org["business_types"]["SDVOSB"] is True and org["is_manufacturer"] is True
        assert org["contacts"][0]["name"] == "Pat Rivera"

        ent2 = dict(ent, city="New London")
        s2 = c.post("/api/crm/teaming/save", json={"entity": ent2, "kind": "vendor"}).json()
        assert s2["created"] is False and s2["organization"]["id"] == org["id"]
        assert s2["organization"]["kind"] == "vendor" and s2["organization"]["city"] == "New London"
        assert len(s2["organization"]["contacts"]) == 1
        assert sum(1 for o in c.get("/api/crm/organizations").json() if o["uei"] == "ABCDEF123456") == 1

        r = c.get("/api/crm/teaming/search", params={"naics": "332710"}).json()
        assert r["results"][0]["saved_id"] == org["id"]
        assert c.post("/api/crm/teaming/save", json={"entity": ent, "kind": "bogus"}).status_code == 422
        c.delete(f"/api/crm/organizations/{org['id']}")
