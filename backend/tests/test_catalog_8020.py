"""80/20 catalog knowledge: numbers checked against Catalog 24 pages noted in app/catalog_8020.py."""
from app import catalog_8020 as c
from app import extrusion


def test_profile_data_and_service_numbers():
    p = c.profile("1515")
    assert p["lb_in"] == 0.1123 and p["i_strong"] == 0.2542 and p["cut_op"] == "7010"
    assert c.profile("1530")["i_strong"] == 1.8042 and c.profile("1530")["cut_op"] == "7020"
    assert c.profile("1515-Black-FB")["part_no"] == "1515"
    assert c.op_number("counterbore", "1515") == "7040" and c.op_number("counterbore", "1010") == "7042"
    assert c.op_number("access_hole", "1530") == "7050" and c.op_number("butt_counterbore", "1515") == "7041"
    assert c.op_number("end_tap", "1515") == "7060" and c.op_number("end_tap", "1515", "7/16-14") == "7054"
    assert c.op_number("end_tap", "1530", "7/16-14") == "7033" and c.op_number("end_tap", "1010") == "7061"
    assert c.op_number("miter_cut", "1515") == "7065" and c.op_number("miter_cut", "1530") == "7075"


def test_catalog_deflection_example():
    # catalog 2-10: 1515, 30 in, 50 lb at the center -> about .011 in
    assert round(c.deflection("1515", 30, 50, "A"), 3) == 0.011


def test_order_list_and_checks():
    lines = [{"kind": "profile", "catalog_id": "1515", "qty": 4, "length_in": 33, "machining": [{"op": "counterbore", "count": 2}]},
             {"kind": "profile", "catalog_id": "1530", "qty": 4, "length_in": 30.75, "machining": []},
             {"kind": "hardware", "catalog_id": "ANCHOR-15", "qty": 10},
             {"kind": "hardware", "catalog_id": "CASTER-15", "qty": 4},
             {"kind": "hardware", "catalog_id": "HINGE-15", "qty": 4},
             {"kind": "panel", "catalog_id": "PANEL-PC-250", "qty": 2, "width_in": 20, "height_in": 28}]
    r = extrusion.price_build(lines)
    text = " ".join(f["text"] for f in r["checks"])
    assert "10 anchor fasteners but 8 anchor counterbores" in text
    assert "need 4 tapped profile ends, but 0 end taps" in text
    rows = {x["part_number"]: x for x in r["order_8020"]["rows"]}
    assert rows["3360"]["qty"] == 10 and rows["2306"]["qty"] == 4 and rows["2104"]["qty"] == 2 and rows["2609"]["qty"] == 2
    assert rows["1515"]["callout"].startswith("#7010 cut to 33.000 in; #7040 counterbore x2")


def test_panel_too_thick_and_long_piece():
    lines = [{"kind": "profile", "catalog_id": "1010", "qty": 2, "length_in": 250, "machining": []},
             {"kind": "hardware", "catalog_id": "ENDCAP-10", "qty": 2},
             {"kind": "panel", "catalog_id": "PANEL-AL-250", "qty": 1, "width_in": 10, "height_in": 10}]
    r = extrusion.price_build(lines)
    levels = {(f["level"], f["page"]) for f in r["checks"]}
    assert ("error", "2-34") in levels  # longer than a 242 in stick
    assert not any("slot opening" in f["text"] for f in r["checks"])  # a .250 plate fits the .256 in 10 Series slot
    thick = c.check([{"kind": "profile", "catalog_id": "1515", "qty": 1, "length_in": 20},
                     {"kind": "panel", "catalog_id": "X", "qty": 1, "width_in": 5, "height_in": 5}], {"X": 0.375})
    assert any(f["level"] == "error" and "slot opening (0.32 in)" in f["text"] for f in thick)
    thin = c.check([{"kind": "profile", "catalog_id": "1515", "qty": 1, "length_in": 20},
                    {"kind": "panel", "catalog_id": "PANEL-PC-125", "qty": 1, "width_in": 5, "height_in": 5}], {"PANEL-PC-125": 0.118})
    assert any("rattle" in f["text"] for f in thin)
    assert any(x["part_number"] == "2015" for x in r["order_8020"]["rows"])  # 1010 end cap


def test_bom_with_8020_numbers():
    csv = (b"Qty,Part,Description,Length,Machining\n4,1515,T-slot profile,30.00,(2) #7040\n4,1530,post,33.75,7054 one end\n"
           b"8,3360,Anchor fastener,,\n4,2306,Caster,,\n")
    lines = extrusion.parse_bom_table(csv, "bom.csv")["lines"]
    by = {l["catalog_id"]: l for l in lines}
    assert by["1515"]["machining"] == [{"op": "counterbore", "count": 2}]
    assert by["1530"]["machining"] == [{"op": "end_tap", "count": 1, "thread": "7/16-14"}]
    assert by["ANCHOR-15"]["qty"] == 8 and by["CASTER-15"]["qty"] == 4
    order = {x["part_number"]: x for x in extrusion.price_build(lines)["order_8020"]["rows"]}
    assert "#7033 end tap 7/16-14" in order["1530"]["callout"]


def _box(x, y, z, dx, dy, dz):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    mm = 25.4
    return BRepPrimAPI_MakeBox(gp_Pnt(x * mm, y * mm, z * mm), dx * mm, dy * mm, dz * mm).Shape()


def _turned(shape, deg, axis=(1, 0, 0)):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    import math

    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(deg))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def test_square_bar_turned_about_its_length_measures_true():
    # a model with rails turned 15 degrees about their length read as 1.86 in square and was machined from solid bar
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    from app import tslot

    bar = BRepAlgoAPI_Cut(_box(0, 0, 0, 13.3125, 1.5, 1.5), _box(-1, 0.5, 0.5, 16, 0.5, 0.5)).Shape()  # hollow, like a T-slot
    for deg in (0, 15, 33, 45):
        (a, b, L), _ = tslot._obb(_turned(bar, deg))
        assert abs(a - 1.5) < 0.01 and abs(b - 1.5) < 0.01 and abs(L - 13.3125) < 0.01, (deg, a, b, L)
        c = tslot.classify(_turned(bar, deg), "Part 22")
        assert c and c["profile"] == "1515"


def test_standard_parts_by_size():
    from app import tslot

    cap = _turned(_box(0, 0, 0, 1.5, 1.5, 0.188), 20, (0, 0, 1))
    assert tslot.standard_part(cap) == ("ENDCAP", "15", "2030")
    assert tslot.standard_part(_box(0, 0, 0, 3, 3, 3)) is None
    assert c.match_part("2333 <7>")[0] == "CASTER-LOCK-15" and c.match_part("2420")[0] == "CASTER-PLATE-15"


def test_material_handling_on_bought_material_only():
    from app import pricing

    lines = [{"kind": "profile", "catalog_id": "1515", "qty": 1, "length_in": 20, "machining": []},
             {"kind": "hardware", "catalog_id": "CASTER-15", "qty": 4}]
    r = extrusion.price_build(lines, {"extrusion": {"prices": {"profiles": {"1515": 1.0}, "hardware": {"CASTER-15": 20.0}}}})
    h = [l for l in r["per_part_lines"] if l["category"] == "handling"]
    assert len(h) == 1 and h[0]["cost"] == round((20 * 1.0 + 4 * 20.0) * pricing.DEFAULT_CONFIG["material_handling_rate"], 2)
    off = extrusion.price_build(lines, {"material_handling_rate": 0, "extrusion": {"prices": {"profiles": {"1515": 1.0}, "hardware": {"CASTER-15": 20.0}}}})
    assert not [l for l in off["per_part_lines"] if l["category"] == "handling"]
    assert r["price_breaks"][0]["total_price"] > off["price_breaks"][0]["total_price"]
    # labor lines (with hours) are never marked up
    assert pricing.handling_lines({"material_handling_rate": 0.1}, [{"category": "hardware", "cost": 50, "hours": 0.5}]) == []
