"""GovBid Pro MCP server: lets AI agents find part RFQs, estimate custom-part costs and save quotes.

Run it:
  python -m app.mcp_server                    stdio (Claude Desktop, Claude Code, most MCP clients)
  python -m app.mcp_server --http --port 8765 streamable HTTP at http://127.0.0.1:8765/mcp

It reads and writes the same database as the website, so quotes an agent saves show up on the
Part Quotes page. Nothing here submits a bid to the government: a person reviews and submits.
"""
from __future__ import annotations

import argparse
import contextlib
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

import base64
from pathlib import Path

from . import cad, cad_quote, pricing, quotes
from .db import SessionLocal, init_db

INSTRUCTIONS = """GovBid Pro part pricing. Use these tools to find government RFQs for parts this shop could
CNC machine, cut, form or weld, and to build should-cost quotes.

Fastest path when you have a STEP file: analyze_step_file, then quote_step_file with material,
finishes and quantities, then save_part_quote with the returned spec.
For a 3D printed part with threaded holes: analyze_step_file, convert_holes_for_inserts (rebuilds the
holes for brass heat-set inserts as a new file), then quote_step_file(process="3d_print") on the new file_id.
With only a PDF drawing: quote_from_drawing, check its assumptions and envelope, then save_part_quote.
For an electromechanical assembly (enclosure with boards, switches, wiring and peripherals): read_pcb_files for each
board, then quote_box_build, then save_part_quote with the spec plus "kind": "box_build".

Workflow without a model:
1. pricing_reference: learn the spec format, materials, finishes and operation types.
2. search_opportunities / get_opportunity: find an RFQ and read its NSN, quantity, drawing and packaging notes.
3. estimate_part: describe the part (material, stock size, operations, finishes, inspection, packaging,
   quantities, and reference_unit_price if a past award price is known). Read the warnings.
4. save_part_quote: store the estimate, linked to the opportunity. A person reviews it before any bid.

Rules:
- Estimates depend entirely on the shop rates (get_shop_rates). Say so when reporting a price.
- Never invent dimensions or features. If the drawing is not available, say what is missing and estimate
  only with values the user or the RFQ gave, stating each assumption.
- Most NSN parts are limited to approved sources. Flag when the RFQ restricts sources.
- Do not change shop rates unless the user asks."""

mcp = MCPServer(name="govbid-pro-pricing", title="GovBid Pro part pricing", instructions=INSTRUCTIONS, version="1.0.0")

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
RATES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


@contextlib.contextmanager
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _err(exc: Exception) -> dict:
    return {"error": str(exc)}


@mcp.tool(annotations=READ)
def pricing_reference() -> dict[str, Any]:
    """Describe the part spec format: operation types and their params, stock shapes, known materials
    (with density and price per lb), finishes, tolerance classes, packaging levels, and a complete example spec."""
    with session() as db:
        cfg = quotes.get_config(db)
    return {
        "operation_types": pricing.OPERATION_TYPES,
        "stock_shapes": pricing.STOCK_SHAPES,
        "materials": cfg["materials"],
        "finishes": cfg["finishes"],
        "3d_printing": {"technologies": cfg["additive"]["technologies"], "materials": cfg["additive"]["materials"],
                        "finishes": cfg["additive"]["finishes"],
                        "note": "Use an additive operation and an additive material; no stock needed."},
        "tolerances": cfg["tolerance_multiplier"],
        "packaging_levels": cfg["packaging"],
        "spec_fields": {
            "name, part_number, nsn, drawing, revision": "identification (optional)",
            "quantities": "list of quantities to price, e.g. [10, 50, 100]",
            "material": "one of the materials keys",
            "stock": "{shape, dims} raw stock for ONE part, inches",
            "tolerance": "standard | tight | precision (default for all operations)",
            "operations": "list of {type, ...params}",
            "finishes": "list of {type, per_part?, lot_min?}",
            "inspection": "{first_article: bool, minutes_per_part?, certificate_of_conformance?: bool}",
            "packaging": "{level: commercial | mil_std_2073}",
            "freight_per_lot": "USD, optional",
            "material_cost_per_part": "USD, overrides the weight-based material cost",
            "material_certs_required": "bool",
            "reference_unit_price": "past award or target unit price to compare against",
            "approved_source_required": "bool, default true",
            "ga_rate, profit_rate": "override markups for this quote only",
        },
        "example_spec": pricing.EXAMPLE_SPEC,
    }


@mcp.tool(annotations=READ)
def get_shop_rates() -> dict[str, Any]:
    """Return the effective shop-rate config (hourly rates, setup and programming hours, material prices,
    finish prices, markups) and which values the user has customized."""
    with session() as db:
        return {"config": quotes.get_config(db), "customized": quotes.get_overrides(db)}


@mcp.tool(annotations=RATES)
def update_shop_rates(changes: dict[str, Any]) -> dict[str, Any]:
    """Change shop rates. Only call when the user asks. `changes` is a partial config merged into the saved
    rates, e.g. {"rates": {"cnc_mill": 110}, "materials": {"6061-T6 aluminum": {"price_per_lb": 5.1}}, "profit_rate": 0.12}.
    New materials or finishes need every field shown by pricing_reference."""
    with session() as db:
        try:
            return {"config": quotes.update_config(db, changes)}
        except (pricing.SpecError, KeyError, TypeError) as exc:
            return _err(exc)


@mcp.tool(annotations=READ)
def estimate_part(spec: dict[str, Any]) -> dict[str, Any]:
    """Estimate cost and price for a custom part without saving it. Returns per-part and per-lot cost lines
    (with hours and rates), price breaks for each quantity, lead time, margin, comparison against
    reference_unit_price, assumptions and warnings. Call pricing_reference first for the spec format."""
    with session() as db:
        try:
            return quotes.run_estimate(db, spec)
        except pricing.SpecError as exc:
            return _err(exc)


@mcp.tool(annotations=WRITE)
def save_part_quote(
    spec: dict[str, Any],
    opportunity_id: int | None = None,
    status: str = "draft",
    quoted_quantity: int | None = None,
    quoted_unit_price: float | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Estimate and save a part quote so it appears on the Part Quotes page. Link it to an opportunity with
    opportunity_id. status: draft | ready | submitted | won | lost | no_bid. If quoted_unit_price is omitted and
    quoted_quantity matches a price break, that break's unit price is used. Put assumptions in notes."""
    with session() as db:
        try:
            return quotes.save_quote(db, spec, opportunity_id=opportunity_id, status=status, quoted_quantity=quoted_quantity,
                                     quoted_unit_price=quoted_unit_price, notes=notes, created_by="agent")
        except pricing.SpecError as exc:
            return _err(exc)


@mcp.tool(annotations=READ)
def list_part_quotes(status: str = "", opportunity_id: int | None = None, query: str = "", limit: int = 25) -> dict[str, Any]:
    """List saved part quotes, newest first. Filter by status, linked opportunity, or text in name/NSN/part number."""
    with session() as db:
        rows = quotes.list_quotes(db, status=status, opportunity_id=opportunity_id, q=query, limit=min(limit, 200))
    return {"count": len(rows), "quotes": rows}


@mcp.tool(annotations=READ)
def get_part_quote(quote_id: int) -> dict[str, Any]:
    """Return one saved quote with its full spec and cost breakdown."""
    with session() as db:
        try:
            return quotes.get_quote(db, quote_id)
        except pricing.SpecError as exc:
            return _err(exc)


@mcp.tool(annotations=WRITE)
def update_part_quote(
    quote_id: int,
    spec: dict[str, Any] | None = None,
    status: str | None = None,
    quoted_quantity: int | None = None,
    quoted_unit_price: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Revise a saved quote: a new spec re-runs the estimate; status, quoted quantity/price and notes can change alone."""
    with session() as db:
        try:
            cur = quotes.get_quote(db, quote_id)
            return quotes.save_quote(
                db, spec or cur["spec"], quote_id=quote_id, opportunity_id=cur["opportunity_id"],
                status=status or cur["status"],
                quoted_quantity=quoted_quantity if quoted_quantity is not None else cur["quoted_quantity"],
                quoted_unit_price=quoted_unit_price, notes=notes if notes is not None else cur["notes"],
            )
        except pricing.SpecError as exc:
            return _err(exc)


@mcp.tool(annotations=READ)
def search_opportunities(
    query: str = "",
    keywords: list[str] | None = None,
    naics: list[str] | None = None,
    fsc_prefixes: list[str] | None = None,
    set_aside: str = "",
    source: str = "",
    eligibility: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Search opportunities already in GovBid Pro (synced from SAM.gov or imported from DIBBS).
    keywords match any word in title/description/agency; fsc_prefixes match the start of the NSN or PSC
    (e.g. ["5340", "3040"] for hardware and mechanical parts); eligibility: eligible_now,eligible_once_certified.
    Open opportunities only, soonest deadline first."""
    from .main import list_opportunities  # imported late: main builds the web app

    with session() as db:
        res = list_opportunities(
            q=query, kw=",".join(keywords or []), source=source, set_aside=set_aside, naics=",".join(naics or []),
            state="", eligibility=eligibility, my_naics_only=False, hide_expired=True, notice_type="", sort="deadline",
            page=1, limit=200, db=db,
        )
    rows = res["results"]
    if fsc_prefixes:
        pre = [p.replace("-", "") for p in fsc_prefixes]
        rows = [r for r in rows if any((r.get("nsn") or "").replace("-", "").startswith(p) or (r.get("psc") or "").startswith(p) for p in pre)]
    keep = ("id", "source", "solicitation_number", "title", "agency", "notice_type", "set_aside_code", "naics", "psc", "nsn",
            "quantity", "response_deadline", "days_left", "url")
    out = [{k: r.get(k) for k in keep} | {"eligibility": r["eligibility"]["status"]} for r in rows[: max(1, min(limit, 100))]]
    return {"total_matches": len(rows), "results": out}


@mcp.tool(annotations=READ)
def get_opportunity(opportunity_id: int) -> dict[str, Any]:
    """Full details of one opportunity: description, NSN and quantity, set-aside and eligibility, contacts,
    attachments, uploaded documents, requirements analysis summary, and any part quotes already linked to it."""
    from .main import opportunity_detail

    with session() as db:
        try:
            d = opportunity_detail(opportunity_id, db)
        except Exception as exc:  # HTTPException for a missing id
            return _err(getattr(exc, "detail", exc))
        d["part_quotes"] = quotes.list_quotes(db, opportunity_id=opportunity_id)
    desc = d.get("description") or ""
    d["description"] = desc[:6000] + ("... [truncated]" if len(desc) > 6000 else "")
    if d.get("analysis"):
        a = d["analysis"]
        d["analysis"] = {"summary": a.get("summary"), "breakdown": a.get("breakdown"), "requirements_count": len(a.get("compliance_matrix") or [])}
    return d


@mcp.tool(annotations=WRITE)
def analyze_step_file(file_path: str = "", content_base64: str = "", filename: str = "part.step") -> dict[str, Any]:
    """Load a STEP (.step/.stp) model and measure it: bounding box, volume, surface area, holes with diameters,
    turned diameters, sheet-metal thickness, bends and cut length, and the suggested process.
    Give either file_path (a file on this computer) or content_base64. Returns a file_id for quote_step_file."""
    try:
        if file_path:
            p = Path(file_path).expanduser()
            if not p.is_file():
                return _err(f"No file at {p}")
            data, filename = p.read_bytes(), p.name
        elif content_base64:
            data = base64.b64decode(content_base64)
        else:
            return _err("Give file_path or content_base64")
        d = cad_quote.store_upload(data, filename)
    except (cad.CadError, ValueError) as exc:
        return _err(exc)
    return {"file_id": d["file_id"], "filename": d["filename"], "geometry": d["geometry"]}


@mcp.tool(annotations=READ)
def quote_step_file(
    file_id: str,
    material: str,
    quantities: list[int] | None = None,
    process: str = "auto",
    finishes: list[str] | None = None,
    tolerance: str = "standard",
    threaded_holes: int = 0,
    inserts: int = 0,
    weld_length_in: float = 0,
    thickness: float | None = None,
    infill: float | None = None,
    support: bool = True,
    first_article: bool = False,
    material_certs: bool = False,
    packaging: str = "commercial",
    reference_unit_price: float | None = None,
    name: str = "",
    part_number: str = "",
    nsn: str = "",
) -> dict[str, Any]:
    """Instant quote for an analyzed STEP file, like an online quoting shop. process: auto | cnc_mill | cnc_lathe |
    sheet_metal | 3d_print. material and finishes must be names from pricing_reference (3D printing uses the
    additive materials and finishes; the material picks FDM, SLA, SLS or MJF). thickness (inches) overrides the
    measured sheet gauge. infill (0.1 to 1) applies to FDM; support=False for parts that print without supports. Returns price breaks, cost lines, warnings, and the spec to pass to save_part_quote."""
    opts = {k: v for k, v in dict(
        material=material, quantities=quantities or [1], process=process, finishes=finishes or [], tolerance=tolerance,
        threaded_holes=threaded_holes, inserts=inserts, weld_length_in=weld_length_in, thickness=thickness,
        **({"infill": infill, "support": support} if process == "3d_print" else {}),
        first_article=first_article, material_certs=material_certs, packaging=packaging,
        reference_unit_price=reference_unit_price, name=name, part_number=part_number, nsn=nsn,
    ).items() if v not in (None, "")}
    with session() as db:
        try:
            r = cad_quote.quote(file_id, opts, quotes.get_overrides(db))
        except (cad.CadError, pricing.SpecError) as exc:
            return _err(exc)
    return {"process": r["process"], "price_breaks": r["estimate"]["price_breaks"], "warnings": r["estimate"]["warnings"],
            "assumptions": r["estimate"]["assumptions"], "per_part_lines": r["estimate"]["per_part_lines"],
            "per_lot_lines": r["estimate"]["per_lot_lines"], "spec": r["spec"]}


@mcp.tool(annotations=READ)
def read_drawing_pdf(file_path: str) -> dict[str, Any]:
    """Read a PDF engineering drawing on this computer: part number, revision, CAGE, material, finish, general
    tolerance, thread callouts, cited specs, distribution statement and export-control warnings. Returns
    quote_options you can pass straight into quote_step_file. Scanned drawings without a text layer return
    text_found=false; enter those fields by hand."""
    from . import drawing
    pth = Path(file_path).expanduser()
    if not pth.is_file():
        return _err(f"No file at {pth}")
    try:
        r = drawing.read_drawing(pth)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    with session() as db:
        cfg = quotes.get_config(db)
    r["quote_options"] = drawing.quote_options(r, list(cfg["materials"]) + list(cfg["additive"]["materials"]),
                                               list(cfg["finishes"]) + list(cfg["additive"]["finishes"]))
    return r


@mcp.tool(annotations=WRITE)
def convert_holes_for_inserts(file_id: str, selections: list[dict[str, Any]] | None = None, auto: bool = True) -> dict[str, Any]:
    """Rebuild threaded holes in an analyzed STEP model as tapered holes for brass heat-set inserts (for 3D
    printing) and save the result as a new STEP file. selections: [{"hole_id": "h1", "thread": "M3",
    "from_end": "auto"}]; hole ids and guessed threads come from the holes list this tool returns on error, or
    leave selections empty with auto=true to convert every hole whose diameter matches a tap drill or nominal
    size (M2 to M8, #2-56 to 3/8-16). Returns the new file_id (quote it with quote_step_file process="3d_print"),
    the inserts used, holes skipped and warnings. The original file is unchanged."""
    from . import inserts
    with session() as db:
        cfg = quotes.get_config(db)
    if not selections and not auto:
        return _err("Give selections, or auto=true to convert every hole that matches a thread")
    try:
        r = inserts.convert_file(file_id, selections or None, not selections, cfg)
    except cad.CadError as exc:
        out = _err(exc)
        try:
            out["holes"] = [{k: h[k] for k in ("id", "diameter_mm", "depth_mm", "through", "open_end_name")} | {"guess": (h.get("guess") or {}).get("thread")}
                            for h in inserts.holes_for_file(file_id, cfg)["holes"]]
        except cad.CadError:
            pass
        return out
    return {"file_id": r["file_id"], "filename": r["filename"], "derived_from": r["derived_from"], "summary": r["summary"],
            "inserts": r["inserts"], "skipped": r["skipped"], "warnings": r["warnings"], "geometry": r["geometry"]}


@mcp.tool(annotations=READ)
def dfm_check(file_id: str, process: str = "auto", material: str = "") -> dict[str, Any]:
    """Manufacturability review of an analyzed STEP file for a process: auto | cnc_mill | cnc_lathe | sheet_metal |
    3d_print. Finds thin walls, deep or tiny or non-standard holes, sharp internal corners, deep pockets with small
    corner radii, extra setups and undercuts (milling), and tight bends, holes near bends and short flanges (sheet
    metal). material picks the wall limit (metal or plastic; for 3d_print the FDM or SLA limit). Each finding has
    severity (info | warn | cost), detail, suggestion, cost_effect and location (points in inches). Also returns
    note, a plain-text summary to paste into a customer quote. Rules of thumb only: say so when reporting."""
    from . import dfm
    with session() as db:
        cfg = quotes.get_config(db)
    try:
        r = dfm.check_file(file_id, process, material, cfg)
    except cad.CadError as exc:
        return _err(exc)
    r.pop("rules", None)
    return r


@mcp.tool(annotations=WRITE)
def split_assembly(file_id: str) -> dict[str, Any]:
    """Split a STEP file that holds several solids (an assembly or weldment) into one stored STEP file per distinct
    body. Identical bodies are grouped with qty per assembly. Returns groups [{file_id, name, qty, suggested_process,
    bounding_box, volume}], the joints where bodies touch, and weld_estimate_in (two fillet welds along each contact,
    an estimate to confirm against the weld symbols). Quote each body with quote_step_file, or price the whole
    assembly over the REST endpoint POST /api/cad/{file_id}/assembly-quote."""
    from . import assembly
    try:
        return assembly.split(file_id)
    except cad.CadError as exc:
        return _err(exc)


@mcp.tool(annotations=READ)
def read_pcb_files(file_paths: list[str]) -> dict[str, Any]:
    """Read PCB fab and assembly files for one board: Gerbers (or a zip of fab outputs), Excellon drill, pick-and-place
    (KiCad .pos, Altium/Eagle CSV) and a BOM (CSV/XLSX). Returns board {layers, width_in, height_in, smt_placements,
    sides, smt_unique, fine_pitch, bga, tht_parts, tht_joints}, bom_lines [{ref, mpn, manufacturer, description, qty, tht}],
    evidence (where each value came from) and warnings. Use the board fields and bom_lines as a pcbs[] entry in
    quote_box_build. Through-hole joints and pins are estimates from footprint names and hole sizes."""
    from . import pcb_files
    try:
        files = [(Path(p).name, Path(p).read_bytes()) for p in file_paths]
        return pcb_files.parse_files(files)
    except (OSError, pcb_files.PcbFileError) as exc:
        return _err(exc)


@mcp.tool(annotations=READ)
def quote_box_build(spec: dict[str, Any]) -> dict[str, Any]:
    """Price a custom electromechanical assembly (box build) without saving it. spec keys:
    quantities [int]; enclosure {source: catalog|custom|customer|none, type (diecast_aluminum, extruded_aluminum, sheet_steel,
    stainless_nema4x, polycarbonate, abs_plastic, rack_chassis, rugged_case), length_in, width_in, height_in, unit_price,
    finish (none|powder_coat|paint|anodize|chem_film), silkscreen_colors, mods {round_holes, rect_cutouts, connector_cutouts,
    display_windows, vent_patterns, pem_inserts, gasket, emi_gasket}, child (a linked quote, see children) when source=custom};
    pcbs [{name, qty_per, mode: estimate|buy|customer, layers, width_in, height_in, finish, ipc_class, smt_placements, smt_unique,
    fine_pitch, bga, tht_parts, tht_joints, sides, conformal, flying_probe, program_minutes, test_minutes, bom_lines or bom_cost_each,
    buy_prices [{quantity, unit_price}] and buy_nre for mode buy, outside_quotes [{vendor, country, url, quote_ref, valid_until,
    scope: assembled|bare, prices [{quantity, unit_price}], setup, shipping, duty_pct, lead_days}] compared with the estimate,
    use: estimate|lowest|q<index>}]; pcb_compare in the result shows each option's landed cost per unit at every quantity;
    lines [{type, part_number, manufacturer, description, qty, unit_price, terminations, method, mount: panel|internal}] for switches,
    connectors, indicators, displays, power supplies, fans and other parts (type is guessed from the description when blank);
    peripherals [{description, qty, unit_price, installed}]; wiring {wires, avg_length_in, mates};
    children [{name, qty_per, mode: make|buy, buy_unit_price, spec}] where spec is any saved quote spec (get_part_quote) such as a
    harness, panel, machined part, DXF part or another box build, rolled in at cost;
    labor {ipc_class, fasteners, ground_points, firmware_minutes, functional_test_minutes, hipot, ground_bond, burn_in_hours,
    ess_thermal, ess_vibration, lab_tests [mil_std_461|mil_std_810|mil_std_167|mil_s_901], work_instructions, test_procedure,
    drawing_package, test_fixture_nre, other_nre, nre_in_price}; options {first_article, packaging_level, crate, freight_per_lot}.
    Returns price_breaks, a breakdown and section totals per quantity, counts, warnings and assumptions. Every rate is a
    placeholder from the shop rates (config box_build): say so when reporting. If "incomplete" is not empty (ready is
    false) some items need a manual price or a check (lines with needs_quote and no unit_price, or a check note): do not
    report the price as a quote; list those items for the user to price by hand. Save it with save_part_quote and kind "box_build"."""
    from . import box_build
    with session() as db:
        overrides = quotes.get_overrides(db)
    try:
        return box_build.price(spec, overrides)
    except (box_build.BoxBuildError, pricing.SpecError) as exc:
        return _err(exc)


@mcp.tool(annotations=READ)
def quote_from_drawing(file_path: str, quantities: list[int] | None = None, material: str = "", process: str = "auto",
                       overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Price a part from a PDF drawing alone (no STEP model). Reads hole callouts, bends, sheet thickness, turned
    diameters and the overall envelope from the drawing text, then estimates it. process: auto | cnc_mill |
    cnc_lathe | sheet_metal | 3d_print. overrides correct what the drawing read got wrong or missed: length,
    width, height (inches), holes, tapped_holes, bends, thickness, max_diameter, finishes, tolerance, name,
    part_number, nsn, first_article, material_certs, packaging, weld_length_in, fill_ratio. Report the
    confidence and assumptions with the price: the envelope is often a low-confidence guess. When the drawing is
    an assembly (enclosure, PCB, switches, several material notes) the result has "assembly" with a
    box_build_spec read from the notes: do not report the single-part price; price box_build_spec with
    quote_box_build and tell the user what to check (assembly.assumptions).
    If review.manual_required is true the drawing was not understood well enough: do NOT report price_breaks as a
    quote. Tell the user this part needs a manual quote and list review.reasons. Only if the user gives the
    missing values (or says they checked every value) call again with those overrides (and confirmed=true)."""
    from . import drawing, drawing_quote
    pth = Path(file_path).expanduser()
    if not pth.is_file():
        return _err(f"No file at {pth}")
    try:
        read = drawing.read_drawing(pth)
        text, _ = drawing.extract_pdf_text(pth)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    read["filename"] = pth.name
    geom = drawing_quote.extract_geometry(read, text)
    o = dict(overrides or {})
    if quantities:
        o["quantities"] = quantities
    if material:
        o["material"] = material
    if process and process != "auto":
        o["process"] = process
    from . import drawing_assembly
    try:
        asm = drawing_assembly.analyze(pth, read)
    except Exception:  # noqa: BLE001
        asm = None
    with session() as db:
        try:
            r = drawing_quote.quote(read, geom, o, quotes.get_overrides(db), assembly=bool(asm))
        except pricing.SpecError as exc:
            return _err(exc)
    out = {"confidence": "low" if asm else r["confidence"], "review": r["review"], "process": r["spec"]["process"], "inputs": r["inputs"],
           "price_breaks": r["estimate"]["price_breaks"], "assumptions": r["assumptions"],
           "warnings": ([asm["message"]] if asm else []) + r["estimate"]["warnings"] + read.get("warnings", []),
           "evidence": geom["evidence"], "spec": r["spec"]}
    if asm:  # an assembly: the single-part price is not meaningful; price box_build with quote_box_build instead
        out["assembly"] = {"reasons": asm["reasons"], "box_build_spec": {k: v for k, v in asm["box_build"].items() if k not in ("evidence", "assumptions", "fabricated")},
                           "evidence": asm["box_build"]["evidence"], "assumptions": asm["box_build"]["assumptions"], "custom_parts": asm["box_build"]["fabricated"]}
    return out


@mcp.tool(annotations=READ)
def nsn_award_history(nsn: str) -> dict[str, Any]:
    """Past award prices for an NSN from imported DIBBS award files, manual entries and your own won or lost
    quotes, with the last award unit price to use as reference_unit_price."""
    from . import nsn_history
    with session() as db:
        try:
            return nsn_history.history(db, nsn)
        except ValueError as exc:
            return _err(exc)


@mcp.tool(annotations=READ)
def opportunity_bid_score(opportunity_id: int) -> dict[str, Any]:
    """Bid/no-bid score (0 to 100) for an opportunity with the reason for each factor: eligibility, fit,
    time, competition, size, price position and risks such as export-controlled drawings."""
    from . import bidding
    from .models import Opportunity
    from .services import get_profile
    with session() as db:
        o = db.get(Opportunity, opportunity_id)
        if not o:
            return _err(f"Opportunity {opportunity_id} not found")
        return bidding.bid_score(db, o, get_profile(db))


@mcp.tool(annotations=WRITE)
def add_vendor_quote(part_quote_id: int, vendor_name: str, prices: list[dict], tooling_charge: float = 0,
                     freight: float = 0, lead_days: int | None = None, quote_ref: str = "", notes: str = "") -> dict[str, Any]:
    """Record an outside shop's price on a saved part quote (make-or-buy). prices: [{"quantity": 10, "unit_price": 42.5}].
    Returns the make-versus-buy comparison per quantity and the nonmanufacturer rule notes for the linked set-aside."""
    from . import make_or_buy
    from .models import PartQuote
    from .models_crm import Organization, VendorQuote
    with session() as db:
        pq = db.get(PartQuote, part_quote_id)
        if not pq:
            return _err(f"Quote {part_quote_id} not found")
        try:
            rows = sorted(({"quantity": int(r["quantity"]), "unit_price": float(r["unit_price"])} for r in prices), key=lambda r: r["quantity"])
        except (KeyError, TypeError, ValueError):
            return _err("prices must be a list of {quantity, unit_price}")
        if not rows or not vendor_name.strip():
            return _err("Give a vendor name and at least one price")
        org = db.query(Organization).filter(Organization.name.ilike(vendor_name.strip())).first()
        db.add(VendorQuote(part_quote_id=pq.id, organization_id=org.id if org else None, vendor_name=vendor_name.strip(), prices=rows,
                           tooling_charge=tooling_charge, freight=freight, lead_days=lead_days, quote_ref=quote_ref, notes=notes))
        db.commit()
        return make_or_buy.compare(db, pq, quotes.get_overrides(db))


@mcp.prompt()
def quote_rfq_part(opportunity_id: int) -> str:
    """Walk through quoting a part for one opportunity."""
    return (
        f"Quote the part in GovBid Pro opportunity {opportunity_id}. Call get_opportunity, then pricing_reference. "
        "List the facts you have (material, dimensions, features, quantity, finish, packaging, inspection) and what is missing. "
        "Run estimate_part with only known facts, stating assumptions. If a past award price is known, pass it as "
        "reference_unit_price. Report the price breaks, margin and warnings, then save the quote as a draft with "
        "save_part_quote, putting assumptions and open questions in notes."
    )


def main() -> None:
    ap = argparse.ArgumentParser(prog="govbid-mcp")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1", help="HTTP bind address (keep 127.0.0.1 unless behind auth)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    init_db()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
