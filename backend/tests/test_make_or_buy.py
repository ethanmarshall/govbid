"""Bought or made: unknown parts in a model are not priced as machined just because we don't recognize them."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import part_kind as PK
from app import portal
from app.main import app

FIX = Path(__file__).parent / "fixtures"


def g(name, qty=1, dims=(2, 1, 0.5), body_names=None, **kw):
    return {"name": name, "qty": qty, "raw_names": [name], "body_names": body_names or [name] * qty,
            "bounding_box": dict(zip(("length", "width", "height"), dims)), **kw}


def test_names_part_numbers_and_choices():
    assert PK.decide(g("Mounting Plate Hardware <3>"))[0] is True  # hardware wins over "plate"
    assert PK.decide(g("Bearing housing"))[0] is False  # made word beats a bought word
    assert PK.decide(g("Bearing"))[0] is True
    assert PK.decide(g("91251A540"))[0] is True and PK.decide(g("2061"))[0] is True  # McMaster, 80/20
    assert PK.decide(g("Part 7"))[0] is False  # unknown: made, with no claim of why
    assert PK.decide(g("Bearing"), choice="make")[:2] == (False, "you chose")
    assert PK.decide(g("Part 7"), bom_buy=True)[0] is True
    rules = PK.learn({}, "part 7", True)
    assert PK.decide(g("Part 7"), rules=rules)[2] == "learned"
    assert PK.learn(rules, "part 7", False) == {"bought": {}, "made": {"part 7": 1}}


def test_a_set_of_small_unnamed_pieces_is_a_bought_unit():
    pieces = [g("Slide Unit <1>", 2, (1.6, 0.8, 0.5), ["Slide Unit <1>", "Slide Unit <2>"]),
              g("Slide Unit <1>", 2, (1.2, 0.6, 0.2), ["Slide Unit <1>", "Slide Unit <2>"])]
    st = PK.structure(pieces)
    assert PK.decide(pieces[0], st=st)[2] == "model"
    big = [g("Weld Frame <1>", 1, (40, 20, 2), ["Weld Frame <1>"]), g("Weld Frame <1>", 1, (30, 2, 2), ["Weld Frame <1>"])]
    assert PK.decide(big[0], st=PK.structure(big))[0] is False  # "frame" is made, and large


@pytest.fixture
def client():
    portal.QUOTE_LIMIT.clear()
    portal.REPRICE_LIMIT.clear()
    with TestClient(app) as c:
        assert c.put("/api/portal/settings", json={"enabled": True}).status_code == 200
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


def test_vendor_unit_is_one_bought_line_and_switches(client):
    step = FIX / "cad" / "vendor_asm.step"
    q = client.post("/api/public/quote", data={"quantity": "1"},
                    files=[("files", (step.name, step.read_bytes(), "application/octet-stream"))]).json()
    items = q["result"]["items"]
    unit = [ln for ln in items if ln["name"] == "Slide Unit"]
    assert len(unit) == 1 and unit[0]["kind"] == "bought" and unit[0]["qty"] == 2  # two units, not six machined pieces
    assert any(f["label"] == "Why bought" for f in unit[0]["facts"])
    plate = next(ln for ln in items if ln["name"] == "Base Plate")
    assert plate["kind"] == "part" and any(o["process"] == "bought" for o in plate["options"]["processes"])
    # the customer says the unit is made here: priced as made parts
    r = client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "lines": {unit[0]["key"]: {"process": "make"}}}).json()
    made = [ln for ln in r["result"]["items"] if ln["name"].startswith("Slide Unit")]
    assert made and all(ln["kind"] == "part" for ln in made)
    # in review, you mark the base plate bought; parts with that name are bought on the next quote
    rid = next(x["id"] for x in client.get("/api/portal/requests?include_drafts=true").json() if x["ref"] == q["ref"])
    d = client.put(f"/api/portal/requests/{rid}/lines", json={"lines": {plate["key"]: {"process": "bought"}}}).json()
    assert next(ln for ln in d["internal"]["items"] if ln["name"] == "Base Plate")["kind"] == "bought"
    q2 = client.post("/api/public/quote", data={"quantity": "1"},
                     files=[("files", (step.name, step.read_bytes(), "application/octet-stream"))]).json()
    assert next(ln for ln in q2["result"]["items"] if ln["name"] == "Base Plate")["kind"] == "bought"
    from app.db import SessionLocal

    with SessionLocal() as db:  # leave the shop's rules as they were for other tests
        s = portal.get_settings(db)
        s.part_rules = None
        db.commit()


def test_shape_checks_for_unnamed_bodies():
    screw = g("CirPattern2", 4, (1.26, 0.38, 0.38))
    geo = {"faces": {"plane": 20, "cylinder": 40, "cone": 105, "sphere": 0, "torus": 2, "freeform": 2}, "volume": 0.057, "holes": []}
    assert PK.decide(screw, geo=geo)[2] == "model"  # modeled threads
    ball = g("Shaft Assembly <1>", 24, (0.29, 0.29, 0.29), ["Shaft Assembly <1>"] * 24)
    assert PK.decide(ball, geo={"faces": {"sphere": 1}, "volume": 0.013, "holes": []})[0] is True
    shaft = g("Shaft Assembly <1>", 1, (10, 1, 1), ["Shaft Assembly <1>"])
    assert PK.decide(shaft, geo={"faces": {"plane": 4, "cylinder": 20, "cone": 4}, "volume": 7.7, "holes": [1]})[0] is False
    washer = g("Imported1", 6, (0.62, 0.62, 0.05))
    assert PK.decide(washer, geo={"faces": {"plane": 2, "cylinder": 2, "torus": 2}, "volume": 0.012, "holes": [{}]})[0] is True
    # the customer's own sub-assembly name does not make every body in it a made part, nor a bought unit
    pieces = [g("Handwheel Assembly <1>", 1, (7, 7, 1.85), ["Handwheel Assembly <1>"]), g("Handwheel Assembly <1>", 1, (3.75, 1, 1), ["Handwheel Assembly <1>"])]
    assert PK.decide(pieces[0], st=PK.structure(pieces), geo={"faces": {"plane": 40, "cylinder": 20}, "volume": 36, "holes": [1] * 14})[0] is False
