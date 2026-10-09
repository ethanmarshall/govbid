import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from app import analysis
from app.connectors import sam_gov, tabular_import
from app.eligibility import evaluate

FIX = Path(__file__).parent / "fixtures"


def profile(**kw):
    base = dict(
        sam_status="active",
        naics_codes=["541519", "423490"],
        certifications={"SB": "certified", "SDVOSB": "pending", "VOSB": "none"},
        small_under_naics={"541519": True, "423490": True},
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------- eligibility
def test_sdvosb_pending_is_eligible_once_certified():
    r = evaluate("SDVOSBC", "541519", profile())
    assert r.status == "eligible_once_certified"
    assert "pending" in r.reason


def test_sdvosb_certified_is_eligible_now():
    r = evaluate("SDVOSBS", "541519", profile(certifications={"SB": "certified", "SDVOSB": "certified"}))
    assert r.status == "eligible_now"


def test_certified_sdvosb_qualifies_for_va_vosb_set_aside():
    r = evaluate("VSA", "541519", profile(certifications={"SDVOSB": "certified"}))
    assert r.status == "eligible_now"


def test_small_business_set_aside_and_unrestricted():
    assert evaluate("SBA", "423490", profile()).status == "eligible_now"
    assert evaluate("", "999999", profile()).status == "eligible_now"
    assert evaluate("8A", "541519", profile()).status == "not_eligible"


def test_not_small_under_naics_blocks_set_aside():
    r = evaluate("SBA", "423490", profile(small_under_naics={"423490": False}))
    assert r.status == "not_eligible"


def test_warnings_for_sam_and_naics():
    r = evaluate("", "111111", profile(sam_status="pending"))
    assert any("SAM" in w for w in r.warnings)
    assert r.naics_match is False


# ---------------------------------------------------------------- SAM connector
def _mock_client():
    payload = json.loads((FIX / "sam_response.json").read_text())
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        offset = int(request.url.params.get("offset", "0"))
        if offset > 0:
            return httpx.Response(200, json={"totalRecords": 3, "opportunitiesData": []})
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_sam_search_and_normalize():
    client, calls = _mock_client()
    raw, used = sam_gov.search(days_back=7, naics="541519", client=client, api_key="k")
    assert used == 1 and len(raw) == 3
    params = calls[0].url.params
    assert params["ncode"] == "541519" and params["limit"] == "1000"
    assert params.get_list("ptype") == ["o", "k", "p", "r"]
    n = sam_gov.normalize(raw[0])
    assert n["set_aside_code"] == "SDVOSBC"
    assert n["pop_state"] == "NY"
    assert n["contacts"][0]["email"] == "jane.smith@va.gov"
    assert n["url"] == "https://sam.gov/opp/abc123/view"
    assert n["agency"].startswith("VETERANS AFFAIRS")


def test_sam_requires_key():
    import app.connectors.sam_gov as mod

    old = mod.SAM_API_KEY
    mod.SAM_API_KEY = ""
    try:
        sam_gov.search()
        assert False, "should raise"
    except sam_gov.SamApiError:
        pass
    finally:
        mod.SAM_API_KEY = old


# ---------------------------------------------------------------- imports
def test_csv_import_and_set_aside_text(tmp_path):
    f = tmp_path / "forecast.csv"
    f.write_text(
        "Title,Agency,NAICS Code,Small Business Set Aside,Estimated Value,Anticipated Solicitation Date\n"
        "Cloud migration support,Dept of Labor,541512,Service-Disabled Veteran-Owned Small Business,$1M - $5M,01/15/2027\n"
        "Office furniture,GSA,337214,Full and Open,$250K,02/01/2027\n"
    )
    recs = tabular_import.parse_table(f, "forecast")
    assert len(recs) == 2
    assert recs[0]["set_aside_code"] == "SDVOSBC"
    assert recs[0]["naics"] == "541512"
    assert recs[0]["estimated_value"] == 5_000_000
    assert recs[1]["set_aside_code"] == ""


def test_dibbs_index_parse_and_watchlist(tmp_path):
    f = tmp_path / "in261008.txt"
    f.write_text(
        "SPE7M126T1234  5340013965472 CLAMP,LOOP          0025 EA 10/08/2026 10/20/2026\n"
        "SPE4A626U5678  2915-01-234-5678 NOZZLE,FUEL INJECTION 0004 EA 10/08/2026 10/22/2026\n"
        "garbage line without a solicitation\n"
    )
    recs = tabular_import.parse_dibbs_index(f)
    assert len(recs) == 2
    assert recs[0]["nsn"] == "5340-01-396-5472"
    assert recs[0]["response_deadline"] == "10/20/2026"
    assert "CLAMP" in recs[0]["title"]
    assert recs[0]["url"].endswith("sn=SPE7M126T1234")
    kept = tabular_import.filter_watchlist(recs, ["2915"])
    assert [r["nsn"] for r in kept] == ["2915-01-234-5678"]


# ---------------------------------------------------------------- analysis
SOLICITATION = """
SECTION L - INSTRUCTIONS TO OFFERORS
L.1 The offeror shall submit the technical volume not to exceed 10 pages in 12-point font.
L.2 Quotes are due no later than October 30, 2026 at 2:00 PM EST.
L.3 Offerors must be registered in SAM at the time of submission.
SECTION M - EVALUATION
Award will be made on a Lowest Price Technically Acceptable basis.
Factor 1: Technical Approach
Factor 2: Price
FAR 52.219-14 Limitations on Subcontracting applies. FAR 52.219-27 Notice of SDVOSB Set-Aside.
DFARS 252.204-7021 CMMC Level 1 is required.
"""


def test_heuristic_analysis_extracts_requirements(tmp_path):
    method, res = analysis.analyze({"title": "Test"}, [("rfq.txt", SOLICITATION)])
    assert method == "heuristic"
    b = res["breakdown"]
    assert "Lowest Price Technically Acceptable" in b["evaluation_method"]
    clauses = {c["clause"] for c in b["key_clauses"]}
    assert {"52.219-14", "52.219-27", "252.204-7021"} <= clauses
    assert any("10 pages" in p for p in b["page_limits"])
    assert any("October 30, 2026" in d for d in b["deadlines"])
    assert any("CMMC" in r for r in b["red_flags"])
    reqs = [r["requirement"] for r in res["compliance_matrix"]]
    assert any("technical volume" in r for r in reqs)
    assert any("registered in SAM" in r for r in reqs)
    out = analysis.matrix_to_xlsx({"title": "T"}, res, tmp_path / "m.xlsx")
    assert out.exists() and out.stat().st_size > 0


def test_extract_text_docx(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph("The contractor shall deliver monthly reports.")
    p = tmp_path / "pws.docx"
    d.save(p)
    assert "monthly reports" in analysis.extract_text(p)


def test_claude_path_parses_json_and_merges_clauses(monkeypatch):
    import sys
    import types

    reply = {
        "summary": "Help desk for VA.",
        "breakdown": {"evaluation_method": "LPTA", "key_clauses": [{"clause": "52.219-27", "note": "SDVOSB only"}], "red_flags": []},
        "compliance_matrix": [{"requirement": "Staff the help desk 8-5", "reference": "PWS 3.1"}],
    }

    class FakeMessages:
        def create(self, **kw):
            assert kw["system"].startswith("You are a federal contracting analyst")
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="```json\n" + json.dumps(reply) + "\n```")])

    fake_mod = types.SimpleNamespace(Anthropic=lambda api_key: types.SimpleNamespace(messages=FakeMessages()))
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setattr(analysis, "ANTHROPIC_API_KEY", "sk-test")
    method, res = analysis.analyze({"title": "Help desk"}, [("rfq.txt", SOLICITATION)])
    assert method == "claude"
    clauses = [c["clause"] for c in res["breakdown"]["key_clauses"]]
    assert clauses[0] == "52.219-27" and "52.219-14" in clauses
    assert res["compliance_matrix"][0]["id"] == 1 and res["compliance_matrix"][0]["status"] == "open"


def test_cited_standards_extraction():
    text = """Drawings shall conform to ASME Y14.100 and MIL-STD-100 with GD&T per ASME Y14.5.
    Mark items per MIL-STD-130N. Deliver drawings per DI-SESS-81000E and test reports per DI-NDTI-80809B.
    Soldering per J-STD-001 and IPC-A-610. Quality system: ISO 9001:2015 or AS9100D.
    Protect CUI per NIST SP 800-171. Package per MIL-STD-2073-1. MIL-STD-130N applies again."""
    found = {s["standard"]: s for s in analysis.cited_standards(text)}
    for k in ["ASME Y14.100", "ASME Y14.5", "MIL-STD-100", "MIL-STD-130N", "DI-SESS-81000E", "DI-NDTI-80809B",
              "J-STD-001", "IPC-A-610", "ISO 9001:2015", "AS9100D", "NIST SP 800-171", "MIL-STD-2073-1"]:
        assert k in found, (k, list(found))
    assert found["MIL-STD-130N"]["count"] == 2
    assert found["MIL-STD-130N"]["free"] is True and found["ASME Y14.5"]["free"] is False
    method, res = analysis.analyze({"title": "T"}, [("sow.txt", text)])
    assert res["breakdown"]["cited_standards"][0]["standard"] == "MIL-STD-130N"


def test_requirement_paragraph_numbers_kept_whole():
    text = """SECTION L - INSTRUCTIONS
L.1 The offeror shall submit a technical volume not to exceed 10 pages.
SECTION C - PWS
C.3.1 The contractor shall staff the help desk 8am to 5pm.
C.3.2 The contractor shall resolve Tier 1 tickets within 4.5 business hours.
3.4.2 Reports shall be delivered monthly to the COR.
"""
    _, res = analysis.analyze({"title": "T"}, [("rfq.txt", text)])
    rows = {r["requirement"]: r["reference"] for r in res["compliance_matrix"]}
    assert rows["The contractor shall staff the help desk 8am to 5pm."] == "C.3.1"
    assert rows["The contractor shall resolve Tier 1 tickets within 4.5 business hours."] == "C.3.2"
    assert rows["The offeror shall submit a technical volume not to exceed 10 pages."] == "L.1"
    assert rows["Reports shall be delivered monthly to the COR."] == "Sec. C 3.4.2"
