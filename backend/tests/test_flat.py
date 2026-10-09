"""DXF flat parts: parsing loops and metrics, units, warnings, nesting math, pricing, REST and saved quotes."""
import math
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient

from app import flat, pricing
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "flat"


def _parse(name, **kw):
    return flat.parse_dxf(FIX / name, **kw)


# ---------------------------------------------------------------- parsing
def test_plate_with_holes_and_slot():
    r = _parse("plate_holes_slot.dxf")
    assert r["units"] == "in" and r["units_source"] == "file header"
    assert len(r["parts"]) == 1
    p = r["parts"][0]
    assert (p["width"], p["height"]) == (6.0, 4.0)
    slot_area = 0.75 * 0.25 + math.pi * 0.125 ** 2
    expected_area = 24 - 4 * math.pi * 0.125 ** 2 - math.pi * 0.25 ** 2 - slot_area
    assert p["net_area"] == pytest.approx(expected_area, abs=0.003)  # slot arcs are polygons; circles are exact
    expected_cut = 20 + 4 * math.pi * 0.25 + math.pi * 0.5 + (2 * 0.75 + math.pi * 0.25)
    assert p["cut_length"] == pytest.approx(expected_cut, abs=1e-3)  # arc lengths are exact
    assert p["pierces"] == 7 and p["cutouts"] == 6 and p["round_holes"] == 5
    assert p["hole_diameters"] == [{"diameter": 0.25, "count": 4}, {"diameter": 0.5, "count": 1}]
    assert p["min_radius"] == pytest.approx(0.125) and p["smallest_cutout"] == pytest.approx(0.25)
    assert p["bend_lines"] == 1  # the line on layer BEND is a bend, not a cut
    text = " ".join(r["warnings"])
    assert "dimension" in text and "text" in text and "NOTES" in text
    assert r["svg"].startswith("<svg") and r["svg"].count("#c2410c") == 6 and "#2563eb" in r["svg"]


def test_bulge_polyline_ellipse_and_block_holes():
    p = _parse("bulge_part.dxf")["parts"][0]
    assert (p["width"], p["height"]) == (5.0, 2.0)  # the half circle bulges 1 in past x = 4
    outer = 8 + math.pi / 2
    holes = math.pi * 0.5 * 0.25 + 2 * math.pi * 0.1 ** 2
    assert p["net_area"] == pytest.approx(outer - holes, abs=0.003)
    ellipse_perim = math.pi * (3 * (0.5 + 0.25) - math.sqrt((3 * 0.5 + 0.25) * (0.5 + 3 * 0.25)))  # Ramanujan
    assert p["cut_length"] == pytest.approx(10 + math.pi + ellipse_perim + 2 * math.pi * 0.2, abs=0.005)
    assert p["pierces"] == 4
    assert p["hole_diameters"] == [{"diameter": 0.2, "count": 2}]  # block inserts exploded


def test_open_contour_and_duplicate_warned():
    r = _parse("open_contour.dxf")
    assert r["open_contours"] == 1 and r["duplicates_removed"] == 1
    assert len(r["parts"]) == 1 and r["parts"][0]["cut_length"] == pytest.approx(8.0)
    assert any("open contour" in w for w in r["warnings"]) and any("duplicate" in w for w in r["warnings"])
    assert 'stroke-dasharray="6 4"' in r["svg"]


def test_mm_units_and_identical_parts_grouped():
    r = _parse("mm_parts.dxf")
    assert r["units"] == "mm"
    plates = [p for p in r["parts"] if p["qty"] == 2]
    disk = [p for p in r["parts"] if p["qty"] == 1]
    assert len(plates) == 1 and len(disk) == 1
    assert plates[0]["width"] == pytest.approx(100 / 25.4, abs=1e-3)
    assert plates[0]["hole_diameters"][0]["diameter"] == pytest.approx(10 / 25.4, abs=1e-4)
    assert disk[0]["pierces"] == 1 and disk[0]["width"] == pytest.approx(30 / 25.4, abs=1e-4)
    # choosing inches reads the same numbers as inches
    r2 = _parse("mm_parts.dxf", units="in")
    assert max(p["width"] for p in r2["parts"]) == pytest.approx(100)


def test_unitless_file_assumed_inches(tmp_path):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 0
    doc.modelspace().add_lwpolyline([(0, 0), (3, 0), (3, 1), (0, 1)], close=True)
    path = tmp_path / "nounits.dxf"
    doc.saveas(path)
    r = flat.parse_dxf(path)
    assert r["units"] == "in" and r["units_source"].startswith("assumed")
    assert any("no units" in w for w in r["warnings"])
    assert flat.parse_dxf(path, units="mm")["parts"][0]["width"] == pytest.approx(3 / 25.4, abs=1e-4)


def test_ignore_layers_configurable(tmp_path):
    doc = ezdxf.new(units=1)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
    msp.add_lwpolyline([(5, 0), (6, 0), (6, 1), (5, 1)], close=True, dxfattribs={"layer": "BORDER"})
    path = tmp_path / "layers.dxf"
    doc.saveas(path)
    assert len(flat.parse_dxf(path)["parts"]) == 1
    assert len(flat.parse_dxf(path, ignore_layers=[])["parts"]) == 2


# ---------------------------------------------------------------- nesting
def test_parts_per_sheet_tries_both_orientations():
    # 10 x 20 parts, 0.25 spacing, 0.5 margin on 48 x 96: usable 47 x 95
    n = flat.parts_per_sheet(10, 20, 48, 96, 0.25, 0.5)
    # upright: floor(47.25/10.25)=4 cols x floor(95.25/20.25)=4 rows = 16; rotated: floor(47.25/20.25)=2 x floor(95.25/10.25)=9 = 18
    assert n["count"] == 18 and n["rotated"] is True
    assert flat.parts_per_sheet(60, 10, 48, 96, 0.25, 0.5)["count"] == 4  # only fits turned lengthwise
    assert flat.parts_per_sheet(100, 100, 48, 96, 0.25, 0.5)["count"] == 0


def test_nest_sheets_per_quantity():
    parts = [{"id": "a", "name": "a", "width": 10, "height": 20, "net_area": 200, "qty": 2}]
    r = flat.nest(parts, [1, 9, 10], {"width": 48, "length": 96}, 0.25, 0.5)
    assert r["parts"][0]["per_sheet"] == 18
    assert r["parts"][0]["utilization_pct"] == pytest.approx(18 * 200 / (48 * 96) * 100, abs=0.1)
    assert [r["by_quantity"][q]["sheets"] for q in (1, 9, 10)] == [1, 1, 2]  # 2, 18 and 20 parts


# ---------------------------------------------------------------- pricing
def _plate_parts():
    return _parse("plate_holes_slot.dxf")["parts"]


def test_laser_matches_pricing_speed_and_falls_with_quantity():
    cfg = pricing.merged_config({})
    r = flat.estimate(_plate_parts(), {"process": "laser_cut", "material": "A36 / 1018 steel", "thickness": 0.125}, [1, 10, 100])
    assert r["cut_ipm"] == pytest.approx(cfg["laser_ipm_at_0125"], abs=0.1)  # cut factor 1.0 at 0.125 in
    prices = [b["unit_price"] for b in r["price_breaks"]]
    assert prices[0] > prices[1] > prices[2] > 0
    assert r["nesting"]["parts"][0]["per_sheet"] > 0 and r["price_breaks"][0]["sheets"] == 1
    wj = flat.estimate(_plate_parts(), {"process": "waterjet", "material": "A36 / 1018 steel", "thickness": 0.125}, [10])
    assert wj["cut_ipm"] == pytest.approx(cfg["waterjet_ipm_at_0125"], abs=0.1)
    assert wj["price_breaks"][0]["unit_price"] > r["price_breaks"][1]["unit_price"]  # waterjet is slower


def test_options_add_cost_and_process_rules():
    base = {"process": "laser_cut", "material": "5052-H32 aluminum", "thickness": 0.09}
    parts = _plate_parts()
    p0 = flat.estimate(parts, base, [10])["price_breaks"][0]["unit_price"]
    parts_b = [dict(p, bends=2, pem=4) for p in parts]
    p1 = flat.estimate(parts_b, {**base, "finishes": ["powder coat"], "first_article": True}, [10])
    assert p1["price_breaks"][0]["unit_price"] > p0
    items = " ".join(l["item"] for l in p1["per_part_lines"] + p1["per_lot_lines"])
    assert "press brake" in items and "PEM" in items and "first article" in items
    router = flat.estimate(parts, {"process": "router", "material": "HDPE", "thickness": 0.5}, [10])
    assert router["cut_ipm"] < 60  # two passes at 0.25 in per pass
    with pytest.raises(pricing.SpecError):
        flat.estimate(parts, {"process": "plasma", "material": "HDPE", "thickness": 0.25}, [1])
    with pytest.raises(pricing.SpecError):
        flat.estimate(parts, {"process": "router", "material": "304 stainless", "thickness": 0.25}, [1])
    with pytest.raises(pricing.SpecError):
        flat.estimate(parts, {**base, "sheet": "12 x 24", "edge_margin_in": 5}, [1])  # 6 x 4 part no longer fits in 2 x 14
    full = flat.estimate(parts, {**base, "full_sheets": True}, [1, 50])
    assert any("sheet(s)" in l["item"] for l in full["per_lot_lines"])


# ---------------------------------------------------------------- REST and saving
def test_flat_endpoints_save_and_restore():
    with TestClient(app) as c:
        o = c.get("/api/flat/options").json()
        assert "plasma" in o["processes"] and "HDPE" in o["materials"] and 0.125 in o["thicknesses"] and "48 x 96" in o["sheet_sizes"]
        files = [("files", ("plate.dxf", (FIX / "plate_holes_slot.dxf").read_bytes(), "application/dxf")),
                 ("files", ("mm.dxf", (FIX / "mm_parts.dxf").read_bytes(), "application/dxf"))]
        r = c.post("/api/flat/parse", files=files, data={"units": "auto"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["files"]) == 2 and len(d["parts"]) == 3
        assert {p["id"] for p in d["parts"]} == {"f1p1", "f2p1", "f2p2"}
        bad = c.post("/api/flat/parse", files=[("files", ("x.txt", b"hello", "text/plain"))])
        assert bad.status_code == 400

        body = {"parts": d["parts"], "quantities": [1, 20], "options": {"process": "laser_cut", "material": "A36 / 1018 steel", "thickness": 0.125}}
        q = c.post("/api/flat/quote", json=body)
        assert q.status_code == 200, q.text
        est = q.json()
        assert est["parts_per_set"] == 4 and len(est["price_breaks"]) == 2
        assert c.post("/api/flat/quote", json={**body, "options": {"material": "unobtainium"}}).status_code == 400

        saved = c.post("/api/flat/save", json={**body, "name": "Brackets", "source": {"files": d["files"]}, "quoted_quantity": 20})
        assert saved.status_code == 200, saved.text
        s = saved.json()
        assert s["kind"] == "flat_dxf" and s["quoted_unit_price"] == est["price_breaks"][1]["unit_price"]
        back = c.get(f"/api/flat/quotes/{s['id']}").json()
        assert back["spec"]["parts"][0]["cut_length"] == d["parts"][0]["cut_length"]
        assert back["spec"]["source"]["files"][0]["svg"].startswith("<svg")
        assert "holes" not in back["spec"]["parts"][0]
        listed = c.get("/api/pricing/quotes").json()
        assert any(x["id"] == s["id"] and x["kind"] == "flat_dxf" for x in listed)
        # update in place
        again = c.post("/api/flat/save", json={**body, "name": "Brackets rev B", "quote_id": s["id"]}).json()
        assert again["id"] == s["id"] and again["name"] == "Brackets rev B"
