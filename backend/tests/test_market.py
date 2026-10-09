import json
import threading
from datetime import date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import market_api
from app.connectors import usaspending_market as usm
from app.db import SessionLocal, init_db
from app.main import app
from app.models_crm import Interaction, Organization
from app.models_market import MarketCache, TrackedRecompete

TODAY = date(2026, 10, 9)


def _award(gid, end, amount=100000.0, start="2025-01-01", recipient="ACME MACHINE"):
    return {"internal_id": 1, "Award ID": gid.split("_")[2], "Recipient Name": recipient, "Recipient UEI": "ABC123DEF456",
            "Award Amount": amount, "Start Date": start, "End Date": end, "Awarding Agency": "Department of Defense",
            "Awarding Sub Agency": "Department of the Navy", "Contract Award Type": "PURCHASE ORDER",
            "NAICS": {"code": "332710", "description": "MACHINE SHOPS"}, "PSC": {"code": "5340", "description": "HARDWARE"},
            "Description": "PARTS", "Last Modified Date": "2026-01-02 10:00:00", "generated_internal_id": gid}


DETAIL = {
    "generated_unique_award_id": "CONT_AWD_N1_9700_-NONE-_-NONE-", "piid": "N1", "type_description": "PURCHASE ORDER",
    "description": "PARTS", "total_obligation": 100000.0, "base_and_all_options": 250000.0,
    "awarding_agency": {"toptier_agency": {"name": "Department of Defense"}, "subtier_agency": {"name": "Department of the Navy"},
                        "office_agency_name": "NUWC DIV NEWPORT"},
    "period_of_performance": {"start_date": "2025-01-01", "end_date": "2027-06-30", "potential_end_date": "2029-06-30 00:00:00"},
    "latest_transaction_contract_data": {"type_set_aside": "SDVOSBC", "type_set_aside_description": "SERVICE DISABLED VETERAN OWNED SMALL BUSINESS SET-ASIDE",
                                         "extent_competed": "A", "extent_competed_description": "FULL AND OPEN COMPETITION",
                                         "number_of_offers_received": "3", "solicitation_identifier": "N1-SOL",
                                         "solicitation_procedures_description": "NEGOTIATED PROPOSAL/QUOTE"},
    "parent_award": None, "place_of_performance": {"city_name": "NEWPORT", "state_code": "RI"},
}


class Recorder:
    """httpx MockTransport handler that records (method, path, body) and answers like USAspending."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request):
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        with self.lock:
            self.calls.append((request.method, path, body))
        if path == "/api/v2/search/spending_by_award/":
            f = body["filters"]
            if body["sort"] == "Award Amount":
                return httpx.Response(200, json={"results": [_award("CONT_AWD_N1_9700_-NONE-_-NONE-", "2027-06-30", 900000),
                                                             _award("CONT_AWD_N2_9700_-NONE-_-NONE-", "2027-01-01", 100000)],
                                                 "page_metadata": {"page": 1, "hasNext": False}})
            if "naics_codes" in f:
                if body["page"] == 1:
                    rows = [_award("CONT_AWD_FAR_9700_-NONE-_-NONE-", "2030-01-01"),  # after window
                            _award("CONT_AWD_N1_9700_-NONE-_-NONE-", "2027-06-30", 500000),
                            _award("CONT_AWD_N2_9700_-NONE-_-NONE-", "2027-05-01", 50000)]
                    return httpx.Response(200, json={"results": rows, "page_metadata": {"page": 1, "hasNext": True}})
                rows = [_award("CONT_AWD_N3_9700_-NONE-_-NONE-", "2027-04-10"),  # in window
                        _award("CONT_AWD_OLD_9700_-NONE-_-NONE-", "2027-03-01")]  # before window: stop paging
                return httpx.Response(200, json={"results": rows, "page_metadata": {"page": 2, "hasNext": True}})
            # PSC search: duplicates N1 plus one new
            rows = [_award("CONT_AWD_N1_9700_-NONE-_-NONE-", "2027-06-30", 500000),
                    _award("CONT_AWD_P1_9700_-NONE-_-NONE-", "2028-04-01", 75000)]
            return httpx.Response(200, json={"results": rows, "page_metadata": {"page": 1, "hasNext": False}})
        if path.startswith("/api/v2/awards/"):
            return httpx.Response(200, json=DETAIL)
        if path == "/api/v2/search/spending_over_time/":
            sa = body["filters"].get("set_aside_type_codes")
            scale = 1.0 if not sa else (0.1 if sa == usm.SDVOSB_SET_ASIDES else 0.4)
            return httpx.Response(200, json={"group": "fiscal_year", "results": [
                {"time_period": {"fiscal_year": str(fy)}, "aggregated_amount": 1000000 * scale * (fy - 2023), "Contract_Obligations": 1000000 * scale * (fy - 2023)}
                for fy in (2024, 2025, 2026)]})
        if path == "/api/v2/search/spending_by_award_count/":
            sa = body["filters"].get("set_aside_type_codes")
            n = 100 if not sa else (5 if sa == usm.SDVOSB_SET_ASIDES else 40)
            if body["filters"].get("agencies"):
                n = 30
            return httpx.Response(200, json={"results": {"contracts": n, "idvs": 0, "grants": 0}})
        if path == "/api/v2/search/spending_by_category/awarding_subagency/":
            return httpx.Response(200, json={"category": "awarding_subagency", "results": [
                {"name": "Department of the Navy", "code": "USN", "agency_name": "Department of Defense", "amount": 4000000},
                {"name": "Defense Logistics Agency", "code": "DLA", "agency_name": "Department of Defense", "amount": 2000000}],
                "page_metadata": {"page": 1, "hasNext": False}})
        if path == "/api/v2/search/spending_by_category/recipient/":
            return httpx.Response(200, json={"category": "recipient", "results": [
                {"name": "ACME MACHINE", "uei": "ABC123DEF456", "recipient_id": "x-C", "amount": 1500000}],
                "page_metadata": {"page": 1, "hasNext": False}})
        return httpx.Response(404, text="not found")


@pytest.fixture
def usa(monkeypatch):
    rec = Recorder()
    real_client = httpx.Client
    monkeypatch.setattr(usm.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(rec)))
    monkeypatch.setattr(market_api, "_today", lambda: TODAY)
    init_db()
    with SessionLocal() as db:
        db.query(MarketCache).delete()
        db.query(TrackedRecompete).delete()
        db.commit()
    return rec


# ------------------------------------------------------------------ pure functions
def test_window_and_fiscal_year_math():
    assert usm.recompete_window(TODAY) == (date(2027, 4, 9), date(2028, 4, 9))
    assert usm.recompete_window(date(2026, 8, 31), 6, 18) == (date(2027, 2, 28), date(2028, 2, 29))
    assert usm.recompete_window(TODAY, 18, 6) == (date(2027, 4, 9), date(2028, 4, 9))
    assert usm.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert usm.fiscal_year(date(2026, 10, 1)) == 2027 and usm.fiscal_year(date(2026, 9, 30)) == 2026
    assert usm.fy_bounds(2026) == (date(2025, 10, 1), date(2026, 9, 30))
    assert usm.last_complete_fys(TODAY, 3) == [2024, 2025, 2026]
    assert usm.last_complete_fys(date(2026, 9, 30), 2) == [2024, 2025]
    assert usm.fsc_prefixes(["5340", "5340-01-123-4567", "4730011234567", "x"]) == ["5340", "4730"]


def test_filters_shape():
    f = usm.base_filters(naics=["332710"], start=date(2000, 1, 1), end=TODAY, agency="Department of Defense",
                         sub_agency="Department of the Navy", set_asides=["SDVOSBC"], min_value=25000)
    assert f["award_type_codes"] == ["A", "B", "C", "D"]
    assert f["time_period"] == [{"start_date": "2007-10-01", "end_date": "2026-10-09"}]
    assert f["agencies"] == [{"type": "awarding", "tier": "subtier", "name": "Department of the Navy", "toptier_name": "Department of Defense"}]
    assert f["award_amounts"] == [{"lower_bound": 25000.0}] and f["set_aside_type_codes"] == ["SDVOSBC"]
    assert "psc_codes" not in f


# ------------------------------------------------------------------ recompetes
def test_recompete_search_bodies_window_and_cache(usa):
    with TestClient(app) as c:
        r = c.post("/api/market/recompetes", json={"naics": ["332710"], "psc": ["5340"], "set_aside": "sdvosb", "min_value": 10000})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["window"] == {"start": "2027-04-09", "end": "2028-04-09"}
        ids = [x["award_id"] for x in d["results"]]
        assert ids == ["N3", "N2", "N1", "P1"]  # sorted by end date, deduped, out-of-window dropped
        assert d["results"][0]["url"] == "https://www.usaspending.gov/award/CONT_AWD_N3_9700_-NONE-_-NONE-"
        assert d["truncated"] is False and d["as_of"].endswith("Z")
        award_calls = [b for m, p, b in usa.calls if p == "/api/v2/search/spending_by_award/"]
        assert len(award_calls) == 3  # naics pages 1-2 (stops once below window), psc page 1
        b = award_calls[0]
        assert b["sort"] == "End Date" and b["order"] == "desc" and b["limit"] == 100 and b["page"] == 1
        assert "End Date" in b["fields"] and "generated_internal_id" in b["fields"]
        assert b["filters"]["naics_codes"] == ["332710"] and "psc_codes" not in b["filters"]
        assert b["filters"]["set_aside_type_codes"] == ["SDVOSBC", "SDVOSBS"]
        assert b["filters"]["award_amounts"] == [{"lower_bound": 10000.0}]
        assert b["filters"]["time_period"] == [{"start_date": "2021-10-10", "end_date": "2026-10-09"}]
        assert award_calls[1]["page"] == 2
        assert award_calls[2]["filters"]["psc_codes"] == ["5340"] and "naics_codes" not in award_calls[2]["filters"]

        # second identical call is served from cache
        n = len(usa.calls)
        r2 = c.post("/api/market/recompetes", json={"naics": ["332710"], "psc": ["5340"], "set_aside": "sdvosb", "min_value": 10000})
        assert r2.json()["results"] == d["results"] and len(usa.calls) == n
        # refresh bypasses the cache
        c.post("/api/market/recompetes", json={"naics": ["332710"], "psc": ["5340"], "set_aside": "sdvosb", "min_value": 10000, "refresh": True})
        assert len(usa.calls) == n + 3


def test_cache_expires_after_24_hours(usa):
    with SessionLocal() as db:
        f = market_api.CachedFetcher(db)
        req = ("GET", "/awards/CONT_AWD_N1_9700_-NONE-_-NONE-/", None)
        f.many([req, req])
        assert f.network_calls == 1  # identical requests deduped
        row = db.query(MarketCache).one()
        assert row.key == market_api.cache_key(*req)
        row.fetched_at = datetime.utcnow() - timedelta(hours=25)
        db.commit()
        f2 = market_api.CachedFetcher(db)
        f2.many([req])
        assert f2.network_calls == 1 and db.query(MarketCache).count() == 1
        f3 = market_api.CachedFetcher(db)
        f3.many([req])
        assert f3.network_calls == 0
        f.close(); f2.close(); f3.close()
    assert market_api.cache_key("POST", "/x/", {"a": 1, "b": 2}) == market_api.cache_key("POST", "/x/", {"b": 2, "a": 1})


def test_recompetes_defaults_from_profile_and_validation(usa):
    with TestClient(app) as c:
        c.put("/api/profile", json={"naics_codes": ["332710"], "psc_codes": [], "nsn_watchlist": ["5340-01-123-4567"]})
        d = c.get("/api/market/defaults").json()
        assert d["naics"] == ["332710"] and d["psc"] == ["5340"] and d["window"]["start"] == "2027-04-09"
        r = c.post("/api/market/recompetes", json={})
        assert r.status_code == 200
        assert any(b["filters"].get("psc_codes") == ["5340"] for m, p, b in usa.calls if b)
        r = c.post("/api/market/recompetes", json={"naics": [], "psc": []})
        assert r.status_code == 400


def test_award_detail(usa):
    with TestClient(app) as c:
        d = c.get("/api/market/award/CONT_AWD_N1_9700_-NONE-_-NONE-").json()
        assert d["office"] == "NUWC DIV NEWPORT" and d["set_aside_code"] == "SDVOSBC" and d["offers"] == "3"
        assert d["extent_competed"] == "FULL AND OPEN COMPETITION" and d["potential_end_date"] == "2029-06-30"
        assert d["place"] == "NEWPORT, RI"
        assert usa.calls[-1][:2] == ("GET", "/api/v2/awards/CONT_AWD_N1_9700_-NONE-_-NONE-/")


# ------------------------------------------------------------------ tracking, CRM, hooks
def test_tracking_crm_calendar_dashboard(usa):
    with TestClient(app) as c:
        soon = (TODAY + timedelta(days=90)).isoformat()
        r = c.post("/api/market/tracked", json={"generated_internal_id": "CONT_AWD_N1_9700_-NONE-_-NONE-", "award_id": "N1",
                                                "recipient": "ACME MACHINE", "end_date": soon, "sub_agency": "Department of the Navy",
                                                "notes": "Call the CO", "reminder_date": "2026-11-01"})
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["days_left"] == 90 and t["url"].endswith("CONT_AWD_N1_9700_-NONE-_-NONE-")
        assert c.post("/api/market/tracked", json={"generated_internal_id": "CONT_AWD_N1_9700_-NONE-_-NONE-"}).json()["already"]
        far = c.post("/api/market/tracked", json={"generated_internal_id": "CONT_AWD_P1_9700_-NONE-_-NONE-", "award_id": "P1",
                                                  "end_date": "2028-04-01"}).json()
        assert c.put(f"/api/market/tracked/{t['id']}", json={"status": "bogus"}).status_code == 400
        assert c.put(f"/api/market/tracked/{t['id']}", json={"reminder_date": "11/01/2026"}).status_code == 400

        # search marks tracked rows
        res = c.post("/api/market/recompetes", json={"naics": ["332710"], "psc": []}).json()
        assert {x["award_id"]: x["tracked_id"] for x in res["results"]}["N1"] == t["id"]

        # detail fills office
        t2 = c.post(f"/api/market/tracked/{t['id']}/refresh-detail").json()
        assert t2["office"] == "NUWC DIV NEWPORT" and t2["set_aside"].startswith("SERVICE DISABLED")
        assert t2["end_date"] == "2027-06-30"
        c.put(f"/api/market/tracked/{t['id']}", json={"end_date": soon})

        with SessionLocal() as db:
            cal = market_api.calendar_items(db)
            uids = {i["uid"] for i in cal}
            assert f"recompete-rem-{t['id']}@govbid" in uids and f"recompete-end-{t['id']}@govbid" in uids
            assert f"recompete-end-{far['id']}@govbid" in uids
            assert all(isinstance(i["date"], date) for i in cal)
            dash = market_api.dashboard_items(db)
            assert len(dash) == 1 and "N1" in dash[0] and "NUWC DIV NEWPORT" in dash[0]

        # CRM: creates agency org once, logs interactions
        r = c.post(f"/api/market/tracked/{t['id']}/crm", json={"summary": "Introduced capabilities", "kind": "email",
                                                             "follow_up_date": "2026-11-15"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["created"] and out["organization"] == "NUWC DIV NEWPORT"
        out2 = c.post(f"/api/market/tracked/{t['id']}/crm", json={}).json()
        assert not out2["created"] and out2["organization_id"] == out["organization_id"]
        with SessionLocal() as db:
            org = db.get(Organization, out["organization_id"])
            assert org.kind == "agency"
            its = db.query(Interaction).filter(Interaction.organization_id == org.id).all()
            assert len(its) == 2 and any(i.summary == "Introduced capabilities" and i.kind == "email" for i in its)

        # linking an opportunity clears the dashboard alert; closed items leave the calendar
        opp = c.post("/api/opportunities", json={"title": "Machined parts recompete", "agency": "Navy"})
        assert opp.status_code == 200, opp.text
        oid = opp.json()["id"]
        assert any(o["id"] == oid for o in c.get("/api/market/opportunity-options?q=recompete").json())
        assert c.put(f"/api/market/tracked/{t['id']}", json={"opportunity_id": 999999}).status_code == 400
        c.put(f"/api/market/tracked/{t['id']}", json={"opportunity_id": oid})
        c.put(f"/api/market/tracked/{far['id']}", json={"status": "closed"})
        with SessionLocal() as db:
            assert market_api.dashboard_items(db) == []
            assert not any(i["uid"].endswith(f"-{far['id']}@govbid") for i in market_api.calendar_items(db))

        assert len(c.get("/api/market/tracked").json()) == 2
        assert c.delete(f"/api/market/tracked/{far['id']}").json()["ok"]
        assert c.put("/api/market/tracked/999999", json={}).status_code == 404


# ------------------------------------------------------------------ buyers
def test_buyer_analytics(usa):
    with TestClient(app) as c:
        r = c.post("/api/market/buyers", json={"naics": ["332710"], "psc": ["5340"], "years": 3})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["basis"] == "naics" and d["psc"] == [] and d["fiscal_years"] == [2024, 2025, 2026]
        assert d["range"] == {"start": "2023-10-01", "end": "2026-09-30"}
        y = {row["fiscal_year"]: row for row in d["years"]}
        assert y[2026]["obligations"] == 3000000 and y[2026]["awards"] == 100 and y[2026]["avg_award"] == 30000
        assert y[2024]["sdvosb_obligations"] == pytest.approx(100000) and y[2024]["sb_awards"] == 40
        t = d["totals"]
        assert t["obligations"] == 6000000 and t["awards"] == 300
        assert t["sb_share_dollars"] == pytest.approx(0.4) and t["sdvosb_share_awards"] == pytest.approx(0.05)
        assert d["sub_agencies"][0] == {"name": "Department of the Navy", "code": "USN", "agency": "Department of Defense",
                                        "amount": 4000000.0, "awards": 30, "avg_award": pytest.approx(4000000 / 30)}
        assert d["recipients"][0]["uei"] == "ABC123DEF456"

        bodies = [(p, b) for m, p, b in usa.calls]
        sot = [b for p, b in bodies if p == "/api/v2/search/spending_over_time/"]
        assert len(sot) == 3 and all(b["group"] == "fiscal_year" for b in sot)
        assert sot[0]["filters"]["naics_codes"] == ["332710"] and "psc_codes" not in sot[0]["filters"]
        assert sot[0]["filters"]["time_period"] == [{"start_date": "2023-10-01", "end_date": "2026-09-30"}]
        assert sorted(tuple(b["filters"].get("set_aside_type_codes") or []) for b in sot)[0] == ()
        counts = [b for p, b in bodies if p == "/api/v2/search/spending_by_award_count/"]
        assert {"start_date": "2025-10-01", "end_date": "2026-09-30"} in [b["filters"]["time_period"][0] for b in counts]
        sub_counts = [b for b in counts if b["filters"].get("agencies")]
        assert sub_counts[0]["filters"]["agencies"] == [{"type": "awarding", "tier": "subtier", "name": "Department of the Navy",
                                                         "toptier_name": "Department of Defense"}]
        cat = [b for p, b in bodies if p == "/api/v2/search/spending_by_category/awarding_subagency/"]
        assert cat[0]["limit"] == 10 and cat[0]["page"] == 1

        n = len(usa.calls)
        assert c.post("/api/market/buyers", json={"naics": ["332710"], "psc": ["5340"], "years": 3}).json()["years"] == d["years"]
        assert len(usa.calls) == n

        both = c.post("/api/market/buyers", json={"naics": ["332710"], "psc": ["5340"], "basis": "both"}).json()
        assert both["naics"] == ["332710"] and both["psc"] == ["5340"]
        assert c.post("/api/market/buyers", json={"naics": ["332710"], "basis": "x"}).status_code == 400

        o = c.post("/api/market/buyers/offices", json={"naics": ["332710"], "sample": 5}).json()
        assert o["sample_size"] == 2 and o["offices"][0]["office"] == "NUWC DIV NEWPORT"
        assert o["offices"][0]["awards"] == 2 and o["offices"][0]["amount"] == 1000000
        big = [b for m, p, b in usa.calls if p == "/api/v2/search/spending_by_award/" and b["sort"] == "Award Amount"]
        assert big[0]["limit"] == 5 and big[0]["order"] == "desc"


def test_upstream_error_is_502(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(usm.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))))
    with TestClient(app) as c:
        r = c.post("/api/market/buyers", json={"naics": ["999999"], "refresh": True})
        assert r.status_code == 502 and "500" in r.json()["detail"]
