"""Quoting a part from its PDF drawing alone."""
from pathlib import Path

from fastapi.testclient import TestClient

from app import drawing, drawing_quote
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "drawings"


def test_extract_geometry_from_text():
    p = FIX / "bracket_6061.pdf"
    read = drawing.read_drawing(p)
    text, _ = drawing.extract_pdf_text(p)
    g = drawing_quote.extract_geometry(read, text)
    assert g["envelope_in"]["length"] > 0 and g["confidence"] in ("low", "medium", "high")
    assert g["tapped_holes"] >= 1 and g["evidence"]


def test_quote_endpoint_overrides_and_save():
    with TestClient(app) as c:
        d = c.post("/api/drawings/read", files={"file": ("bracket.pdf", (FIX / "bracket_6061.pdf").read_bytes(), "application/pdf")}).json()
        r = c.post(f"/api/drawings/{d['drawing_id']}/quote", json={"quantities": [1, 10]})
        assert r.status_code == 200, r.text
        base = r.json()
        prices = [b["unit_price"] for b in base["estimate"]["price_breaks"]]
        assert prices[0] > prices[1] > 0 and base["spec"]["drawing"]["drawing_id"] == d["drawing_id"]
        big = c.post(f"/api/drawings/{d['drawing_id']}/quote", json={"quantities": [10], "overrides": {"length": 12, "width": 8, "height": 2}}).json()
        assert big["estimate"]["price_breaks"][0]["unit_price"] > base["estimate"]["price_breaks"][1]["unit_price"]
        assert big["inputs"]["length"] == 12
        printed = c.post(f"/api/drawings/{d['drawing_id']}/quote", json={"quantities": [10], "overrides": {"process": "3d_print", "material": "PETG"}}).json()
        assert printed["spec"]["operations"][0]["type"] == "additive"
        saved = c.post("/api/pricing/quotes", json={"spec": base["spec"], "quoted_quantity": 10})
        assert saved.status_code == 200
        assert c.post("/api/drawings/ffff/quote", json={}).status_code in (400, 404)
