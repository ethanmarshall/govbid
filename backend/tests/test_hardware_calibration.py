"""McMaster-Carr client (mocked: the real API needs an approved account), hardware matching and costing, calibration."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import calibration, hardware, mcmaster
from app.db import SessionLocal
from app.main import app
from app.models_hardware import CalibrationSample, HardwareItem

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True, scope="module")
def _tables():
    from app.db import init_db

    init_db()


def fake_mcmaster(subscribed: set):
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path))
        if req.url.path == "/v1/login":
            body = json.loads(req.content)
            if body["Password"] != "pw":
                return httpx.Response(401, json={"ErrorCode": "UNAUTHORIZED"})
            return httpx.Response(200, json={"AuthToken": "tok", "ExpirationTS": "2099-01-01"})
        assert req.headers.get("Authorization") == "Bearer tok"
        if req.method == "PUT" and req.url.path == "/v1/products":
            subscribed.add(json.loads(req.content)["URL"].rsplit("/", 1)[-1])
            return httpx.Response(201, json={})
        pn = req.url.path.split("/")[3]
        if pn not in subscribed:
            return httpx.Response(403, json={"ErrorCode": "NOT_SUBSCRIBED_TO_PRODUCT"})
        if req.url.path.endswith("/price"):
            return httpx.Response(200, json=[{"Amount": 9.12, "MinimumQuantity": 1, "UnitOfMeasure": "Pack of 100"},
                                             {"Amount": 8.20, "MinimumQuantity": 10, "UnitOfMeasure": "Pack of 100"}])
        return httpx.Response(200, json={"PartNumber": pn, "ProductStatus": "Active", "FamilyDescription": "Socket Head Screw, M5 x 10 mm"})

    return handler, calls


def test_mcmaster_client_subscribes_then_prices(monkeypatch):
    monkeypatch.setenv("MCMASTER_USERNAME", "me")
    monkeypatch.setenv("MCMASTER_PASSWORD", "pw")
    handler, calls = fake_mcmaster(set())
    c = mcmaster.Client(transport=httpx.MockTransport(handler))
    p = c.product("91290a115")
    assert p["part_number"] == "91290A115" and p["pack_qty"] == 100 and p["unit_price"] == pytest.approx(0.0912)
    assert ("PUT", "/v1/products") in calls  # subscribed because the first read said not subscribed
    assert "Socket Head" in p["description"]
    monkeypatch.setenv("MCMASTER_PASSWORD", "bad")
    with pytest.raises(mcmaster.McMasterError, match="not approved"):
        mcmaster.Client(transport=httpx.MockTransport(handler)).product("91290A115")
    with pytest.raises(mcmaster.McMasterError):
        c.product("not a part")


def test_part_numbers_found_in_names():
    assert mcmaster.part_numbers_in("91290A115_M5x10_SHCS") == ["91290A115"]
    assert mcmaster.part_numbers_in("bearing 5972K91 reference") == ["5972K91"]
    assert mcmaster.part_numbers_in("08_bearing_608_reference") == []
    assert mcmaster.pack_size("Pack of 25") == 25 and mcmaster.pack_size("Each") == 1


def test_library_match_and_pack_costing():
    db = SessionLocal()
    try:
        db.query(HardwareItem).delete()
        db.add(HardwareItem(part_number="5972K91", description="608 ball bearing", match="608 bearing", pack_price=6.50, pack_qty=1))
        db.add(HardwareItem(part_number="91290A115", description="M5 x 10 socket head screw", match="m5 x 10 socket head, m5x10 shcs",
                            pack_price=9.12, pack_qty=100, price_breaks=[{"min_qty": 1, "amount": 9.12}, {"min_qty": 3, "amount": 8.20}]))
        db.commit()
        it, _ = hardware.find(db, "08_bearing_608_reference")
        assert it.part_number == "5972K91"
        r = hardware.price_bought(db, "08_bearing_608_reference", 2)
        assert r["each"] == 6.50 and r["total"] == 13.0
        r = hardware.price_bought(db, "M5x10 SHCS", 4)
        assert r["total"] == 9.12 and r["packs"] == 1  # you buy a whole pack
        r = hardware.price_bought(db, "M5x10 SHCS", 240)
        assert r["packs"] == 3 and r["total"] == pytest.approx(24.60)  # the 3-pack break
        assert hardware.price_bought(db, "turbine wheel", 1)["found"] is False
    finally:
        db.query(HardwareItem).delete()
        db.commit()
        db.close()


def test_calibration_factors():
    db = SessionLocal()
    try:
        db.query(CalibrationSample).delete()
        db.commit()
        fs = calibration.factors(db)
        assert calibration.factor_for(fs, "cnc_mill") == (1.0, "")
        for tool, real in ((100, 120), (200, 250), (50, 60)):
            calibration.add(db, process="cnc_mill", tool_unit_price=tool, actual_unit_price=real, quantity=1)
        calibration.add(db, process="cnc_lathe", tool_unit_price=100, actual_unit_price=1000)  # one wild sample
        fs = calibration.factors(db)
        f, why = calibration.factor_for(fs, "cnc_mill")
        assert f == pytest.approx(1.2) and "3 real prices" in why
        f, why = calibration.factor_for(fs, "cnc_lathe")  # one sample: falls back to the median of all four
        assert f == pytest.approx(1.225) and "all processes" in why
        calibration.add(db, process="cnc_lathe", tool_unit_price=100, actual_unit_price=1000)
        assert calibration.factor_for(calibration.factors(db), "cnc_lathe")[0] == 3.0  # limited
    finally:
        db.query(CalibrationSample).delete()
        db.commit()
        db.close()


def test_benchmark_and_hardware_routes():
    with TestClient(app) as c:
        r = c.post("/api/calibration/benchmark", data={"material": "6061-T6 aluminum", "quantities": "1, 10", "prices": "650, 120", "vendor": "Shop A"},
                   files={"file": ("machined_block.step", (FIX / "cad" / "machined_block.step").read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        added = r.json()["added"]
        assert len(added) == 2 and added[0]["process"] == "cnc_mill" and added[0]["ratio"] < 1
        ov = c.get("/api/calibration").json()
        assert ov["factors"]["processes"]["cnc_mill"]["samples"] >= 2
        for s in added:
            c.delete(f"/api/calibration/{s['id']}")
        assert c.post("/api/calibration/benchmark", data={"quantities": "1, 10", "prices": "5"},
                      files={"file": ("m.step", (FIX / "cad" / "machined_block.step").read_bytes(), "x")}).status_code == 400
        h = c.post("/api/hardware", json={"part_number": "92196A110", "description": "4-40 screw", "match": "4-40 x 1/4", "pack_price": 5, "pack_qty": 100}).json()
        assert h["unit_price"] == 0.05 and h["url"].endswith("92196A110/")
        assert c.post("/api/hardware/test", json={"name": "screw 4-40 x 1/4 socket", "qty": 10}).json()["total"] == 5
        st = c.get("/api/hardware").json()["mcmaster"]
        assert st["configured"] is False and st["missing"]
        assert c.post("/api/hardware/mcmaster", json={"part_number": "91290A115"}).status_code == 400  # API not set up here
        c.delete(f"/api/hardware/{h['id']}")
