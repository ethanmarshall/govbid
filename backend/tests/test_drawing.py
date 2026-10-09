"""Engineering drawing reader: text parsing, material/finish/tolerance mapping, scanned drawings, API."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import drawing, pricing
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "drawings"


@pytest.fixture(scope="module")
def reads():
    return {n: drawing.read_drawing(FIX / f"{n}.pdf") for n in ("bracket_6061", "shaft_304", "frame_weldment", "scanned")}


# ---------------------------------------------------------------- fixture drawings
def test_bracket_title_block(reads):
    r = reads["bracket_6061"]
    assert r["text_found"] and r["pages"] == 1
    assert r["part_number"] == "12345-001"
    assert r["cage"] == "1ABC5"
    assert r["revision"] == "B"
    assert r["title"] == "BRACKET, MOUNTING"


def test_bracket_callouts(reads):
    r = reads["bracket_6061"]
    assert r["material"]["mapped"] == "6061-T6 aluminum"
    assert "6061-T6" in r["material"]["raw"]
    assert [f["mapped"] for f in r["finishes"]] == ["anodize (Type II)"]
    assert r["tolerance"]["tightest_in"] == 0.002 and r["tolerance"]["class"] == "tight"
    assert r["threads"]["count"] == 6 and r["holes_tapped_guess"] == 6
    assert "1/4-20 UNC-2B (4X)" in r["threads"]["callouts"]
    assert r["surface_finish"]["ra_microin"] == 125
    assert r["inspection"]["first_article"] and r["inspection"]["material_certs"]
    specs = {s["standard"] for s in r["specs"]}
    assert {"MIL-PRF-8625", "MIL-STD-130", "AS9102", "ASTM B209"} <= specs
    assert len(r["notes"]) == 7 and r["notes"][0].startswith("1. INTERPRET")


def test_bracket_distribution_and_export(reads):
    r = reads["bracket_6061"]
    assert r["distribution"]["letter"] == "D"
    assert r["export_controlled"] is True
    assert any("Distribution statement D" in w for w in r["warnings"])
    assert any("Export-controlled" in w for w in r["warnings"])


def test_shaft(reads):
    r = reads["shaft_304"]
    assert (r["part_number"], r["drawing_number"], r["cage"], r["revision"]) == ("8842-17", "8842", "3XY77", "C")
    assert r["material"]["mapped"] == "304 stainless"
    assert [f["mapped"] for f in r["finishes"]] == ["passivate (stainless)"]  # "DO NOT PAINT" is not a finish
    assert r["tolerance"]["class"] == "precision"
    t = r["threads"]
    assert t["external"] == 1 and t["helicoils"] == 2
    assert t["count"] == 4  # 3/8-24 UNF-2A, 1/4-20 UNC-2B, 2X M6x1.0-6H
    assert r["heat_treat"] and r["surface_finish"]["ra_microin"] == 32
    assert r["distribution"]["letter"] == "A" and not r["export_controlled"]
    assert not any("Distribution statement" in w for w in r["warnings"])


def test_weldment_metric(reads):
    r = reads["frame_weldment"]
    assert r["part_number"] == "WF-2201" and r["revision"] == "3" and r["cage"] == "9ZZ01"
    assert r["material"]["mapped"] == "A36 / 1018 steel"
    assert {f["mapped"] for f in r["finishes"]} == {"zinc plate", "paint (wet)"}
    assert r["tolerance"]["metric_drawing"] and r["tolerance"]["class"] == "tight"  # ±0.1 mm = ±.0039 in
    assert r["welding"]["specs"] == ["AWS D1.1"]
    assert r["inspection"]["first_article"]
    assert r["distribution"]["letter"] == "C" and r["export_controlled"]


def test_scanned_without_key(reads):
    r = reads["scanned"]
    assert r["text_found"] is False
    assert r["part_number"] == "" and r["material"]["mapped"] is None
    assert "scanned" in r["warnings"][0]


# ---------------------------------------------------------------- mapping rules
@pytest.mark.parametrize("raw,name", [
    ("ALUMINUM 6061-T6", "6061-T6 aluminum"),
    ("AL 6061 PER QQ-A-250/11", "6061-T6 aluminum"),
    ("ASTM B209 6061 T651 PLATE", "6061-T6 aluminum"),
    ("QQ-A-250/11", "6061-T6 aluminum"),
    ("7075-T651 PER AMS-QQ-A-250/12", "7075-T6 aluminum"),
    ("5052-H32 SHEET", "5052-H32 aluminum"),
    ("304 CRES", "304 stainless"),
    ("ASTM A240 TYPE 304", "304 stainless"),
    ("CRES 316L", "316 stainless"),
    ("ASTM A36", "A36 / 1018 steel"),
    ("1018 CRS", "A36 / 1018 steel"),
    ("AISI 4140 Q&T", "4140 steel"),
    ("BRASS C36000", "brass 360"),
    ("COPPER C11000", "copper 110"),
    ("DELRIN 150 BLACK", "delrin (acetal)"),
    ("ACETAL COPOLYMER", "delrin (acetal)"),
    ("G-10 GLASS EPOXY", "G10 / FR4"),
    ("FR4 .062", "G10 / FR4"),
    ("TITANIUM 6AL-4V", None),
])
def test_material_mapping(raw, name):
    assert drawing.map_material(raw) == name


def test_mapped_names_exist_in_pricing():
    names = {n for _, n in drawing.MATERIAL_STRONG + drawing.MATERIAL_WEAK}
    assert names <= set(pricing.DEFAULT_CONFIG["materials"])
    fins = {n for _, n in drawing.FINISH_RULES if n}
    assert fins <= set(pricing.DEFAULT_CONFIG["finishes"])


@pytest.mark.parametrize("text,finish", [
    ("FINISH: ANODIZE PER MIL-PRF-8625 TYPE III CLASS 1", "hard anodize (Type III)"),
    ("HARDCOAT ANODIZE .002 THK", "hard anodize (Type III)"),
    ("ANODIZE PER MIL-A-8625, TYPE II, CLASS 1", "anodize (Type II)"),
    ("CHEM FILM PER MIL-DTL-5541 TYPE II CLASS 3", "chem film (MIL-DTL-5541)"),
    ("PASSIVATE PER ASTM A967", "passivate (stainless)"),
    ("PASSIVATE PER AMS 2700 METHOD 1", "passivate (stainless)"),
    ("ZINC PLATE PER ASTM B633 TYPE III FE/ZN 8", "zinc plate"),
    ("BLACK OXIDE PER MIL-DTL-13924 CLASS 1", "black oxide"),
    ("POWDER COAT BLACK", "powder coat"),
    ("PRIME AND PAINT PER MIL-DTL-53039", "paint (wet)"),
])
def test_finish_mapping(text, finish):
    assert [f["mapped"] for f in drawing.parse_text(text)["finishes"]] == [finish]


def test_type_one_anodize_is_unmapped_with_warning():
    r = drawing.parse_text("ANODIZE PER MIL-PRF-8625 TYPE IC")
    assert [f["mapped"] for f in r["finishes"]] == [None]
    assert any("no matching finish" in w for w in r["warnings"])


@pytest.mark.parametrize("tol,cls", [(0.010, "standard"), (0.005, "standard"), (0.004, "tight"), (0.002, "tight"), (0.001, "precision"), (0.0005, "precision"), (None, None)])
def test_tolerance_class(tol, cls):
    assert drawing.tolerance_class(tol) == cls


def test_tolerance_text_forms():
    assert drawing.parse_text("TOLERANCES .XX ±.01 .XXX ±.005")["tolerance"]["class"] == "standard"
    assert drawing.parse_text("Ø.5000 +/- .0005")["tolerance"]["class"] == "precision"
    assert drawing.parse_text("ANGLES ±0.5°")["tolerance"]["class"] is None  # angular, not linear


def test_threads_and_counts():
    r = drawing.parse_text("6X #8-32 UNC-2B THRU\n1/2-13 UNC-2B 4 PLACES\nM8x1.25-6H\n.250-28 UNF-2A")
    t = r["threads"]
    assert t["count"] == 12 and t["internal"] == 11 and t["external"] == 1


def test_negated_paint_is_ignored():
    assert drawing.parse_text("NOTE 5. DO NOT PAINT MATING SURFACES")["finishes"] == []


# ---------------------------------------------------------------- quote options
def test_quote_options_from_bracket(reads):
    o = drawing.quote_options(reads["bracket_6061"], list(pricing.DEFAULT_CONFIG["materials"]), list(pricing.DEFAULT_CONFIG["finishes"]))
    assert o == {"material": "6061-T6 aluminum", "finishes": ["anodize (Type II)"], "tolerance": "tight", "threaded_holes": 6,
                 "part_number": "12345-001", "name": "Bracket, Mounting", "material_certs": True, "first_article": True}


def test_quote_options_skip_unknown():
    r = drawing.parse_text("MATERIAL: INCONEL 718\nTYPE III HARD ANODIZE AND ANODIZE PER MIL-PRF-8625")
    o = drawing.quote_options(r, ["6061-T6 aluminum"], ["hard anodize (Type III)", "anodize (Type II)"])
    assert "material" not in o
    assert o["finishes"] == ["hard anodize (Type III)"]
    assert drawing.quote_options(drawing.parse_text("")) == {}


def test_quote_options_helicoil_inserts(reads):
    o = drawing.quote_options(reads["shaft_304"])
    assert o["inserts"] == 2 and o["threaded_holes"] == 3 and o["tolerance"] == "precision"
    assert "material_certs" not in o and "first_article" not in o


# ---------------------------------------------------------------- AI read for scanned drawings
def test_scanned_ai_read(monkeypatch):
    seen = {}

    def fake(data):
        seen["pdf"] = data[:4]
        return {"text": "NOTES:\n1. BREAK SHARP EDGES.\n2. FIRST ARTICLE INSPECTION REQUIRED.", "part_number": "77-100", "cage": "4QQ12",
                "revision": "A", "title": "COVER", "material": "6061-T6 ALUMINUM", "finishes": ["CHEM FILM PER MIL-DTL-5541"],
                "general_tolerance": ".XXX ±.003", "thread_callouts": ["4X 6-32 UNC-2B"], "distribution_statement": "D", "export_warning": True}

    monkeypatch.setattr(drawing, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(drawing, "_claude_read_pdf", fake)
    r = drawing.read_drawing(FIX / "scanned.pdf", use_ai=True)
    assert seen["pdf"] == b"%PDF"
    assert r["ai_used"] and not r["text_found"]
    assert (r["part_number"], r["cage"], r["revision"], r["title"]) == ("77-100", "4QQ12", "A", "COVER")
    assert r["material"]["mapped"] == "6061-T6 aluminum"
    assert [f["mapped"] for f in r["finishes"]] == ["chem film (MIL-DTL-5541)"]
    assert r["tolerance"]["class"] == "tight" and r["threads"]["count"] == 4
    assert r["distribution"]["letter"] == "D" and r["export_controlled"]
    assert r["inspection"]["first_article"]
    assert "read by Claude" in r["warnings"][0]


def test_scanned_ai_failure_is_a_warning(monkeypatch):
    def boom(data):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(drawing, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(drawing, "_claude_read_pdf", boom)
    r = drawing.read_drawing(FIX / "scanned.pdf", use_ai=True)
    assert not r["ai_used"] and "rate limited" in r["warnings"][0]


def test_scanned_ai_requested_without_key():
    r = drawing.read_drawing(FIX / "scanned.pdf", use_ai=True)
    assert not r["ai_used"] and "ANTHROPIC_API_KEY" in r["warnings"][0]


def test_claude_request_shape(monkeypatch):
    """The SDK call sends the PDF as a base64 document block and parses JSON out of the reply."""
    import anthropic

    calls = {}

    class Block:
        type = "text"
        text = 'Here you go: {"text": "PART NO: 5-1", "part_number": "5-1"}'

    class Msgs:
        def create(self, **kw):
            calls.update(kw)
            return type("M", (), {"content": [Block()]})()

    class Fake:
        def __init__(self, api_key):
            self.messages = Msgs()

    monkeypatch.setattr(anthropic, "Anthropic", Fake)
    out = drawing._claude_read_pdf(b"%PDF-1.4 test")
    assert out["part_number"] == "5-1"
    doc = calls["messages"][0]["content"][0]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf" and doc["source"]["type"] == "base64"
    assert calls["model"]


# ---------------------------------------------------------------- API
def test_api_read_and_fetch():
    with TestClient(app) as c:
        data = (FIX / "bracket_6061.pdf").read_bytes()
        r = c.post("/api/drawings/read", files={"file": ("bracket.pdf", data, "application/pdf")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["drawing_id"]) == 32 and d["filename"] == "bracket.pdf"
        assert d["quote_options"]["material"] == "6061-T6 aluminum"
        assert d["quote_options"]["first_article"] is True
        assert d["export_controlled"] and d["distribution"]["letter"] == "D"

        again = c.post("/api/drawings/read", files={"file": ("copy.pdf", data, "application/pdf")}).json()
        assert again["drawing_id"] == d["drawing_id"]  # same content, same id

        info = c.get(f"/api/drawings/{d['drawing_id']}").json()
        assert info["part_number"] == "12345-001" and info["filename"] == "bracket.pdf"
        f = c.get(f"/api/drawings/{d['drawing_id']}/file")
        assert f.status_code == 200 and f.content[:4] == b"%PDF"
        assert c.get("/api/drawings/" + "0" * 32).status_code == 404
        assert c.get("/api/drawings/not-a-drawing-id").status_code == 400


def test_api_rejects_non_pdf():
    with TestClient(app) as c:
        r = c.post("/api/drawings/read", files={"file": ("x.pdf", b"hello", "application/pdf")})
        assert r.status_code == 400


def test_api_scanned_with_ai(monkeypatch):
    monkeypatch.setattr(drawing, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(drawing, "_claude_read_pdf", lambda data: {"text": "", "part_number": "SCN-1", "material": "304 CRES"})
    with TestClient(app) as c:
        files = {"file": ("scan.pdf", (FIX / "scanned.pdf").read_bytes(), "application/pdf")}
        plain = c.post("/api/drawings/read", files=files).json()
        assert plain["text_found"] is False and plain["quote_options"] == {}
        ai = c.post("/api/drawings/read", files=files, data={"use_ai": "true"}).json()
        assert ai["ai_used"] and ai["quote_options"] == {"material": "304 stainless", "part_number": "SCN-1"}
