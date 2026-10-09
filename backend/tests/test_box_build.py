"""Box builds: PCB file reading, assembly BOM import, pricing roll-up and the REST endpoints."""
import copy
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import box_build, pcb_files, pricing
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "pcb"

HARNESS = {"kind": "harness", "name": "W1", "quantities": [1],
           "wires": [{"wire_id": "1", "from_ref": "J1", "from_pin": "1", "to_ref": "P2", "to_pin": "1", "gauge": "20", "spec": "M22759/16", "length_in": 18}],
           "bom": [{"ref": "J1", "kind": "connector", "part_number": "D38999/26WB35PN", "qty": 1}]}


def base_spec(**kw):
    s = {"name": "Console", "quantities": [1, 5, 25],
         "enclosure": {"source": "catalog", "type": "diecast_aluminum", "length_in": 10, "width_in": 8, "height_in": 4},
         "pcbs": [{"name": "Main", "layers": 4, "width_in": 5, "height_in": 4, "smt_placements": 300, "smt_unique": 40, "bom_cost_each": 80}],
         "lines": [{"type": "toggle_switch", "qty": 2, "unit_price": 10}, {"type": "circular_connector", "qty": 1, "unit_price": 100}],
         "labor": {"functional_test_minutes": 20}}
    s.update(kw)
    return s


# ---------------------------------------------------------------- PCB files
def test_kicad_zip_reads_layers_size_placements_and_bom():
    r = pcb_files.parse_files([("fab.zip", (FIX / "kicad_fab.zip").read_bytes())])
    b = r["board"]
    assert b["layers"] == 4
    assert b["width_in"] == pytest.approx(100 / 25.4, abs=0.01) and b["height_in"] == pytest.approx(80 / 25.4, abs=0.01)
    assert b["smt_placements"] == 7 and b["sides"] == 2  # fiducial skipped, one part on the bottom
    assert b["bga"] == 1 and b["fine_pitch"] == 2
    assert b["tht_parts"] == 1 and b["tht_joints"] == 6  # 1x06 header
    assert len(r["bom_lines"]) == 7  # DNP and fiducial lines dropped
    assert any("12 holes" in e for e in r["evidence"])


def test_protel_names_and_inch_units():
    r = pcb_files.parse_files([("p.zip", (FIX / "protel_2layer.zip").read_bytes())])
    assert r["board"] == {"layers": 2, "width_in": 3.0, "height_in": 2.0}
    assert any("No BOM" in w for w in r["warnings"])


def test_bom_alone_counts_placements():
    r = pcb_files.parse_files([("bom.csv", (FIX / "ctrl-bom.csv").read_bytes())])
    assert r["board"]["smt_placements"] == 7 and r["board"]["smt_unique"] == 6  # C1,C2 count twice


def test_kicad_text_pos_format():
    text = "### Module positions\n## Unit = mm\n# Ref     Val       Package                PosX       PosY       Rot  Side\nC1  100n  C_0402  10.0 -5.0 0.0 top\nU1  MCU  QFN-32  20.0 -5.0 0.0 bottom\nFID1 F Fid 1 1 0 top\n"
    c = pcb_files.parse_cpl(text)
    assert c["placements"] == 2 and c["bottom"] == 1 and c["fine_pitch"] == 1 and c["skipped"] == 1


def test_refs_expand_ranges():
    assert pcb_files.expand_refs("R1-R4, C2") == ["R1", "R2", "R3", "R4", "C2"]


def test_zip_with_nothing_useful_is_an_error():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.md", "hello")
    with pytest.raises(pcb_files.PcbFileError):
        pcb_files.parse_files([("x.zip", buf.getvalue())])


# ---------------------------------------------------------------- assembly BOM
def test_assembly_bom_sorted_into_sections():
    a = box_build.parse_assembly_bom(FIX / "assembly_bom.csv")
    e = a["enclosure"]
    assert e["part_number"] == "1590BB" and e["unit_price"] == 14.5 and e["length_in"] == 4.7 and e["type"] == "diecast_aluminum"
    assert [p["name"] for p in a["pcbs"]] == ["Controller PCBA"]
    types = {l["description"][:12]: l["type"] for l in a["lines"]}
    assert types["Toggle switc"] == "toggle_switch"
    assert types["Connector, c"] == "circular_connector"
    assert types["7 in TFT dis"] == "display"
    assert types["Screw, pan h"] == "hardware"
    assert types["Cable assemb"] == "cable_assembly"
    assert [p["description"] for p in a["peripherals"]] == ["Operator manual"]
    assert a["peripherals"][0]["installed"] is False


# ---------------------------------------------------------------- pricing
def test_price_rolls_up_and_breaks_fall_with_quantity():
    r = box_build.price(base_spec(), {})
    units = [b["unit_price"] for b in r["price_breaks"]]
    assert units[0] > units[1] > units[2]
    for b in r["price_breaks"]:
        bd = r["breakdowns"][str(b["quantity"])]
        assert b["total_cost"] == pytest.approx(bd["per_part_cost"] * b["quantity"] + bd["per_lot_cost"], abs=0.05)
        assert sum(bd["sections"].values()) == pytest.approx(b["unit_cost"], abs=0.1)
    assert {"enclosure", "pcbs", "components", "integration", "test"} <= set(r["breakdowns"]["5"]["sections"])


def test_untyped_lines_are_classified_and_wires_estimated():
    s = base_spec(lines=[{"description": "Toggle switch SPDT", "qty": 2}, {"description": "D38999 receptacle", "qty": 1}])
    r = box_build.price(s, {})
    c = r["counts"]
    assert c["terminations"] == {"solder": 6.0, "crimp": 8.0}
    assert c["wires"] == 7  # 14 ends / 2
    assert "estimated" in c["wire_basis"]


def test_linked_quotes_roll_in_at_cost_without_freight():
    bracket = copy.deepcopy(pricing.EXAMPLE_SPEC)
    alone = pricing.estimate({**bracket, "quantities": [10]}, {})
    ex = sum(l["cost"] for l in alone["per_part_lines"] if l["category"] in ("freight", "packaging")) * 10 + \
        sum(l["cost"] for l in alone["per_lot_lines"] if l["category"] in ("freight", "packaging") or l["item"].startswith("certificate of conformance"))
    want = alone["price_breaks"][0]["total_cost"] - ex
    r = box_build.price(base_spec(quantities=[5], children=[{"name": "Bracket", "qty_per": 2, "spec": bracket}]), {})
    line = next(l for l in r["breakdowns"]["5"]["per_part_lines"] if l["item"].startswith("Bracket"))
    assert line["cost"] * 5 == pytest.approx(want, abs=0.1)
    assert "made at" not in line["item"]


def test_bought_child_needs_a_price_and_carries_burden():
    s = base_spec(quantities=[2], children=[{"name": "Bracket", "qty_per": 1, "mode": "buy", "spec": pricing.EXAMPLE_SPEC}])
    with pytest.raises(box_build.BoxBuildError):
        box_build.price(s, {})
    s["children"][0]["buy_unit_price"] = 30
    r = box_build.price(s, {})
    lines = r["breakdowns"]["2"]["per_part_lines"]
    assert any(l["item"].startswith("Bracket") and l["cost"] == 30 for l in lines)
    assert any(l["category"] == "material" for l in lines)


def test_harness_child_means_no_loose_wires():
    r = box_build.price(base_spec(children=[{"name": "W1", "qty_per": 1, "spec": HARNESS}]), {})
    assert r["counts"]["wires"] == 0 and r["counts"]["mates"] >= 2
    assert "wiring" in r["breakdowns"]["1"]["sections"]


def test_nested_box_build_and_depth_limit():
    inner = {**base_spec(quantities=[1]), "kind": "box_build"}
    r = box_build.price({"quantities": [2], "enclosure": {"source": "none"}, "children": [{"name": "Unit", "qty_per": 2, "spec": inner}]}, {})
    assert r["price_breaks"][0]["unit_price"] > 0
    deep = inner
    for _ in range(4):
        deep = {"kind": "box_build", "quantities": [1], "enclosure": {"source": "none"}, "children": [{"name": "n", "qty_per": 1, "spec": deep}]}
    with pytest.raises(box_build.BoxBuildError):
        box_build.price(deep, {})


def test_pcb_buy_mode_uses_break_at_or_below_need():
    pcb = {"name": "CM board", "mode": "buy", "buy_prices": [{"quantity": 1, "unit_price": 50}, {"quantity": 10, "unit_price": 20}]}
    r = box_build.price(base_spec(quantities=[1, 10], pcbs=[pcb]), {})
    p1 = next(l for l in r["breakdowns"]["1"]["per_part_lines"] if "CM price" in l["item"])
    p10 = next(l for l in r["breakdowns"]["10"]["per_part_lines"] if "CM price" in l["item"])
    assert p1["cost"] == 50 and p10["cost"] == 20


def test_pcb_lot_minimum_and_class3():
    small = {"name": "Tiny", "layers": 2, "width_in": 1, "height_in": 1, "smt_placements": 10, "bom_cost_each": 1}
    r = box_build.price(base_spec(quantities=[1], pcbs=[small]), {})
    assert any("lot minimum" in l["item"] for l in r["breakdowns"]["1"]["per_lot_lines"])
    r3 = box_build.price(base_spec(quantities=[1], pcbs=[{**small, "ipc_class": 3}]), {})
    assert r3["price_breaks"][0]["unit_cost"] > r["price_breaks"][0]["unit_cost"]
    assert any("Class 3" in w for w in r3["warnings"])


def test_no_bom_is_a_placeholder_warning():
    r = box_build.price(base_spec(pcbs=[{"name": "B", "width_in": 2, "height_in": 2, "smt_placements": 100}]), {})
    assert any("placeholder guess" in w for w in r["warnings"])


def test_nre_can_be_left_out():
    lab = {"work_instructions": True, "test_fixture_nre": 2000}
    a = box_build.price(base_spec(quantities=[1], labor=lab), {})
    b = box_build.price(base_spec(quantities=[1], labor={**lab, "nre_in_price": False}), {})
    assert a["nre_total"] == b["nre_total"] > 2000
    assert a["price_breaks"][0]["total_cost"] - b["price_breaks"][0]["total_cost"] == pytest.approx(a["nre_total"], abs=0.05)


def test_lab_tests_burn_in_and_first_article_add_lead_time():
    a = box_build.price(base_spec(quantities=[1]), {})
    b = box_build.price(base_spec(quantities=[1], labor={"burn_in_hours": 48, "lab_tests": ["mil_std_810"]}, options={"first_article": True}), {})
    assert b["price_breaks"][0]["lead_time_days"] >= a["price_breaks"][0]["lead_time_days"] + 30 + 2
    assert any("outside lab" in l["item"] for l in b["per_lot_lines"])


def test_empty_build_is_an_error():
    with pytest.raises(box_build.BoxBuildError):
        box_build.price({"quantities": [1], "enclosure": {"source": "none"}}, {})


def test_purchase_list_scales_with_builds():
    s = base_spec(pcbs=[{"name": "Main", "width_in": 2, "height_in": 2, "bom_lines": [{"mpn": "X1", "qty": 3, "unit_price": 1}]}])
    rows = box_build.purchase_rows(s, 10, {})
    part = next(r for r in rows if r[1] == "X1")
    assert part[5] == 31  # 3 x 10 + 2 % attrition, rounded up


def test_shop_rates_accept_box_build_config():
    from app.quotes import _validate_numbers
    _validate_numbers(pricing.merged_config({}))


# ---------------------------------------------------------------- REST
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_api_round_trip(client):
    cat = client.get("/api/box-build/catalog").json()
    assert "toggle_switch" in cat["component_types"] and "mil_std_461" in cat["lab_tests"]
    with open(FIX / "kicad_fab.zip", "rb") as f:
        pcb = client.post("/api/box-build/pcb-parse", files=[("files", ("fab.zip", f, "application/zip"))]).json()
    assert pcb["board"]["layers"] == 4
    with open(FIX / "assembly_bom.csv", "rb") as f:
        bom = client.post("/api/box-build/parse", files={"file": ("bom.csv", f, "text/csv")}).json()
    assert bom["enclosure"]["part_number"] == "1590BB"
    part = client.post("/api/pricing/quotes", json={"spec": pricing.EXAMPLE_SPEC}).json()
    linked = client.get(f"/api/box-build/link/{part['id']}").json()
    body = {"name": "Console", "quantities": [1, 5], "enclosure": bom["enclosure"], "lines": bom["lines"], "peripherals": bom["peripherals"],
            "pcbs": [{**bom["pcbs"][0], **pcb["board"], "bom_lines": pcb["bom_lines"]}],
            "children": [{**linked, "qty_per": 2}], "labor": {"functional_test_minutes": 15}}
    est = client.post("/api/box-build/quote", json=body)
    assert est.status_code == 200, est.text
    saved = client.post("/api/box-build/save", json={**body, "quoted_quantity": 5}).json()
    assert saved["kind"] == "box_build" and saved["quoted_unit_price"] == est.json()["price_breaks"][1]["unit_price"]
    again = client.get(f"/api/box-build/quotes/{saved['id']}").json()
    assert again["spec"]["children"][0]["quote_id"] == part["id"]
    self_link = {**body, "quote_id": saved["id"], "children": [{"quote_id": saved["id"], "name": "me", "spec": again["spec"]}]}
    assert client.post("/api/box-build/save", json=self_link).status_code == 400
    x = client.get(f"/api/box-build/sheet.xlsx?quote_id={saved['id']}")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    pdf = client.get(f"/api/quote-tools/{saved['id']}/customer-quote.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/box-build/quotes/{part['id']}").status_code == 400


# ---------------------------------------------------------------- outside PCB quotes (JLCPCB and the like)
def _board(**kw):
    b = {"name": "Main", "layers": 4, "width_in": 4, "height_in": 3, "smt_placements": 200, "smt_unique": 30, "bom_cost_each": 40, "program_minutes": 3,
         "outside_quotes": [{"vendor": "JLCPCB", "scope": "assembled", "prices": [{"quantity": 5, "unit_price": 28}, {"quantity": 30, "unit_price": 19}],
                             "setup": 25, "shipping": 22, "duty_pct": 25, "lead_days": 14, "url": "https://jlcpcb.com/quote", "quote_ref": "Q123"},
                            {"vendor": "OSH Park", "scope": "bare", "prices": [{"quantity": 3, "unit_price": 12}], "lead_days": 12}]}
    b.update(kw)
    return b


def test_outside_quote_landed_cost_and_vendor_minimum():
    oq = box_build.normalize_outside_quote({"vendor": "JLCPCB", "prices": [{"quantity": 5, "unit_price": 28}], "setup": 25, "shipping": 22, "duty_pct": 25})
    assert oq["country"] == "China"  # known board house
    c = box_build.outside_quote_cost(oq, 2)
    assert c["buy"] == 5 and c["total"] == pytest.approx((28 * 5 + 25 + 22) * 1.25) and "lowest quantity" in c["note"]


def test_estimate_is_kept_and_quotes_compared_at_every_quantity():
    r = box_build.price({"quantities": [1, 10, 50], "enclosure": {"source": "none"}, "pcbs": [_board()]}, {})
    assert [c["quantity"] for c in r["pcb_compare"]] == [1, 10, 50]
    c10 = next(c for c in r["pcb_compare"] if c["quantity"] == 10)
    labels = [o["label"] for o in c10["options"]]
    assert labels == ["Our estimate", "JLCPCB", "OSH Park"] and c10["chosen"] == "estimate"  # default: our estimate
    jlc = c10["options"][1]
    assert jlc["unit"] == pytest.approx((28 * 10 + 25 + 22) * 1.25 / 10 + 3.75 + 3.75 + 37.5 / 10, abs=0.5)  # + kept test, inspection, programming setup
    assert any("10 U.S.C. 4873" in w for w in r["warnings"])


def test_use_a_quote_or_the_lowest():
    use_q = box_build.price({"quantities": [10], "enclosure": {"source": "none"}, "pcbs": [_board(use="q0")]}, {})
    lines = use_q["breakdowns"]["10"]["per_part_lines"]
    assert any("JLCPCB quote, assembled boards" in l["item"] for l in lines)
    assert not any(": components" in l["item"] or "SMT assembly" in l["item"] for l in lines)  # replaced by the assembled quote
    bare = box_build.price({"quantities": [10], "enclosure": {"source": "none"}, "pcbs": [_board(use="q1")]}, {})
    bl = bare["breakdowns"]["10"]["per_part_lines"]
    assert any("OSH Park quote, bare boards" in l["item"] for l in bl) and any(": components" in l["item"] for l in bl)
    assert not any("bare board, 4 layer" in l["item"] for l in bl)  # our fab replaced, our assembly kept
    low = box_build.price({"quantities": [1, 50], "enclosure": {"source": "none"}, "pcbs": [_board(use="lowest")]}, {})
    for c in low["pcb_compare"]:
        assert c["chosen"] == c["cheapest"]


def test_bad_use_falls_back_to_estimate_and_expired_quote_warns():
    b = box_build.normalize_pcbs([_board(use="q9")])[0]
    assert b["use"] == "estimate"
    old = _board()
    old["outside_quotes"][0]["valid_until"] = "2020-01-01"
    r = box_build.price({"quantities": [5], "enclosure": {"source": "none"}, "pcbs": [old]}, {})
    assert any("expired 2020-01-01" in w for w in r["warnings"])


def test_purchase_list_names_the_quote_used():
    rows = box_build.purchase_rows({"enclosure": {"source": "none"}, "pcbs": [_board(use="q0")]}, 10, {})
    assert rows[0][0] == "PCB from JLCPCB (assembled)" and rows[0][-1] == "https://jlcpcb.com/quote"
