"""Designing a part on the website: the part builder, previews, pricing, attaching to an idea, and the AI assistant."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import design, design_ai, portal, portal_api
from app.main import app

L_BRACKET = {"type": "l_bracket", "name": "Sensor bracket", "units": "in",
             "params": {"leg_a": 2, "leg_b": 3, "width": 1.5, "thickness": 0.125, "bend_radius": 0.125,
                        "holes_a": [{"x": 1.25, "y": 0.75, "diameter": 0.201}], "holes_b": [{"x": 2.25, "y": 0.75, "diameter": 0.201}]}}


@pytest.fixture
def client(monkeypatch):
    for lim in (portal.QUOTE_LIMIT, portal.REPRICE_LIMIT, portal.SUBMIT_LIMIT, portal_api.DESIGN_LIMIT, portal_api.ASSIST_LIMIT):
        lim.clear()
    monkeypatch.setattr(portal, "notify", lambda req, s: None)
    with TestClient(app) as c:
        c.put("/api/portal/settings", json={"enabled": True})
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


@pytest.mark.parametrize("t", design.TYPES)
def test_every_part_type_builds_from_its_defaults(t):
    tpl = next(x for x in design.templates() if x["type"] == t)
    r = design.render({"type": t, "params": tpl["default_params"]})
    assert r["mesh"]["triangles"] > 10 and "<svg" in r["drawing"] and r["summary"][0]["label"] in ("Part", "Build")


def test_sizes_are_checked():
    bad = [({"type": "plate", "params": {"length": 6, "width": 4, "thickness": 0.25, "holes": [{"x": 0, "y": 0, "diameter": 0.25}]}}, "off the edge"),
           ({**L_BRACKET, "params": {**L_BRACKET["params"], "holes_a": [{"x": 0.1, "y": 0.75, "diameter": 0.2}]}}, "in the bend"),
           ({"type": "plate", "params": {"length": 100, "width": 4, "thickness": 0.25}}, "between"),
           ({"type": "plate", "params": {"length": "six", "width": 4, "thickness": 0.25}}, "number"),
           ({"type": "flange", "params": {"diameter": 4, "thickness": 0.4, "bore": 1, "bolt_circle": {"count": 40, "diameter": 3, "hole_diameter": 0.3}}}, "overlap"),
           ({"type": "rocket", "params": {}}, "part type")]
    for spec, words in bad:
        with pytest.raises(design.DesignError, match=words):
            design.clean(spec)


def test_millimeters_stay_millimeters():
    r = design.render({"type": "plate", "units": "mm", "params": {"length": 100, "width": 50, "thickness": 3}})
    assert r["units"] == "mm" and r["size"] == [100.0, 50.0, 3.0] and r["spec"]["params"]["length"] == 100
    assert any(row["text"] == "100 mm" for row in r["summary"])


def test_preview_and_price_a_design(client):
    r = client.post("/api/public/design/preview", json={"spec": L_BRACKET})
    assert r.status_code == 200 and r.json()["size"] == [2.0, 1.5, 3.0]
    assert client.post("/api/public/design/preview", json={"spec": {"type": "plate", "params": {}}}).status_code == 400
    q = client.post("/api/public/design/quote", json={"spec": L_BRACKET, "quantity": 10, "material": "6061-T6 aluminum"}).json()
    assert q["result"]["kind"] == "instant" and q["token"] and q["files"][0]["name"] == "Sensor_bracket.step"
    assert q["checkout"]["eligible"] and "Designed on the website" in q["notes"] and "Base leg: 2 in" in q["notes"]
    assert q["result"]["items"][0]["qty"] == 10


def test_attach_a_design_to_a_project_idea(client):
    payload = {"contact": {"name": "Dana Lee", "email": "dana@example.com", "accept_terms": True},
               "concept": {"title": "Sensor mount", "description": "A bracket that holds a pressure sensor on a trainer panel."},
               "design": L_BRACKET}
    r = client.post("/api/public/concept", data={"payload": json.dumps(payload)})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["files"][0]["name"] == "Sensor_bracket.step"
    brief = {x["label"]: x["text"] for x in v["concept"]}
    assert "Upright leg: 3 in" in brief["Design made on the site"]


class _Block(SimpleNamespace):
    def model_dump(self, exclude_none=False):
        return {k: v for k, v in self.__dict__.items() if not (exclude_none and v is None)}


def _fake_client(replies):
    calls = []

    class Msgs:
        def create(self, **kw):
            calls.append(kw)
            return replies.pop(0)
    return SimpleNamespace(messages=Msgs()), calls


def test_assistant_is_off_without_a_key(client, monkeypatch):
    monkeypatch.setattr(design_ai, "ANTHROPIC_API_KEY", "")
    assert not client.get("/api/public/info").json()["design"]["ai"]
    assert client.post("/api/public/design/assistant", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 404


def test_assistant_builds_and_fixes_a_design(client, monkeypatch):
    monkeypatch.setattr(design_ai, "ANTHROPIC_API_KEY", "sk-test")
    bad = {**L_BRACKET, "params": {**L_BRACKET["params"], "holes_a": [{"x": 0.1, "y": 0.75, "diameter": 0.2}]}}
    replies = [
        SimpleNamespace(stop_reason="tool_use", content=[_Block(type="text", text="Here is a first try."),
                                                         _Block(type="tool_use", id="t1", name="set_design", input=bad)]),
        SimpleNamespace(stop_reason="tool_use", content=[_Block(type="tool_use", id="t2", name="set_design", input=L_BRACKET)]),
        SimpleNamespace(stop_reason="end_turn", content=[_Block(type="text", text="I made a 2 x 3 in bracket from 1/8 in aluminum.")]),
    ]
    fake, calls = _fake_client(replies)
    monkeypatch.setattr(design_ai, "_client", lambda: fake)
    assert client.get("/api/public/info").json()["design"]["ai"]
    r = client.post("/api/public/design/assistant", json={"messages": [{"role": "user", "content": "I need an L bracket for a sensor, 2 by 3 inches"}]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["reply"].startswith("I made a 2 x 3 in bracket") and out["spec"]["type"] == "l_bracket" and out["render"]["size"] == [2.0, 1.5, 3.0]
    results = [b for m in calls[-1]["messages"] if isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
    assert results[0].get("is_error") and "bend" in results[0]["content"] and not results[1].get("is_error")  # the error went back to Claude to fix
    assert "Sensor" not in calls[0]["system"].split("right now")[0]  # rules first, the current design after


def test_assistant_history_is_trimmed_and_checked(client, monkeypatch):
    monkeypatch.setattr(design_ai, "ANTHROPIC_API_KEY", "sk-test")
    assert client.post("/api/public/design/assistant", json={"messages": [{"role": "assistant", "content": "hello"}]}).status_code == 400
    fake, calls = _fake_client([SimpleNamespace(stop_reason="end_turn", content=[_Block(type="text", text="What size?")])])
    monkeypatch.setattr(design_ai, "_client", lambda: fake)
    long = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 5000} for i in range(60)] + [{"role": "user", "content": "a plate"}]
    r = client.post("/api/public/design/assistant", json={"messages": long})
    assert r.status_code == 200 and r.json()["spec"] is None
    sent = calls[0]["messages"]
    assert sent[0]["role"] == "user" and sum(len(m["content"]) for m in sent) <= design_ai.MAX_TOTAL + 4
    monkeypatch.setitem(design_ai._day, "n", 10 ** 9)
    monkeypatch.setitem(design_ai._day, "date", __import__("datetime").date.today().isoformat())
    assert "busy" in client.post("/api/public/design/assistant", json={"messages": [{"role": "user", "content": "hi"}]}).json()["detail"]


CART = {"type": "frame", "name": "Rolling cart", "units": "in",
        "params": {"width": 36, "depth": 26, "height": 33.75, "post_profile": "1530", "rail_profile": "1515", "base": "casters",
                   "doors": [{"face": "front", "leaves": 1, "panel": "PANEL-PC-250"}, {"face": "back", "leaves": 1, "panel": "PANEL-PC-250"}]}}


def test_frame_cut_list_uses_butt_joints():
    from app import frame

    spec = design.clean(CART)
    cuts = {(g["profile"], g["length"]): g["qty"] for g in frame.cut_list(frame.members(spec["params"]))}
    assert cuts[("1530", 33.75)] == 4  # corner posts, full height
    assert cuts[("1515", 33.0)] == 4  # front and back rails between 1.5 in post faces
    assert cuts[("1515", 20.0)] == 4  # side rails between the 3 in post faces
    assert cuts[("1515", 30.5)] == 4 and cuts[("1515", 29.75)] == 4  # door stiles and rails, 1/8 in gaps
    r = design.render(CART)
    assert any(x["label"] == "Cut 1530" for x in r["summary"]) and r["mesh"]["triangles"] > 500


def test_frame_checks():
    bad = [({"width": 4}, "Width"), ({"post_profile": "9999"}, "Corner post"), ({"rail_profile": "20-2020"}, "one series"),
           ({"doors": [{"face": "top"}]}, "face"), ({"levels": [{"z": 100}]}, "Level 1")]
    for change, words in bad:
        with pytest.raises(design.DesignError, match=words):
            design.clean({**CART, "params": {**CART["params"], **change}})


def test_frame_is_quoted_from_its_parts_list(client):
    q = client.post("/api/public/design/quote", json={"spec": CART, "quantity": 2}).json()
    assert q["result"]["kind"] == "estimate" and q["result"]["total_low"] > 0
    assert [f["name"] for f in q["files"]] == ["Rolling_cart (frame design).json", "Rolling_cart.step"]
    it = q["result"]["items"][0]
    assert it["qty"] == 2 and it["view"] and any(f["label"] == "Cut 1530" for f in it["facts"])
    assert not q["checkout"]["eligible"]


def test_uploaded_frame_is_priced_as_extrusion_not_machined(client):
    """A cart model (here the designer's own STEP) is priced as cut-to-length extrusion plus hardware."""
    name, data, _ = design.step_for({**CART, "params": {**CART["params"], "doors": [], "base": "none"}})  # no caster bodies
    q = client.post("/api/public/quote", data={"quantity": "1"}, files=[("files", ("cart.step", data))]).json()
    items = q["result"]["items"]
    frame_lines = [i for i in items if i["kind"] == "frame"]
    assert len(frame_lines) == 1, [(i["name"], i.get("process_label")) for i in items]
    facts = {f["label"]: f["value"] for f in frame_lines[0]["facts"]}
    assert facts["Cut 1530"].startswith("4 x 33 3/4 in") and "Cut 1515" in facts
    assert not [i for i in items if i.get("process_label", "").startswith("CNC")]


def test_tslot_names_and_hardware():
    from app import tslot

    assert tslot.hardware_for(["Front_door_hinge_reference_0", "Front_door_hinge_reference_1"]) == ("HINGE", 2)
    assert tslot.hardware_for(["Caster_reference_0_0_wheel", "Caster_reference_0_0_fork_1", "Caster_reference_1_0_wheel"]) == ("CASTER", 2)
    assert tslot.hardware_for(["Locking_caster_2"])[0] == "CASTER-LOCK"
    assert tslot.hardware_for(["Door_pull_handle"])[0] == "HANDLE" and tslot.hardware_for(["Side_plate"]) == (None, 0)


def test_thick_flat_plate_is_waterjet_cut():
    from app import cad

    spec = design.clean({"type": "plate", "params": {"length": 30, "width": 20, "thickness": 0.5, "holes": [{"x": 2, "y": 2, "diameter": 0.344}]}})
    g = cad.analyze(design.build(spec))
    assert g["sheet_metal"] and g["sheet_metal"]["plate"] and g["suggested_process"] == "sheet_metal"


def test_tslot_joints_measured_from_geometry():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    from app import tslot

    mm = 25.4
    box = lambda x, y, z, dx, dy, dz: BRepPrimAPI_MakeBox(gp_Pnt(x * mm, y * mm, z * mm), dx * mm, dy * mm, dz * mm).Shape()
    solids = [box(0, 0, 0, 1.5, 3, 30), box(1.5, 0, 28.5, 20, 1.5, 1.5), box(40, 0, 0, 1.5, 1.5, 10)]  # post, rail butted into it, loose bar
    c1530 = {"profile": "1530", "miters": 0}
    c1515 = {"profile": "1515", "miters": 0}
    j = tslot.measure_joints(solids, [(0, c1530), (1, c1515), (2, c1515)])
    assert j[1] == {"joined_ends": 1, "anchors": 1}  # one end on the post, the other end free
    assert j[0]["joined_ends"] == 0 and j[2]["joined_ends"] == 0
    solids[0] = box(1.5, 0, 30, 1.5, 3, 10)  # a 1530 standing on the rail's end region: two anchors on that end
    j = tslot.measure_joints(solids, [(0, c1530), (1, c1515)])
    assert j[0] == {"joined_ends": 1, "anchors": 2}


def test_tslot_panels_by_name():
    from app import tslot

    assert tslot.panel_for("Rear_right_door_infill", 0.236) == "PANEL-PC-250"
    assert tslot.panel_for("Front acrylic panel", 0.12) == "PANEL-ACR-125"
    assert tslot.panel_for("Side_infill_ACM", 0.118, "PC") == "PANEL-ACM-118"
    assert tslot.panel_for("Side_plate", 0.236) is None and tslot.panel_for("Aluminum infill panel", 0.125) is None
