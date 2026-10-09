import copy
import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from app import pricing
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]


def spec(**kw):
    s = copy.deepcopy(pricing.EXAMPLE_SPEC)
    s.update(kw)
    return s


# ---------------------------------------------------------------- engine
def test_unit_price_falls_with_quantity_and_markup_applied():
    r = pricing.estimate(spec())
    breaks = r["price_breaks"]
    assert [b["quantity"] for b in breaks] == [10, 50, 100]
    assert breaks[0]["unit_price"] > breaks[1]["unit_price"] > breaks[2]["unit_price"]
    for b in breaks:
        assert b["unit_price"] == pytest.approx(b["unit_cost"] * 1.10 * 1.15, abs=0.02)
    lot_items = [l["item"] for l in r["per_lot_lines"]]
    assert any("programming" in i for i in lot_items) and any("anodize" in i for i in lot_items)


def test_reference_price_flags_unwinnable_quantities():
    r = pricing.estimate(spec(reference_unit_price=20.0))
    assert all("cannot match" in b["reference_note"] for b in r["price_breaks"])
    assert any("every quantity" in w for w in r["warnings"])


def test_material_cost_from_stock_volume():
    s = spec(operations=[], finishes=[], quantities=[1])
    r = pricing.estimate(s)
    vol = 4 * 3 * 0.5
    expected = vol * 0.0975 * 1.15 * 4.50
    assert r["stock_volume_in3"] == pytest.approx(vol)
    assert r["per_part_lines"][0]["cost"] == pytest.approx(expected, abs=0.01)


def test_sheet_metal_and_weld_part():
    s = {
        "name": "Electrical enclosure",
        "quantities": [5, 25],
        "material": "304 stainless",
        "stock": {"shape": "sheet", "dims": {"length": 24, "width": 18, "thickness": 0.0625}},
        "operations": [
            {"type": "laser_cut", "cut_length_in": 180, "pierces": 12},
            {"type": "press_brake", "bends": 4},
            {"type": "weld", "process": "tig", "weld_length_in": 24, "joints": 4},
            {"type": "hardware_insert", "count": 8, "unit_cost": 0.35},
        ],
        "finishes": [{"type": "passivate (stainless)"}],
        "packaging": {"level": "commercial"},
        "approved_source_required": False,
    }
    r = pricing.estimate(s)
    cats = {l["category"] for l in r["per_part_lines"]}
    assert {"cutting", "forming", "welding", "hardware"} <= cats
    weld = next(l for l in r["per_part_lines"] if l["category"] == "welding")
    assert weld["hours"] == pytest.approx((24 / 1.5 + 4 * 1.0 + 0.5) / 60, abs=0.001)
    assert r["price_breaks"][1]["unit_price"] < r["price_breaks"][0]["unit_price"]
    assert not any("approved sources" in w for w in r["warnings"])


def test_finish_lot_minimum_applies_at_small_qty():
    s = spec(quantities=[2], operations=[], finishes=[{"type": "powder coat"}], reference_unit_price=None)
    small = pricing.estimate(s)["price_breaks"][0]["total_cost"]
    s2 = spec(quantities=[2], operations=[], finishes=[], reference_unit_price=None)
    base = pricing.estimate(s2)["price_breaks"][0]["total_cost"]
    assert small - base == pytest.approx(175.0, abs=0.01)  # lot minimum, not 2 x $8


@pytest.mark.parametrize("bad, msg", [
    ({"material": "unobtainium"}, "Unknown material"),
    ({"operations": [{"type": "plasma"}]}, "not one of"),
    ({"stock": {"shape": "plate", "dims": {}}}, "Stock dimensions"),
    ({"quantities": ["x"]}, "positive integers"),
])
def test_spec_errors(bad, msg):
    with pytest.raises(pricing.SpecError, match=msg):
        pricing.estimate(spec(**bad))


# ---------------------------------------------------------------- REST
def test_rest_config_estimate_and_quotes():
    with TestClient(app) as c:
        meta = c.get("/api/pricing/meta").json()
        assert "cnc_mill" in meta["operation_types"] and "6061-T6 aluminum" in meta["materials"]
        before = c.post("/api/pricing/estimate", json=spec()).json()["price_breaks"][0]["unit_price"]
        cfg = c.put("/api/pricing/config", json={"changes": {"rates": {"cnc_mill": 150}}}).json()["config"]
        assert cfg["rates"]["cnc_mill"] == 150 and cfg["rates"]["cnc_lathe"] == 85.0
        after = c.post("/api/pricing/estimate", json=spec()).json()["price_breaks"][0]["unit_price"]
        assert after > before
        assert c.post("/api/pricing/config/reset").json()["config"]["rates"]["cnc_mill"] == 95.0
        assert c.post("/api/pricing/estimate", json=spec(material="nope")).status_code == 400

        oid = c.post("/api/opportunities", json={"title": "Bracket, mounting", "solicitation_number": "SPE7M5-26-T-0001"}).json()["id"]
        q = c.post("/api/pricing/quotes", json={"spec": spec(), "opportunity_id": oid, "quoted_quantity": 50}).json()
        assert q["quoted_unit_price"] == q["price_breaks"][1]["unit_price"]
        assert q["solicitation_number"] == "SPE7M5-26-T-0001"
        q2 = c.put(f"/api/pricing/quotes/{q['id']}", json={"spec": spec(), "opportunity_id": oid, "status": "ready", "quoted_quantity": 50, "quoted_unit_price": 58.0}).json()
        assert q2["status"] == "ready" and q2["quoted_unit_price"] == 58.0
        assert c.get("/api/pricing/quotes", params={"opportunity_id": oid}).json()[0]["id"] == q["id"]
        c.delete(f"/api/opportunities/{oid}")
        assert c.get(f"/api/pricing/quotes/{q['id']}").json()["opportunity_id"] is None
        assert c.delete(f"/api/pricing/quotes/{q['id']}").json()["ok"]


# ---------------------------------------------------------------- MCP (in process)
def test_mcp_tools_registered_and_callable():
    from app import mcp_server

    async def run():
        tools = {t.name: t for t in await mcp_server.mcp.list_tools()}
        expected = {"pricing_reference", "get_shop_rates", "update_shop_rates", "estimate_part", "save_part_quote",
                    "list_part_quotes", "get_part_quote", "update_part_quote", "search_opportunities", "get_opportunity"}
        assert expected <= set(tools)
        assert tools["estimate_part"].annotations.read_only_hint is True
        assert tools["update_shop_rates"].annotations.destructive_hint is True
        res = await mcp_server.mcp.call_tool("estimate_part", {"spec": spec()})
        payload = json.loads(res.content[0].text)
        assert payload["price_breaks"][0]["quantity"] == 10
        bad = json.loads((await mcp_server.mcp.call_tool("estimate_part", {"spec": spec(material="x")})).content[0].text)
        assert "Unknown material" in bad["error"]

    anyio.run(run)


# ---------------------------------------------------------------- MCP end to end over stdio
def test_mcp_stdio_end_to_end(tmp_path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp_path}/mcp.db", UPLOAD_DIR=str(tmp_path / "up"), SAM_API_KEY="", ANTHROPIC_API_KEY="")
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"], cwd=str(BACKEND), env=env)

    async def run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                init = await s.initialize()
                assert init.server_info.name == "govbid-pro-pricing"
                names = {t.name for t in (await s.list_tools()).tools}
                assert "save_part_quote" in names and "search_opportunities" in names
                ref = json.loads((await s.call_tool("pricing_reference", {})).content[0].text)
                saved = json.loads((await s.call_tool("save_part_quote", {"spec": ref["example_spec"], "quoted_quantity": 100, "notes": "agent test"})).content[0].text)
                assert saved["created_by"] == "agent" and saved["quoted_quantity"] == 100
                listed = json.loads((await s.call_tool("list_part_quotes", {})).content[0].text)
                assert listed["quotes"][0]["id"] == saved["id"]
                upd = json.loads((await s.call_tool("update_part_quote", {"quote_id": saved["id"], "status": "ready"})).content[0].text)
                assert upd["status"] == "ready"
                search = json.loads((await s.call_tool("search_opportunities", {"keywords": ["bracket"]})).content[0].text)
                assert search["total_matches"] == 0
                prompts = await s.list_prompts()
                assert prompts.prompts[0].name == "quote_rfq_part"

    anyio.run(run)


def test_rate_validation_rejects_bad_values():
    with TestClient(app) as c:
        assert c.put("/api/pricing/config", json={"changes": {"rates": {"cnc_mill": ""}}}).status_code == 400
        assert c.put("/api/pricing/config", json={"changes": {"rates": {"cnc_mill": -5}}}).status_code == 400
        assert c.put("/api/pricing/config", json={"changes": {"materials": {"steel X": {"price_per_lb": 2}}}}).status_code == 400
        assert c.get("/api/pricing/config").json()["config"]["rates"]["cnc_mill"] == 95.0
