"""Digi-Key list prices for 80/20 profiles and hardware, saved into the extrusion prices."""
import json

import httpx

from app import digikey, quotes


def _products(keywords):
    def prod(mpn, price, maker="80/20"):
        return {"ManufacturerProductNumber": mpn, "Manufacturer": {"Name": maker}, "ProductUrl": f"https://dk/{mpn}",
                "Description": {"ProductDescription": mpn}, "UnitPrice": price,
                "ProductVariations": [{"StandardPricing": [{"BreakQuantity": 1, "UnitPrice": price}, {"BreakQuantity": 10, "UnitPrice": price * 0.9}]}]}
    table = {"1515": [prod("1515-72", 36.0), prod("1515-145", 58.0), prod("1515-6", 9.0), prod("1515-72", 1.0, "Other Co")],
             "3360": [prod("3360", 2.1)], "4303": [prod("4303", 6.0)], "3320": [prod("3320", 0.9)]}
    return table.get(keywords, [])


def _transport():
    def handler(req: httpx.Request):
        if req.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 600})
        body = json.loads(req.content)
        return httpx.Response(200, json={"Products": _products(body["Keywords"])})
    return httpx.MockTransport(handler)


def test_profile_per_inch_and_part_price(monkeypatch):
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "x")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "y")
    c = digikey.Client(transport=_transport())
    p = digikey.profile_per_inch(c, "1515")
    assert p["bar"] == "1515-145" and abs(p["per_inch"] - 58 / 145) < 0.001  # cheapest per inch, other makers and short pieces ignored
    assert digikey.part_price(c, "3360")["price"] == 2.1
    assert digikey.part_price(c, "9999") is None


def test_refresh_saves_prices(monkeypatch):
    from app.db import SessionLocal, init_db

    init_db()
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "x")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "y")
    db = SessionLocal()
    before = quotes.get_overrides(db)
    try:
        r = digikey.refresh(db, digikey.Client(transport=_transport()), profiles=["1515"])
        cfg = quotes.get_config(db)["extrusion"]
        assert abs(cfg["prices"]["profiles"]["1515"] - 0.4) < 0.001
        assert cfg["prices"]["hardware"]["ANCHOR-15"] == 2.1
        assert abs(cfg["prices"]["hardware"]["BRKT-4H-15"] - (6.0 + 4 * 0.9)) < 0.001  # the bracket with its four screws and T-nuts
        assert cfg["price_source"]["source"] == "Digi-Key" and "Digi-Key" in cfg["note"]
        assert r["profiles"] == 1 and "2053" in r["missing"]
    finally:
        quotes.update_config(db, before, replace=True)
        db.close()
