"""Assembly drawings: misreads that priced a trainer enclosure at $834k, and the box build read from the notes.

The PDF is generated here (it imitates a real multi-sheet assembly drawing) so no customer drawing is kept in the repo.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import box_build, drawing, drawing_assembly, drawing_quote
from app.main import app

SHEETS = [
    ["RESISTANCE CHECK", "TRAINER ASSEMBLY, FMP", "DWG NO", "FMP-252-A001", "TITLE", "SCALE SHEETCAGE CODE", "5VU62",
     "UNLESS OTHERWISE SPECIFIED", "DIMENSIONS ARE IN INCHES", "3 DEC PLACE ± .005", "1", "2", "3", "4", "GENERAL NOTES:",
     "1. DIMENSIONS SHOWN, THIS DOCUMENT, ARE FOR REFERENCE ONLY.", "2. FINAL CONFIGURATION IS SUBJECT TO CUSTOMER REVIEW/APPROVAL."],
    ["RESISTANCE CHECK", "TRAINER ASSEMBLY, FMP", "FMP-252-A001", "TITLE", "1", "2", "3", "4", "NOTES:",
     '1. COVER PLATE MATERIAL, 0.125" THK. 5052 ALUMINUM.', "2. ENCLOSURE MATERIAL, 14 GA. A1008 MILD CARBON STEEL.",
     "3. SWITCH COVER MATERIAL, 16 GA. A1008 MILD CARBON STEEL.", "4. FINISH FOR NOTES 1 - 3, MATTE BLACK POWDER COAT (OR EQV).",
     "5. SWITCHED COVER SHOWN WITH CAM LOCK (1/4 TURN, KEYED ALIKE).", "(14)", "(5.625)", "(7.75)", "(4.125)", "(18.75)", "(.344)", "RUBBER FOOT (4X)"],
    ["TRAINER ASSEMBLY, FMP", "1", "2", "3", "4", "NOTES:", "1. TEST JACK, 4 MM PANEL MOUNT W/ QC CONTACT(S), BLACK (QTY: 12).",
     "2. INERT COMPONENT(S) INSTALLED NEXT TO ELECTRICAL CIRCUIT SYMBOL.", "3. ENCLOSURE HAS BEEN REMOVED FROM THIS VIEW."],
    ["TRAINER ASSEMBLY, FMP", "1", "2", "3", "4", "NOTES:", "1. PCB ASSEMBLY LAYOUT, COMPONENTS ARE SHOWN FOR REFRENCE.",
     "2. TOGGLE SWITCH, SP3T/DPDT, PANEL MOUNT TYPE W/ PC PINS (QTY: 3).", "3. TOGGLE SWITCH, SPST, PANEL MOUNT TYPE W/ PC PINS (QTY: 12).",
     "4. TERMINAL BLOCK, SCREW CLAMP TYPE (MFR #: 1-282837-2).", "5. MOUNTING HOLES (4X), REQUIRED FOR #6 SIZE HARDWARE.",
     "(12.25)", "MAX", "(2.875)", "MAX", "(1.438)", "(1.25)", "RCT ASSEMBLY (PCB ASSEMBLY LAYOUT)"],
    ["TRAINER ASSEMBLY, FMP", "NOTES:", "1. SILK SCREENING DETAILS, WHITE TEXT/GRAPHICS ON MATTE BLACK PANEL.",
     "2. SILK SCREEN COLOR, BRIGHT WHITE (HEX CODE #: F4F5F0) OR EQV.", "(12.063)", "(.969)"],
]


@pytest.fixture(scope="module")
def pdf(tmp_path_factory) -> Path:
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("asm") / "assembly.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    for lines in SHEETS:
        y = 560
        for ln in lines:
            c.drawString(40, y, ln)
            y -= 16
        c.showPage()
    c.save()
    return path


# ---------------------------------------------------------------- the single-part reader no longer misreads it
def test_alloy_number_is_not_a_thickness():
    line = '1. COVER PLATE MATERIAL, 0.125" THK. 5052 ALUMINUM.'
    g = drawing_quote.extract_geometry(drawing.parse_text(line), line)
    assert g["sheet_thickness"] == 0.125


@pytest.mark.parametrize("line,want", [("THK: .125", 0.125), (".090 THK", 0.09), ("THICKNESS = 3 MM", 0.1181), ("THK. 6061 ALUMINUM", None)])
def test_thickness_forms(line, want):
    assert drawing_quote.extract_geometry(drawing.parse_text(line), line)["sheet_thickness"] == want


def test_gauge_uses_its_own_note_material():
    text = '1. COVER MATERIAL, 0.125" THK 5052 ALUMINUM.\n2. ENCLOSURE MATERIAL, 14 GA. A1008 MILD CARBON STEEL.'
    no_thk = text.replace('0.125" THK ', "")
    g = drawing_quote.extract_geometry(drawing.parse_text(no_thk), no_thk)
    assert g["sheet_thickness"] == 0.0747  # steel gauge table, though the first material note is aluminum


@pytest.mark.parametrize("callout,want", [
    ("MATERIAL, 0.125\" THK. 5052 ALUMINUM", "5052-H32 aluminum"), ("MATERIAL: 14 GA A1008 MILD CARBON STEEL", "A36 / 1018 steel"),
    ("MATL: 16 GA CRS", "A36 / 1018 steel"), ("6061-T6 ALUMINUM BAR", "6061-T6 aluminum")])
def test_materials(callout, want):
    assert drawing.parse_text(callout)["material"]["mapped"] == want


def test_title_next_to_a_bare_label(pdf):
    r = drawing.read_drawing(pdf)
    assert r["title"] == "RESISTANCE CHECK TRAINER ASSEMBLY, FMP"
    assert drawing.nice_title(r["title"]) == "Resistance Check Trainer Assembly, FMP"


def test_implausible_size_is_flagged():
    w = drawing_quote.sanity_warnings({"length": 18.75, "width": 12.25, "height": 5052, "thickness": 0.125}, {"per_part_lines": []})
    assert w and "5052" in w[0]


# ---------------------------------------------------------------- assembly detection and box build
def test_single_part_drawings_are_not_assemblies():
    for f in sorted((Path(__file__).parent / "fixtures" / "drawings").glob("*.pdf")):
        r = drawing.read_drawing(f)
        assert drawing_assembly.detect(r, drawing_assembly.page_texts(f)) is None, f.name


def test_assembly_read_into_a_box_build(pdf):
    r = drawing.read_drawing(pdf)
    a = drawing_assembly.analyze(pdf, r)
    assert a and "assembly drawing" in a["message"]
    bb = a["box_build"]
    e = bb["enclosure"]
    assert (e["length_in"], e["width_in"], e["height_in"]) == (18.75, 14.0, 4.125)  # border zone numbers ignored
    assert e["source"] == "custom" and e["finish"] == "powder_coat" and e["silkscreen_colors"] == 1  # fabricated: priced by hand or linked
    types = {(ln["type"], ln["qty"]) for ln in bb["lines"]}
    assert ("test_jack", 12) in types and ("hardware", 4) in types
    assert any(ln["description"].startswith("Cam lock") for ln in bb["lines"])
    (b,) = bb["pcbs"]
    assert (b["width_in"], b["height_in"]) == (12.25, 2.875)
    assert b["tht_parts"] == 16 and b["tht_joints"] == 3 * 6 + 12 * 2 + 2
    assert any(x["mpn"] == "1-282837-2" for x in b["bom_lines"])
    assert e["mods"]["round_holes"] == 12 + 15 + 1
    assert {f["name"] for f in bb["fabricated"]} == {"Cover Plate", "Enclosure", "Switch Cover"}
    r = box_build.price({**bb, "quantities": [1, 10]}, {})
    # everything it was not sure of must be priced or checked by hand before this is a quote
    assert not r["ready"] and "NOT READY" in r["warnings"][0]
    reasons = " | ".join(f"{i['item']}: {i['reason']}" for i in r["incomplete"])
    for want in ("Custom enclosure", "Cover Plate", "Switch Cover", "Inert components", "layer count"):
        assert want in reasons, want
    # price the custom parts, set the inert parts, confirm the rest: then it is ready
    bb["enclosure"].update(unit_price=180.0, check="")
    for ln in bb["lines"]:
        if ln["needs_quote"]:
            ln.update(unit_price=25.0, check="")
    bb["pcbs"][0]["check"] = ""
    r = box_build.price({**bb, "quantities": [1, 10]}, {})
    assert r["ready"] and not r["incomplete"]
    assert 300 < r["price_breaks"][1]["unit_price"] < r["price_breaks"][0]["unit_price"] < 5000


def test_api_flags_assembly_and_hides_nothing_silently(pdf, tmp_path):
    with TestClient(app) as c:
        with open(pdf, "rb") as f:
            read = c.post("/api/drawings/read", files={"file": ("rct.pdf", f, "application/pdf")}).json()
        assert read["assembly"]["box_build"]["pcbs"]
        q = c.post(f"/api/drawings/{read['drawing_id']}/quote", json={"quantities": [1]}).json()
        assert q["assembly"] and q["confidence"] == "low" and "assembly drawing" in q["warnings"][0]
        assert q["review"]["manual_required"] and not q["review"]["confirmed"]
        assert q["estimate"]["price_breaks"][0]["unit_price"] < 5000  # the single-part read is sane too
        # an assembly cannot be "confirmed" as one part
        q = c.post(f"/api/drawings/{read['drawing_id']}/quote", json={"quantities": [1], "overrides": {"confirmed": True}}).json()
        assert q["review"]["manual_required"]


# ---------------------------------------------------------------- not sure -> manual quote
def test_unsure_single_part_needs_manual_quote_until_checked():
    f = Path(__file__).parent / "fixtures" / "drawings" / "bracket_6061.pdf"
    r = drawing.read_drawing(f)
    text, _ = drawing.extract_pdf_text(f)
    g = drawing_quote.extract_geometry(r, text)
    q = drawing_quote.quote(r, g, {"quantities": [1]}, {})
    assert q["review"]["manual_required"] and "guess" in q["review"]["reasons"][0]
    sized = drawing_quote.quote(r, g, {"quantities": [1], "length": 4, "width": 3, "height": 0.5}, {})
    assert not sized["review"]["manual_required"]  # the user entered the size: nothing left to guess
    checked = drawing_quote.quote(r, g, {"quantities": [1], "confirmed": True}, {})
    assert checked["review"]["confident"] and checked["review"]["confirmed"]
    explicit = Path(__file__).parent / "fixtures" / "drawings" / "sheet_cover.pdf"
    r2 = drawing.read_drawing(explicit)
    t2, _ = drawing.extract_pdf_text(explicit)
    assert not drawing_quote.quote(r2, drawing_quote.extract_geometry(r2, t2), {"quantities": [1]}, {})["review"]["manual_required"]


def test_no_text_and_no_material_need_manual_quote():
    rv = drawing_quote.review({"material": {"mapped": None}}, {"confidence": "none"}, {}, [])
    assert rv["manual_required"] and len(rv["reasons"]) == 2
    assert not drawing_quote.review({"material": {"mapped": None}}, {"confidence": "high"}, {"material": "6061-T6 aluminum"}, [])["manual_required"]


def test_customer_quote_refused_until_manual_items_are_done(pdf):
    f = Path(__file__).parent / "fixtures" / "drawings" / "bracket_6061.pdf"
    r = drawing.read_drawing(f)
    text, _ = drawing.extract_pdf_text(f)
    g = drawing_quote.extract_geometry(r, text)
    unsure = drawing_quote.quote(r, g, {"quantities": [5]}, {})["spec"]
    checked = drawing_quote.quote(r, g, {"quantities": [5], "confirmed": True}, {})["spec"]
    bb = drawing_assembly.analyze(pdf, drawing.read_drawing(pdf))["box_build"]
    with TestClient(app) as c:
        a = c.post("/api/pricing/quotes", json={"spec": unsure}).json()
        assert a["needs_manual"]
        res = c.get(f"/api/quote-tools/{a['id']}/customer-quote")
        assert res.status_code == 400 and "not understood well enough" in res.json()["detail"]
        b = c.post("/api/pricing/quotes", json={"spec": checked}).json()
        assert not b["needs_manual"] and c.get(f"/api/quote-tools/{b['id']}/customer-quote").status_code == 200
        box = c.post("/api/box-build/save", json={**{k: bb[k] for k in ("enclosure", "pcbs", "lines", "wiring", "labor", "options")}, "quantities": [1]}).json()
        assert box["needs_manual"]
        res = c.get(f"/api/quote-tools/{box['id']}/customer-quote")
        assert res.status_code == 400 and "manual price or a check" in res.json()["detail"]
