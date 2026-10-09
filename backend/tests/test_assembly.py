"""Multi-body STEP files: listing bodies, grouping identical ones, joints and weld estimate, splitting,
assembly pricing, saving an assembly quote, and the MCP split tool."""
import json
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app import assembly, cad_quote
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "cad"


@pytest.fixture(scope="module")
def weldment():
    return cad_quote.store_upload((FIX / "weldment.step").read_bytes(), "weldment.step")


def test_bodies_grouped_with_joints(weldment):
    assert weldment["geometry"]["solids"] == 3
    b = assembly.bodies(weldment["file_id"])
    assert b["count"] == 3 and len(b["bodies"]) == 3
    assert all(x["mesh"]["triangles"] > 0 for x in b["bodies"])
    qtys = sorted(g["qty"] for g in b["groups"])
    assert qtys == [1, 2]  # base plate, two identical uprights
    base = next(g for g in b["groups"] if g["qty"] == 1)
    assert sorted(base["bounding_box"].values(), reverse=True) == pytest.approx([100 / 25.4, 50 / 25.4, 6 / 25.4], abs=0.005)
    assert len(b["joints"]) == 2  # each upright stands on the base; the uprights do not touch
    for j in b["joints"]:
        assert j["contact_length_in"] == pytest.approx(100 / 25.4, abs=0.01)
    assert b["weld_estimate_in"] == pytest.approx(4 * 100 / 25.4, abs=0.05)  # two fillets per joint


def test_split_stores_each_body_once(weldment):
    s = assembly.split(weldment["file_id"])
    assert len(s["groups"]) == 2
    for g in s["groups"]:
        d = cad_quote.load(g["file_id"])
        assert d["geometry"]["solids"] == 1 and d["split_from"] == weldment["file_id"]
    again = assembly.split(weldment["file_id"])
    assert [g["file_id"] for g in again["groups"]] == [g["file_id"] for g in s["groups"]]


def test_assembly_price_is_bodies_plus_joining(weldment):
    s = assembly.split(weldment["file_id"])
    lines = [{"file_id": g["file_id"], "name": g["name"], "qty": g["qty"], "process": "cnc_mill", "material": "A36 / 1018 steel"} for g in s["groups"]]
    plain = assembly.quote_assembly(lines, {}, [1, 10])
    welded = assembly.quote_assembly(lines, {"weld_length_in": s["weld_estimate_in"], "weld_joints": 2, "assembly_minutes": 15}, [1, 10])
    for b in welded["price_breaks"]:
        assert b["total_price"] == pytest.approx(b["bodies_price"] + b["joining_price"], abs=0.02)
    assert welded["price_breaks"][0]["total_price"] > plain["price_breaks"][0]["total_price"]
    # each body is priced at qty per assembly x assemblies, matching its own instant quote
    upright = next(g for g in s["groups"] if g["qty"] == 2)
    alone = cad_quote.quote(upright["file_id"], {"process": "cnc_mill", "material": "A36 / 1018 steel", "quantities": [20],
                                                 "freight_per_lot": 0, "approved_source_required": False})
    row = next(r for r in welded["bodies"] if r["file_id"] == upright["file_id"])
    assert row["breaks"][1]["parts"] == 20 and row["breaks"][1]["total_price"] == alone["estimate"]["price_breaks"][0]["total_price"]
    assert welded["price_breaks"][1]["unit_price"] < welded["price_breaks"][0]["unit_price"]
    # skipped and bought-out bodies
    skip = assembly.quote_assembly([dict(lines[0], skip=True), lines[1]], {}, [1])
    assert skip["price_breaks"][0]["bodies_price"] < plain["price_breaks"][0]["bodies_price"]
    buy = assembly.quote_assembly([dict(lines[0], buy=True, buy_unit_price=10.0), lines[1]], {}, [1])
    assert next(r for r in buy["bodies"] if r["buy"])["breaks"][0]["total_price"] == pytest.approx(10 * 1.15)
    missing = assembly.quote_assembly([dict(lines[0], buy=True), lines[1]], {}, [1])
    assert missing["incomplete"] and any("not priced" in w for w in missing["warnings"])


def test_assembly_endpoints_and_saved_quote(weldment):
    fid = weldment["file_id"]
    with TestClient(app) as c:
        b = c.get(f"/api/cad/{fid}/bodies").json()
        assert len(b["groups"]) == 2
        s = c.post(f"/api/cad/{fid}/split").json()
        body = {"bodies": [{"file_id": g["file_id"], "name": g["name"], "qty": g["qty"], "process": "sheet_metal", "material": "A36 / 1018 steel"} for g in s["groups"]],
                "joining": {"weld_length_in": s["weld_estimate_in"], "weld_joints": 2, "fasteners": 4}, "quantities": [2, 20], "name": "Weld frame"}
        r = c.post(f"/api/cad/{fid}/assembly-quote", json=body)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["spec"]["kind"] == "assembly" and q["spec"]["cad"]["file_id"] == fid and len(q["price_breaks"]) == 2
        saved = c.post("/api/pricing/quotes", json={"spec": q["spec"], "quoted_quantity": 20})
        assert saved.status_code == 200, saved.text
        sv = saved.json()
        assert sv["kind"] == "assembly" and sv["cad_file"] == "weldment.step"
        assert sv["quoted_unit_price"] == q["price_breaks"][1]["unit_price"]
        assert c.post("/api/cad/0000000000000000000000ff/split").status_code == 404

    from app import mcp_server

    async def run():
        out = json.loads((await mcp_server.mcp.call_tool("split_assembly", {"file_id": fid})).content[0].text)
        assert sorted(g["qty"] for g in out["groups"]) == [1, 2]

    anyio.run(run)
