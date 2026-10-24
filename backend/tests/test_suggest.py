"""A suggested way to make a part the customer gave no material for: printed with inserts and bushings."""
from app import cad_quote, suggest


def test_print_extras_find_index_holes_and_insert_holes():
    radial = [{"diameter": 0.5625, "depth": 0.99, "axis": [0, round(c, 3), round(s, 3)]}
              for c, s in ((1, 0), (0.87, 0.5), (0.5, 0.87), (0, 1), (-0.5, 0.87), (-0.87, 0.5))]
    geo = {"holes": radial + [{"diameter": 0.349, "depth": 0.36, "axis": [0, -0.26, -0.97]},  # set screw hole: a 1/4-20 insert
                              {"diameter": 0.488, "depth": 0.7, "axis": [1, 0, 0]}]}  # the bore
    ex = suggest.print_extras(geo)
    assert ex["bushings"] == 6 and ex["inserts"] == 1
    # four bolt holes on one axis are clearance holes, not index holes
    assert suggest.print_extras({"holes": [{"diameter": 0.266, "depth": 0.25, "axis": [0, 0, 1]}] * 4})["bushings"] == 0


def test_suggest_print_only_when_machining_is_hard_and_far_dearer(monkeypatch):
    monkeypatch.setattr(cad_quote, "quote", lambda fid, o, cfg=None: {"estimate": {"price_breaks": [{"unit_price": 400.0}]}, "spec": {}})
    monkeypatch.setattr(cad_quote, "complexity_of", lambda g: {"five_axis": False})
    geo = {"holes": [], "estimated_setups": 5}
    s = suggest.suggestion("x", geo, {"quantities": [1]}, {"process": "cnc_mill", "unit_price": 3000.0, "five_axis": True})
    assert s and s["material"] == suggest.SUGGEST_MATERIAL and s["opts"]["process"] == "3d_print"
    assert suggest.suggestion("x", geo, {}, {"process": "cnc_mill", "unit_price": 700.0, "five_axis": True}) is None  # print not much cheaper
    assert suggest.suggestion("x", {"holes": [], "estimated_setups": 2}, {}, {"process": "cnc_mill", "unit_price": 3000.0, "five_axis": False}) is None


def test_infill_choice_is_validated():
    import pytest

    from app import portal

    assert portal.merge_line_opts({}, {"a": {"infill": 100}}, 100) == {"a": {"infill": 100}}
    with pytest.raises(portal.PortalError):
        portal.merge_line_opts({}, {"a": {"infill": 5}}, 100)


def test_simple_parts_program_and_set_up_faster():
    from app import pricing

    def lot(faces, holes):
        spec = {"quantities": [1], "material": "6061-T6 aluminum", "stock": {"shape": "plate", "dims": {"length": 3, "width": 3, "thickness": 1}},
                "operations": [{"type": "cnc_mill", "setups": 2, "features": {"holes": holes, "faces": faces, "volume_removed_in3": 1}}]}
        r = pricing.estimate(spec)
        return sum(l["cost"] for l in r["per_lot_lines"] if l["category"] in ("programming", "setup"))

    assert abs(lot(10, 2) - lot(60, 2) / 2) < 0.01  # a ring with two holes: half the programming and setup
    assert lot(10, 8) == lot(60, 8)  # many holes: not simple


def test_parts_of_an_order_share_freight_and_the_minimum():
    from app import pricing
    from app.portal_lines import shared_lot

    cfg = pricing.merged_config(shared_lot({"additive": {"technologies": {"fdm": {"cm3_per_hour": 40}}}}))
    assert cfg["min_lot_charge"] == 0 and cfg["default_freight_per_lot"] == 0 and cfg["additive"]["min_lot_charge"] == 0
    assert cfg["additive"]["technologies"]["fdm"]["cm3_per_hour"] == 40  # your own settings are kept
