"""Manufacturability checks on generated STEP fixtures, the REST endpoint and the MCP tool."""
import json
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app import cad, cad_quote, dfm
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "cad"


def _check(name, process, material=""):
    shape = cad.load_step(FIX / f"{name}.step")
    return dfm.check(shape, cad.analyze(shape), process, material)


def _rules(r):
    return {f["rule"]: f for f in r["findings"]}


def test_thin_wall_and_sharp_corners():
    r = _check("thin_wall", "cnc_mill", "6061-T6 aluminum")
    f = _rules(r)
    assert f["thin_wall"]["severity"] == "warn"
    assert "0.020 in" in f["thin_wall"]["title"]
    pt = f["thin_wall"]["location"]["point"]
    assert pt[0] == pytest.approx(59.75 / 25.4, abs=0.01)  # in the 0.5 mm wall at x = 59.5..60 mm
    assert f["sharp_internal_corner"]["count"] == 4 and f["sharp_internal_corner"]["cost_effect"] == "EDM or extra op"
    assert len(f["sharp_internal_corner"]["location"]["points"]) == 4
    # the pocket floor edges are reachable by a flat end mill: only the 4 vertical corners are flagged
    assert r["counts"]["warn"] == 2
    assert "Manufacturability review" in r["note"] and "Thin wall" in r["note"]
    # a plastic part uses the larger plastic limit; a printed part the FDM limit (0.8 mm)
    assert "0.040" in _rules(_check("thin_wall", "cnc_mill", "delrin (acetal)"))["thin_wall"]["detail"]
    assert "FDM" in _rules(_check("thin_wall", "3d_print", "PLA"))["thin_wall"]["detail"]


def test_holes_depth_size_and_drill_sizes_and_setups():
    r = _check("deep_hole", "cnc_mill")
    titles = [f["title"] for f in r["findings"]]
    deep = [f for f in r["findings"] if f["rule"] == "hole_depth"]
    assert any(f["severity"] == "warn" and "17x" in f["title"] for f in deep)  # 3 mm x 50 mm
    assert any(f["severity"] == "cost" for f in deep)
    assert any("Very small hole" in t for t in titles)
    odd = [f for f in r["findings"] if f["rule"] == "drill_size"]
    assert len(odd) == 1 and "0.2700" in odd[0]["title"] and "I (0.2720 in)" in odd[0]["suggestion"]  # #7 (0.201) passes
    setups = _rules(r)["setups"]
    assert setups["severity"] == "cost" and setups["cost_effect"] == "+1 setup(s)"


def test_nearest_drill():
    assert dfm.nearest_drill(0.201) == ("#7", 0.201)
    assert dfm.nearest_drill(0.25)[1] == 0.25
    assert dfm.nearest_drill(3.3 / 25.4)[0] == "3.3 mm"


def test_sheet_metal_rules():
    f = _rules(_check("bad_bend", "sheet_metal", "A36 / 1018 steel"))
    assert f["bend_radius"]["severity"] == "warn"
    assert f["hole_near_bend"]["count"] == 1  # the 3 mm hole, not the 4 mm one 20 mm away
    assert f["hole_near_bend"]["location"]["point"][0] == pytest.approx(3 / 25.4, abs=0.01)
    assert f["short_flange"]["count"] == 1 and "0.1969" in f["short_flange"]["title"]  # 3 + 0.5 + 1.5 mm
    ok = _rules(_check("sheet_bracket", "sheet_metal"))
    assert "bend_radius" not in ok and "short_flange" not in ok  # radius = thickness, long flanges


def test_clean_lathe_part_has_no_mill_checks():
    r = _check("turned_shaft", "auto")
    assert r["process"] == "cnc_lathe"
    assert not any(f["rule"] in ("setups", "sharp_internal_corner") for f in r["findings"])
    with pytest.raises(cad.CadError):
        _check("turned_shaft", "laser")


def test_rules_override_from_config():
    shape = cad.load_step(FIX / "thin_wall.step")
    r = dfm.check(shape, cad.analyze(shape), "cnc_mill", "", {"dfm": {"thin_wall_in": {"metal": 0.01}}})
    assert "thin_wall" not in _rules(r)


def test_dfm_endpoint_and_mcp_tool():
    fid = cad_quote.store_upload((FIX / "deep_hole.step").read_bytes(), "deep_hole.step")["file_id"]
    with TestClient(app) as c:
        r = c.get(f"/api/cad/{fid}/dfm", params={"process": "cnc_mill"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["process"] == "cnc_mill" and d["counts"]["warn"] >= 2 and d["note"]
        assert all({"severity", "title", "detail", "suggestion", "cost_effect", "location"} <= set(x) for x in d["findings"])
        assert c.get(f"/api/cad/{fid}/dfm", params={"process": "laser"}).status_code == 400
        assert c.get("/api/cad/0000000000000000000000ff/dfm").status_code == 404

    from app import mcp_server

    async def run():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        assert {"dfm_check", "split_assembly"} <= names
        out = json.loads((await mcp_server.mcp.call_tool("dfm_check", {"file_id": fid, "process": "cnc_mill"})).content[0].text)
        assert out["findings"] and "rules" not in out

    anyio.run(run)
