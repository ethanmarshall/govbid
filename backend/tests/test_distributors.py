import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import distributors
from app.db import SessionLocal, init_db
from app.main import app
from app.models_quote_tools import DistributorCache


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    init_db()
    for k in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET", "MOUSER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(distributors.time, "sleep", lambda s: None)
    distributors._clear_token()
    with SessionLocal() as db:
        db.query(DistributorCache).delete()
        db.commit()
    yield
    distributors._clear_token()


DK_PRODUCT = {
    "ManufacturerProductNumber": "LM358DR",
    "Manufacturer": {"Id": 296, "Name": "Texas Instruments"},
    "Description": {"ProductDescription": "IC OPAMP GP 2 CIRCUIT 8SOIC", "DetailedDescription": "General Purpose Amplifier"},
    "QuantityAvailable": 5000,
    "ProductUrl": "https://www.digikey.com/en/products/detail/texas-instruments/LM358DR/1",
    "UnitPrice": 0.5,
    "ManufacturerLeadWeeks": "6",
    "ProductVariations": [
        {"DigiKeyProductNumber": "296-1014-1-ND", "PackageType": {"Id": 2, "Name": "Cut Tape (CT)"},
         "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.50, "TotalPrice": 0.5},
                             {"BreakQuantity": 10, "UnitPrice": 0.30, "TotalPrice": 3.0},
                             {"BreakQuantity": 100, "UnitPrice": 0.20, "TotalPrice": 20.0}],
         "QuantityAvailableforPackageType": 500, "MinimumOrderQuantity": 1},
        {"DigiKeyProductNumber": "296-1014-2-ND", "PackageType": {"Id": 1, "Name": "Tape & Reel (TR)"},
         "StandardPricing": [{"BreakQuantity": 2500, "UnitPrice": 0.08, "TotalPrice": 200.0}],
         "QuantityAvailableforPackageType": 5000, "MinimumOrderQuantity": 2500},
    ],
}


def _digikey_client(calls):
    def handler(req: httpx.Request):
        calls.append(req)
        if req.url.path == "/v1/oauth2/token":
            form = dict(x.split("=") for x in req.content.decode().split("&"))
            assert form == {"client_id": "dk-id", "client_secret": "dk-secret", "grant_type": "client_credentials"}
            assert req.headers["content-type"].startswith("application/x-www-form-urlencoded")
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 599, "token_type": "Bearer"})
        assert req.method == "POST" and str(req.url) == "https://api.digikey.com/products/v4/search/keyword"
        assert req.headers["authorization"] == "Bearer tok-1"
        assert req.headers["x-digikey-client-id"] == "dk-id"
        assert req.headers["x-digikey-locale-currency"] == "USD" and req.headers["x-digikey-locale-site"] == "US"
        body = json.loads(req.content)
        assert body["Limit"] == 10 and body["Offset"] == 0
        if body["Keywords"] == "LM358DR":
            return httpx.Response(200, json={"Products": [DK_PRODUCT], "ProductsCount": 1, "ExactMatches": [DK_PRODUCT]})
        return httpx.Response(200, json={"Products": [], "ProductsCount": 0, "ExactMatches": []})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_not_configured_makes_no_calls():
    def handler(req):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP call expected")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = distributors.price_bom([{"mpn": "LM358DR", "qty": 2}], [5], client=client)
    assert out["configured"] == {"digikey": False, "mouser": False}
    assert out["results"][0]["best"] is None and out["results"][0]["offers"] == []
    with TestClient(app) as c:
        assert c.get("/api/distributors/status").json()["configured"] == {"digikey": False, "mouser": False}
        r = c.post("/api/distributors/price-bom", json={"lines": [{"mpn": "LM358DR", "qty": 1}]}).json()
        assert r["configured"]["mouser"] is False and r["results"][0]["best"] is None
        assert c.get("/api/distributors/search", params={"q": "LM358DR"}).json()["offers"] == []


def test_digikey_lookup_price_breaks_and_cache(monkeypatch):
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "dk-id")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "dk-secret")
    calls = []
    client = _digikey_client(calls)
    out = distributors.price_bom([{"mpn": "LM358DR", "manufacturer": "Texas Instruments", "qty": 2}, {"mpn": "NOPE123", "qty": 1}],
                                 [5, 100], client=client)
    assert out["configured"] == {"digikey": True, "mouser": False}
    first, missing = out["results"]
    assert len(first["offers"]) == 2
    best = first["best"]  # 2 per build x 5 builds = 10 at the 10-piece break
    assert best["distributor"] == "digikey" and best["need_qty"] == 10
    assert best["unit_price"] == 0.30 and best["qty_break"] == 10 and best["extended_price"] == 3.0
    assert best["stock"] == 500 and best["stock_ok"] and best["lead_weeks"] == 6
    assert best["url"].startswith("https://www.digikey.com/") and best["description"].startswith("IC OPAMP")
    at200 = first["by_quantity"][1]["best"]  # 200 needed: cut tape at the 100 break
    assert at200["need_qty"] == 200 and at200["unit_price"] == 0.20 and at200["extended_price"] == 40.0
    assert missing["best"] is None and "Not found" in missing["error"]
    n_token = sum(1 for c in calls if c.url.path == "/v1/oauth2/token")
    assert n_token == 1  # token reused for both searches
    # second run comes from the 24 h cache (the miss is cached too)
    before = len(calls)
    again = distributors.price_bom([{"mpn": "lm358dr", "qty": 2}], [5], client=client)
    assert len(calls) == before and again["results"][0]["best"]["unit_price"] == 0.30


def test_digikey_sign_in_failure_is_reported(monkeypatch):
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "dk-id")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "bad")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "invalid_client"})))
    out = distributors.price_bom([{"mpn": "LM358DR", "qty": 1}], client=client)
    assert out["results"][0]["best"] is None and "sign-in failed" in out["results"][0]["error"]
    with SessionLocal() as db:  # errors are not cached
        assert db.query(DistributorCache).count() == 0


def _mouser_part(mpn, price="$1.20", stock="250", lead="84 Days"):
    return {"ManufacturerPartNumber": mpn, "Manufacturer": "Acme Semi", "Description": f"Part {mpn}", "MouserPartNumber": f"595-{mpn}",
            "Availability": f"{stock} In Stock", "AvailabilityInStock": stock, "LeadTime": lead,
            "ProductDetailUrl": f"https://www.mouser.com/ProductDetail/{mpn}", "Min": "1", "Mult": "1",
            "PriceBreaks": [{"Quantity": 1, "Price": price, "Currency": "USD"}, {"Quantity": 100, "Price": "$0.90", "Currency": "USD"}]}


def test_mouser_batches_ten_per_call(monkeypatch):
    monkeypatch.setenv("MOUSER_API_KEY", "mk-1")
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        assert req.method == "POST" and req.url.path == "/api/v1/search/partnumber" and req.url.host == "api.mouser.com"
        assert req.url.params["apiKey"] == "mk-1"
        body = json.loads(req.content)["SearchByPartRequest"]
        assert body["partSearchOptions"] == "Exact"
        mpns = body["mouserPartNumber"].split("|")
        assert len(mpns) <= 10
        parts = [_mouser_part(m) for m in mpns if m != "GONE999"]
        return httpx.Response(200, json={"Errors": [], "SearchResults": {"NumberOfResult": len(parts), "Parts": parts}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    lines = [{"mpn": f"PN{i:04d}", "qty": 1} for i in range(11)] + [{"mpn": "GONE999", "qty": 1}]
    out = distributors.price_bom(lines, client=client)
    assert len(calls) == 2  # 12 part numbers in two batches
    assert out["configured"] == {"digikey": False, "mouser": True}
    b = out["results"][0]["best"]
    assert b["distributor"] == "mouser" and b["unit_price"] == 1.20 and b["stock"] == 250 and b["lead_weeks"] == 12.0
    assert b["url"] == "https://www.mouser.com/ProductDetail/PN0000"
    assert out["results"][-1]["best"] is None


def test_choose_best_rules():
    cheap_low_stock = {"distributor": "mouser", "mpn": "X", "stock": 5, "min_qty": 1, "lead_weeks": 10,
                       "price_breaks": [{"qty": 1, "unit_price": 1.0}]}
    pricey_stocked = {"distributor": "digikey", "mpn": "X", "stock": 1000, "min_qty": 1,
                      "price_breaks": [{"qty": 1, "unit_price": 1.5}, {"qty": 10, "unit_price": 0.5}]}
    best = distributors.choose_best([cheap_low_stock, pricey_stocked], 9)
    # ordering 10 at the 10 break ($5.00) beats 9 at $1.50 and the low-stock offer
    assert best["distributor"] == "digikey" and best["order_qty"] == 10 and best["extended_price"] == 5.0 and best["stock_ok"]
    none_enough = distributors.choose_best([cheap_low_stock, {**pricey_stocked, "stock": 3}], 50)
    assert not none_enough["stock_ok"] and "in stock" in none_enough["note"]
    assert distributors.choose_best([], 5) is None
    # minimum order quantity is respected
    reel = {"distributor": "digikey", "mpn": "X", "stock": 9000, "min_qty": 2500, "price_breaks": [{"qty": 2500, "unit_price": 0.08}]}
    assert distributors.cost_at(reel, 10)["order_qty"] == 2500


def test_number_parsing():
    assert distributors._num("$1,234.50") == 1234.5
    assert distributors._num("0,45 €") == 0.45
    assert distributors._num("1,000") == 1000
    assert distributors._lead_from_text("84 Days") == 12.0
    assert distributors._lead_from_text("6 Weeks") == 6
    assert distributors._lead_from_text("") is None


def test_endpoint_uses_live_client(monkeypatch):
    monkeypatch.setenv("MOUSER_API_KEY", "mk-2")
    handler = lambda req: httpx.Response(200, json={"Errors": [], "SearchResults": {"NumberOfResult": 1, "Parts": [_mouser_part("ABC123")]}})  # noqa: E731
    monkeypatch.setattr(distributors, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with TestClient(app) as c:
        r = c.post("/api/distributors/price-bom", json={"lines": [{"mpn": "ABC123", "qty": 3}], "quantities": [40]}).json()
        best = r["results"][0]["best"]
        assert best["need_qty"] == 120 and best["unit_price"] == 0.90 and best["extended_price"] == 108.0
        s = c.get("/api/distributors/search", params={"q": "ABC123"}).json()
        assert s["offers"][0]["distributor_pn"] == "595-ABC123"
