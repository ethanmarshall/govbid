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
    assert r["mesh"]["triangles"] > 10 and "<svg" in r["drawing"] and r["summary"][0]["label"] == "Part"


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
