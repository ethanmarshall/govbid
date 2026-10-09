"""Heat-set insert holes: hole finding, thread guessing, conversion, endpoints, pricing, MCP."""
import json
import math
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app import cad, cad_quote, inserts, pricing
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "cad"
BLOCK = FIX / "insert_block.step"  # see fixtures/cad/make_insert_block.py


@pytest.fixture(scope="module")
def block():
    return cad.load_step(BLOCK)


def _plate(thickness, hole_d, hole_depth):
    """A 30 x 30 plate with one blind hole from the top face."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    box = BRepPrimAPI_MakeBox(30, 30, thickness).Shape()
    z0 = thickness - hole_depth
    cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(15, 15, z0), gp_Dir(0, 0, 1)), hole_d / 2, hole_depth + 1).Shape()
    return BRepAlgoAPI_Cut(box, cyl).Shape()


# ---------------------------------------------------------------- table
def test_table_matches_pem_hole_geometry():
    assert set(inserts.INSERT_TABLE) >= {"M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "#2-56", "#4-40", "#6-32", "#8-32",
                                         "#10-24", "#10-32", "1/4-20", "5/16-18", "3/8-16"}
    for name, t in inserts.INSERT_TABLE.items():
        assert t["entry_d"] > t["bottom_d"] > t["tap_drill"], name
        assert t["min_depth"] > t["insert_length"] > t["taper_length"], name
        assert t["nominal"] > t["tap_drill"], name
        # 8 degree included taper over the taper length (bulletin values are rounded)
        assert t["entry_d"] - t["bottom_d"] == pytest.approx(2 * t["taper_length"] * math.tan(math.radians(4)), abs=0.04), name
    assert inserts.INSERT_TABLE["#6-32"]["entry_d"] == pytest.approx(0.206 * 25.4, abs=1e-3)
    assert inserts.INSERT_TABLE["M3"]["min_depth"] == 6.58
    cfg = pricing.merged_config({})
    assert cfg["additive"]["inserts"]["threads"]["M3"]["unit_cost"] > 0


def test_guess_thread():
    assert inserts.guess_thread(2.5)["thread"] == "M3"
    assert inserts.guess_thread(2.5)["match"] == "tap_drill"
    assert inserts.guess_thread(2.705)["thread"] == "#6-32"
    assert inserts.guess_thread(3.0) == {"thread": "M3", "match": "nominal", "diameter_mm": 3.0, "off_mm": 0.0}
    assert inserts.guess_thread(5.105)["thread"] == "1/4-20"
    assert inserts.guess_thread(5.0)["thread"] == "M6"
    assert inserts.guess_thread(4.04)["thread"] == "#10-32"  # tap drill beats M4 nominal
    assert inserts.guess_thread(5.6) is None
    assert inserts.guess_thread(12.0) is None


# ---------------------------------------------------------------- hole finding
def test_find_holes(block):
    holes = inserts.find_holes(block)
    assert len(holes) == 4
    by_d = {round(h["diameter_mm"], 3): h for h in holes}
    m3 = [h for h in holes if h["diameter_mm"] == pytest.approx(2.5)]
    assert len(m3) == 2
    for h in m3:
        assert not h["through"] and h["depth_mm"] == pytest.approx(8.0)
        assert h["open_end_name"] in ("start", "end")
        top = h["start"] if h["open_start"] else h["end"]
        assert top[2] == pytest.approx(12.0)  # opens on the top face
    for d in (2.705, 5.6):
        assert by_d[d]["through"] and by_d[d]["open_end_name"] == "both" and by_d[d]["depth_mm"] == pytest.approx(12.0)
    assert [h["id"] for h in holes] == ["h1", "h2", "h3", "h4"]
    assert [h["id"] for h in inserts.find_holes(cad.load_step(BLOCK))] == [h["id"] for h in holes]  # stable ids
    assert holes[0]["diameter_in"] == pytest.approx(2.5 / 25.4, abs=1e-4)


def test_blind_hole_with_drill_point_is_not_open_at_the_bottom():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    plate = _plate(12, 2.5, 6)
    tip = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(15, 15, 6), gp_Dir(0, 0, -1)), 1.25, 0, 1.25 / math.tan(math.radians(59))).Shape()
    shape = BRepAlgoAPI_Cut(plate, tip).Shape()
    (h,) = inserts.find_holes(shape)
    assert not h["through"] and h["open_end_name"] in ("start", "end")


# ---------------------------------------------------------------- conversion
def test_convert_block(block):
    sel = inserts.auto_selections(block)
    assert {s["thread"] for s in sel} == {"M3", "#6-32"} and len(sel) == 3
    r = inserts.convert(block, sel)
    out = r["shape"]
    assert inserts.is_valid(out) and len(inserts._solids(out)) == 1
    assert inserts.count_faces(out, "cone") == 3
    assert r["volume_after"] < r["volume_before"]
    assert r["volume_after"] == pytest.approx(r["expected_volume"], rel=0.002)
    # independent check of the expected volume change for one M3 blind hole (8 mm deep, deeper than the 6.58 mm minimum)
    t = inserts.INSERT_TABLE["M3"]
    m3 = (math.pi * t["taper_length"] * ((t["entry_d"] / 2) ** 2 + t["entry_d"] * t["bottom_d"] / 4 + (t["bottom_d"] / 2) ** 2) / 3
          + math.pi * (t["bottom_d"] / 2) ** 2 * (8 - t["taper_length"]) - math.pi * 1.25 ** 2 * 8)
    assert r["inserts"][0]["thread"] == "M3" and r["inserts"][0]["depth"] == pytest.approx(8.0)
    assert m3 > 0 and r["volume_before"] - r["volume_after"] > 2 * m3
    after = inserts.find_holes(out)
    th = [h for h in after if h["diameter_mm"] == pytest.approx(inserts.INSERT_TABLE["#6-32"]["bottom_d"], abs=0.01)]
    assert len(th) == 1 and th[0]["through"] and th[0]["open_start"] and th[0]["open_end"]
    assert any(h["diameter_mm"] == pytest.approx(5.6) and h["through"] for h in after)  # odd hole untouched
    assert not r["warnings"]


def test_shallow_blind_hole_is_deepened_with_warning():
    shape = _plate(10, 2.5, 4)
    r = inserts.convert(shape, [{"hole_id": "h1", "thread": "M3"}])
    assert r["inserts"][0]["depth"] == pytest.approx(6.58)
    assert any("deepened" in w for w in r["warnings"])
    assert inserts.is_valid(r["shape"])


def test_thin_wall_hole_is_skipped():
    shape = _plate(4, 2.5, 3)  # an M3 insert needs 6.58 mm: it would break through the 4 mm plate
    with pytest.raises(inserts.InsertError) as e:
        inserts.convert(shape, [{"hole_id": "h1", "thread": "M3"}])
    assert "wall too thin" in str(e.value)


def test_convert_rejects_bad_selection(block):
    with pytest.raises(inserts.InsertError):
        inserts.convert(block, [{"hole_id": "h9", "thread": "M3"}])
    with pytest.raises(inserts.InsertError):
        inserts.convert(block, [{"hole_id": "h1", "thread": "M99"}])
    with pytest.raises(inserts.InsertError):  # 5.6 mm is already wider than an M3 insert hole
        inserts.convert(block, [{"hole_id": "h4", "thread": "M3"}])


# ---------------------------------------------------------------- files, endpoints, pricing
def test_endpoints_and_quote_with_inserts():
    with TestClient(app) as c:
        up = c.post("/api/cad/upload", files={"file": ("insert_block.step", BLOCK.read_bytes(), "application/step")})
        assert up.status_code == 200, up.text
        fid = up.json()["file_id"]
        h = c.get(f"/api/cad/{fid}/holes")
        assert h.status_code == 200, h.text
        hb = h.json()
        assert len(hb["holes"]) == 4
        groups = {(round(g["diameter_mm"], 2), g["through"]): g for g in hb["groups"]}
        assert groups[(2.5, False)]["count"] == 2 and groups[(2.5, False)]["guess"] == "M3"
        assert groups[(2.71, True)]["guess"] == "#6-32" and groups[(5.6, True)]["guess"] is None
        assert hb["holes"][0]["insert"]["entry_d"] == inserts.INSERT_TABLE["M3"]["entry_d"]
        assert c.get("/api/cad/0123abcd/holes").status_code == 404

        assert c.post(f"/api/cad/{fid}/inserts", json={"selections": []}).status_code == 400
        conv = c.post(f"/api/cad/{fid}/inserts", json={"auto": True})
        assert conv.status_code == 200, conv.text
        d = conv.json()
        assert d["file_id"] != fid and d["filename"] == "insert_block_inserts.step"
        assert d["derived_from"] == fid and len(d["inserts"]) == 3
        assert d["summary"] == "Converted 3 holes for 2x M3, 1x #6-32 inserts"
        assert d["mesh"]["triangles"] > 0 and d["geometry"]["faces"]["cone"] == 3
        assert d["geometry"]["volume"] < up.json()["geometry"]["volume"]
        stored = c.get(f"/api/cad/{d['file_id']}").json()
        assert stored["derived_from"] == fid and stored["inserts"][0]["thread"] in ("M3", "#6-32")
        assert {"hole_id", "thread", "insert", "entry_d", "bottom_d", "depth"} <= set(stored["inserts"][0])
        assert c.get(f"/api/cad/{d['file_id']}/download").content.startswith(b"ISO-10303")

        opts = {"process": "3d_print", "material": "PETG", "quantities": [10]}
        q = c.post("/api/cad/quote", json={"file_id": d["file_id"], "options": opts}).json()
        hw = next(o for o in q["spec"]["operations"] if o["type"] == "hardware_insert")
        cost = 2 * inserts.INSERT_TABLE["M3"]["unit_cost"] + inserts.INSERT_TABLE["#6-32"]["unit_cost"]
        assert hw["count"] == 3 and hw["unit_cost"] * 3 == pytest.approx(cost, abs=1e-3)
        line = next(l for l in q["estimate"]["per_part_lines"] if l["item"] == "3 hardware item(s)")
        assert line["cost"] == pytest.approx(cost, abs=0.01)
        assert any("heat-set insert" in a and "2x M3" in a for a in q["estimate"]["assumptions"])
        assert q["spec"]["cad"]["derived_from"] == fid
        orig = c.post("/api/cad/quote", json={"file_id": fid, "options": opts}).json()  # undo: the original has none
        assert not any(o["type"] == "hardware_insert" for o in orig["spec"]["operations"])
        assert q["estimate"]["per_part_cost"] > orig["estimate"]["per_part_cost"] - 1  # inserts add cost; volume drops slightly

        # milled quote of the converted file ignores the inserts
        mill = c.post("/api/cad/quote", json={"file_id": d["file_id"], "options": {"process": "cnc_mill", "material": "6061-T6 aluminum"}}).json()
        assert not any(o["type"] == "hardware_insert" for o in mill["spec"]["operations"])

        # one hole by hand
        one = c.post(f"/api/cad/{fid}/inserts", json={"selections": [{"hole_id": "h3", "thread": "#6-32", "from_end": "start"}]}).json()
        assert len(one["inserts"]) == 1 and one["inserts"][0]["through"]

        # the shop can change the insert price in the rates; values stay numeric
        r = c.put("/api/pricing/config", json={"changes": {"additive": {"inserts": {"threads": {"M3": {"unit_cost": 1.0}}}}}})
        assert r.status_code == 200, r.text
        q2 = c.post("/api/cad/quote", json={"file_id": d["file_id"], "options": opts}).json()
        hw2 = next(o for o in q2["spec"]["operations"] if o["type"] == "hardware_insert")
        assert hw2["unit_cost"] * 3 == pytest.approx(2.0 + inserts.INSERT_TABLE["#6-32"]["unit_cost"], abs=1e-3)
        bad = c.put("/api/pricing/config", json={"changes": {"additive": {"inserts": {"threads": {"M3": {"unit_cost": "cheap"}}}}}})
        assert bad.status_code == 400
        c.post("/api/pricing/config/reset")


def test_threaded_holes_still_priced_without_conversion():
    fid = cad_quote.store_upload(BLOCK.read_bytes(), "insert_block.step")["file_id"]
    q = cad_quote.quote(fid, {"process": "3d_print", "material": "PLA", "quantities": [1], "threaded_holes": 2})
    hw = next(o for o in q["spec"]["operations"] if o["type"] == "hardware_insert")
    assert hw == {"type": "hardware_insert", "count": 2, "unit_cost": 0.25, "minutes_each": 0.75}


def test_mcp_convert_then_quote():
    from app import mcp_server

    async def run():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        assert {"convert_holes_for_inserts", "analyze_step_file", "quote_step_file"} <= names
        a = json.loads((await mcp_server.mcp.call_tool("analyze_step_file", {"file_path": str(BLOCK)})).content[0].text)
        conv = json.loads((await mcp_server.mcp.call_tool("convert_holes_for_inserts", {"file_id": a["file_id"]})).content[0].text)
        assert conv["derived_from"] == a["file_id"] and len(conv["inserts"]) == 3 and "mesh" not in conv
        q = json.loads((await mcp_server.mcp.call_tool("quote_step_file", {"file_id": conv["file_id"], "material": "PETG",
                                                                            "process": "3d_print", "quantities": [5]})).content[0].text)
        assert any(o["type"] == "hardware_insert" and o["count"] == 3 for o in q["spec"]["operations"])
        bad = json.loads((await mcp_server.mcp.call_tool("convert_holes_for_inserts", {"file_id": a["file_id"],
                                                                                       "selections": [{"hole_id": "h4", "thread": "M3"}]})).content[0].text)
        assert "error" in bad and len(bad["holes"]) == 4

    anyio.run(run)
