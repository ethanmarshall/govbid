"""STEP instant quote: geometry measurement, pricing from the model, REST endpoints, MCP tools."""
import base64
import json
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app import cad, cad_quote
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "cad"


@pytest.fixture(scope="module")
def geo():
    return {n: cad.analyze_file(FIX / f"{n}.step")["geometry"] for n in ("machined_block", "sheet_bracket", "turned_shaft")}


# ---------------------------------------------------------------- geometry
def test_block_measured(geo):
    g = geo["machined_block"]
    assert sorted(g["bounding_box"].values(), reverse=True) == pytest.approx([4.0, 3.0, 0.5], abs=0.01)
    assert len(g["holes"]) == 5
    assert g["suggested_process"] == "cnc_mill"
    assert g["volume"] < 4 * 3 * 0.5


def test_sheet_measured(geo):
    sm = geo["sheet_bracket"]["sheet_metal"]
    assert geo["sheet_bracket"]["suggested_process"] == "sheet_metal"
    assert sm["thickness"] == pytest.approx(0.0625, abs=0.002)
    assert sm["bends"] == 1
    assert sm["cut_length"] == pytest.approx(14.55, abs=0.3)
    assert sm["holes_through_thickness"] == 2


def test_shaft_measured(geo):
    g = geo["turned_shaft"]
    assert g["suggested_process"] == "cnc_lathe"
    assert {round(d, 3) for d in g["turned"]["diameters"]} >= {1.0, 0.75}
    axis = g["turned"]["axis"]
    assert sum(1 for h in g["holes"] if not cad._parallel(h["axis"], axis, 0.05)) == 1


def test_not_a_step_file_rejected():
    with pytest.raises(cad.CadError):
        cad_quote.store_upload(b"hello world", "x.step")


# ---------------------------------------------------------------- pricing from the model
def test_quote_prices_each_process_and_falls_with_quantity():
    for name, process in [("machined_block", "cnc_mill"), ("sheet_bracket", "sheet_metal"), ("turned_shaft", "cnc_lathe")]:
        fid = cad_quote.store_upload((FIX / f"{name}.step").read_bytes(), f"{name}.step")["file_id"]
        r = cad_quote.quote(fid, {"material": "6061-T6 aluminum", "quantities": [1, 10, 100]})
        assert r["process"] == process
        prices = [b["unit_price"] for b in r["estimate"]["price_breaks"]]
        assert prices[0] > prices[1] > prices[2] > 0
        assert r["spec"]["cad"]["file_id"] == fid


def test_options_change_price():
    fid = cad_quote.store_upload((FIX / "machined_block.step").read_bytes(), "b.step")["file_id"]
    base = cad_quote.quote(fid, {"material": "6061-T6 aluminum", "quantities": [10]})["estimate"]["price_breaks"][0]["unit_price"]
    steel = cad_quote.quote(fid, {"material": "304 stainless", "quantities": [10]})["estimate"]["price_breaks"][0]["unit_price"]
    anod = cad_quote.quote(fid, {"material": "6061-T6 aluminum", "quantities": [10], "finishes": ["anodize (Type II)"]})["estimate"]["price_breaks"][0]["unit_price"]
    tapped = cad_quote.quote(fid, {"material": "6061-T6 aluminum", "quantities": [10], "threaded_holes": 4, "first_article": True})["estimate"]["price_breaks"][0]["unit_price"]
    assert steel > base and anod > base and tapped > base


def test_sheet_process_refused_for_block():
    fid = cad_quote.store_upload((FIX / "machined_block.step").read_bytes(), "b.step")["file_id"]
    from app import pricing
    with pytest.raises(pricing.SpecError):
        cad_quote.quote(fid, {"material": "6061-T6 aluminum", "process": "sheet_metal"})


# ---------------------------------------------------------------- REST
def test_cad_endpoints_and_saved_quote():
    with TestClient(app) as c:
        opts = c.get("/api/cad/options").json()
        assert "sheet_metal" in opts["processes"] and opts["materials"]
        up = c.post("/api/cad/upload", files={"file": ("bracket.step", (FIX / "sheet_bracket.step").read_bytes(), "application/step")})
        assert up.status_code == 200, up.text
        d = up.json()
        assert d["mesh"]["triangles"] > 0 and len(d["mesh"]["indices"]) == 3 * d["mesh"]["triangles"]
        assert c.get(f"/api/cad/{d['file_id']}").json()["geometry"]["sheet_metal"]["bends"] == 1
        assert c.get(f"/api/cad/{d['file_id']}/download").content.startswith(b"ISO-10303")
        assert c.post("/api/cad/upload", files={"file": ("x.step", b"nope", "text/plain")}).status_code == 400
        assert c.get("/api/cad/zz-bad").status_code == 404

        q = c.post("/api/cad/quote", json={"file_id": d["file_id"], "options": {"filename": "bracket.step", "material": "5052-H32 aluminum", "quantities": [5, 50], "finishes": ["powder coat"]}})
        assert q.status_code == 200, q.text
        body = q.json()
        assert "geometry" not in body and body["process"] == "sheet_metal"
        assert c.post("/api/cad/quote", json={"file_id": d["file_id"], "options": {"material": "unobtainium"}}).status_code == 400

        saved = c.post("/api/pricing/quotes", json={"spec": body["spec"], "quoted_quantity": 50}).json()
        assert saved["cad_file"] == "bracket.step"
        assert saved["spec"]["cad"]["options"]["finishes"] == ["powder coat"]
        assert saved["quoted_unit_price"] == body["estimate"]["price_breaks"][1]["unit_price"]
        listed = c.get("/api/pricing/quotes").json()
        assert any(r["id"] == saved["id"] and r["cad_file"] == "bracket.step" for r in listed)


# ---------------------------------------------------------------- MCP
def test_mcp_step_tools():
    from app import mcp_server

    async def run():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        assert {"analyze_step_file", "quote_step_file"} <= names
        a = json.loads((await mcp_server.mcp.call_tool("analyze_step_file", {"file_path": str(FIX / "turned_shaft.step")})).content[0].text)
        assert a["geometry"]["suggested_process"] == "cnc_lathe" and "mesh" not in a
        b64 = base64.b64encode((FIX / "machined_block.step").read_bytes()).decode()
        b = json.loads((await mcp_server.mcp.call_tool("analyze_step_file", {"content_base64": b64, "filename": "block.step"})).content[0].text)
        q = json.loads((await mcp_server.mcp.call_tool("quote_step_file", {"file_id": b["file_id"], "material": "A36 / 1018 steel", "quantities": [1, 25], "finishes": ["black oxide"]})).content[0].text)
        assert q["process"] == "cnc_mill" and len(q["price_breaks"]) == 2 and q["spec"]["cad"]["file_id"] == b["file_id"]
        missing = json.loads((await mcp_server.mcp.call_tool("analyze_step_file", {"file_path": "/nope.step"})).content[0].text)
        assert "error" in missing

    anyio.run(run)


# ---------------------------------------------------------------- 3D printing
def test_3d_print_quote_and_options():
    from app import pricing
    fid = cad_quote.store_upload((FIX / "turned_shaft.step").read_bytes(), "shaft.step")["file_id"]
    pla = cad_quote.quote(fid, {"process": "3d_print", "material": "PLA", "quantities": [1, 10], "infill": 0.2})
    solid = cad_quote.quote(fid, {"process": "3d_print", "material": "PLA", "quantities": [1, 10], "infill": 1.0})
    mjf = cad_quote.quote(fid, {"process": "3d_print", "material": "Nylon 12 (MJF)", "quantities": [10], "finishes": ["dyed black"], "threaded_holes": 2})
    assert pla["spec"]["operations"][0]["type"] == "additive"
    assert solid["estimate"]["price_breaks"][1]["unit_price"] > pla["estimate"]["price_breaks"][1]["unit_price"]
    assert pla["estimate"]["price_breaks"][0]["total_price"] >= 75.0  # printed-part lot minimum, not the shop minimum
    items = [l["item"] for l in mjf["estimate"]["per_part_lines"]]
    assert any("MJF" in i for i in items) and "dyed black" in items and any("hardware" in i for i in items)
    with pytest.raises(pricing.SpecError):  # metal material on a printer
        cad_quote.quote(fid, {"process": "3d_print", "material": "6061-T6 aluminum"})
    with pytest.raises(pricing.SpecError):  # SLA material forced onto FDM
        cad_quote.quote(fid, {"process": "3d_print", "material": "Tough resin", "technology": "fdm"})
    with TestClient(app) as c:
        o = c.get("/api/cad/options").json()
        assert o["print_materials"]["PETG"] == "fdm" and "3d_print" in o["processes"]
        saved = c.post("/api/pricing/quotes", json={"spec": mjf["spec"], "quoted_quantity": 10}).json()
        assert saved["price_breaks"][0]["unit_price"] == mjf["estimate"]["price_breaks"][0]["unit_price"]
        bad = c.put("/api/pricing/config", json={"changes": {"additive": {"materials": {"X": {"tech": "laser", "price_per_cm3": 1, "density": 1}}}}})
        assert bad.status_code == 400


def test_large_part_flags_build_volume():
    from app import pricing
    spec = {"quantities": [1], "material": "Standard resin", "operations": [{"type": "additive", "part_volume_in3": 20, "bbox_in": [10, 4, 2]}]}
    r = pricing.estimate(spec)
    assert any("build volume" in w for w in r["warnings"])
