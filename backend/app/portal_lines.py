"""Customer quotes, line by line.

Every part is its own line with its own quantity, material, finish, process and price:
  - each single-part STEP file
  - each part of a multi-body STEP assembly (identical bodies grouped, quantity per assembly), its bought parts
    (priced from the hardware library or McMaster-Carr when found), and an assembly line for fit-up and test
  - each part in a DXF file
  - each drawing without a matching model, and circuit board files
A PDF drawing whose name matches a STEP file (or the only drawing next to the only model) is read for that part:
material, finish, tolerance and threads come from it.

The customer can change quantity, material, finish and process on any line (saved in req.line_opts by line key),
and you can set a final price per line in review. Prices are the tool's, corrected by the calibration factors.
Nothing here returns costs or margins to the customer; those stay in the internal copy.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from . import calibration, pricing, quotes

HOT = re.compile(r"turbine|combustor|liner|nozzle guide|\bngv\b|exhaust|tail cone|flame|burner|heat shield", re.I)
PROC_LABEL = {"cnc_mill": "CNC milled", "cnc_5axis": "5-axis CNC milled", "cnc_lathe": "CNC turned", "sheet_metal": "Sheet metal",
              "3d_print": "3D printed", "laser_cut": "Laser cut", "waterjet": "Waterjet cut", "router": "CNC routed", "plasma": "Plasma cut"}


def _stem(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", Path(name or "").stem.lower())


def pair_drawings(steps: list[dict], reads: list[dict]) -> tuple[dict, list[dict]]:
    """{stored STEP name: read} for drawings that belong to a model, and the drawings left over."""
    pairs: dict[str, dict] = {}
    used = set()
    for f in steps:
        st = _stem(f["name"])
        for rd in reads:
            if id(rd) in used or not rd.get("read"):
                continue
            pn = _stem(rd["read"].get("part_number") or "")
            ds = _stem(rd["file"]["name"])
            if ds == st or (pn and len(pn) >= 4 and pn in st) or (len(st) >= 4 and st in ds):
                pairs[f["stored"]] = rd
                used.add(id(rd))
                break
    if len(steps) == 1 and len(reads) == 1 and not pairs and reads[0].get("read"):
        pairs[steps[0]["stored"]] = reads[0]
        used.add(id(reads[0]))
    return pairs, [rd for rd in reads if id(rd) not in used]


def _price_calibrated(fs: dict, process: str, raw: float) -> tuple[float, float, str]:
    f, why = calibration.factor_for(fs, process)
    return round(raw * f, 2), f, why


def _breakdown(est: dict, qty: int) -> dict:
    """Setup (per lot) and run (per part) cost split, for the review page."""
    lot = sum(l["cost"] for l in est.get("per_lot_lines") or est.get("lot_lines") or [] if isinstance(l, dict))
    per = {}
    for l in est.get("per_part_lines") or est.get("part_lines") or []:
        if isinstance(l, dict):
            per[l["category"]] = per.get(l["category"], 0) + l["cost"]
    return {"lot_cost": round(lot, 2), "per_part": {k: round(v, 2) for k, v in per.items()}, "qty": qty}


class Ctx:
    def __init__(self, db: Session, req, s, cfg: dict, over: dict):
        self.db, self.req, self.s, self.cfg, self.over = db, req, s, cfg, over
        self.fs = calibration.factors(db)
        self.n = req.quantity
        self.lo = req.line_opts or {}

    def opt(self, key: str) -> dict:
        return self.lo.get(key) or {}

    def qty(self, key: str, per: int) -> int:
        q = self.opt(key).get("qty")
        try:
            q = int(q) if q not in (None, "") else None
        except (TypeError, ValueError):
            q = None
        return max(1, min(q if q else per * self.n, self.s.max_quantity * max(per, 1)))


def new_line(key: str, name: str, kind: str, route: str, **kw) -> dict:
    out = {"key": key, "name": name, "kind": kind, "route": route, "group": "", "qty": 1, "qty_per": 1, "material": "", "finish": "",
           "process": "", "process_label": "", "desc": "", "unit_price": None, "raw_unit_price": None, "unit_cost": None, "margin_pct": None,
           "lead_days": None, "calibration": None, "facts": [], "view": None, "public_reason": "", "internal_reasons": [], "spec": None,
           "options": None, "incomplete": False, "breakdown": None, "editable": {"qty": True, "material": False, "finish": False, "process": False},
           "final_unit_price": None}
    out.update(kw)
    return out


def apply_final(ctx: Ctx, ln: dict) -> dict:
    """A price you set in review replaces the tool's and is what the customer sees."""
    fp = ctx.opt(ln["key"]).get("final_unit_price")
    if fp not in (None, "") and float(fp) > 0:
        ln["final_unit_price"] = float(fp)
        ln["unit_price"] = float(fp)
        ln["route"] = "instant" if ln["route"] in ("estimate", "manual") else ln["route"]
        ln["public_reason"] = "Price confirmed by our engineer."
        ln["incomplete"] = False
        if ln.get("unit_cost"):
            ln["margin_pct"] = round((ln["unit_price"] - ln["unit_cost"]) / ln["unit_price"] * 100, 1)
    return ln


# ------------------------------------------------------------------ STEP parts
def part_line(ctx: Ctx, key: str, file_id: str, name: str, *, group: str = "", qty_per: int = 1, defaults: dict,
              paired: dict | None = None, geometry: dict | None = None, view: dict | None = None, raw_names: list | None = None) -> dict:
    from . import cad, cad_quote, portal_read

    o = ctx.opt(key)
    qty = ctx.qty(key, qty_per)
    read = (paired or {}).get("read") or {}
    mat = o.get("material") or defaults["material"]
    mat_src = "chosen" if o.get("material") or defaults["material_source"] == "chosen" else defaults["material_source"]
    if o.get("finish") is not None and o.get("finish") != "":
        fins = [] if o["finish"] == "none" else [o["finish"]]
        fin_src = "chosen"
    else:
        fins, fin_src = defaults["finishes"], defaults["finish_source"]
    opts = {"material": mat, "finishes": fins, "quantities": [qty], "name": name}
    tol = (read.get("tolerance") or {}).get("class")
    if tol in ("tight", "precision"):
        opts["tolerance"] = tol
    th = (read.get("threads") or {}).get("count") or 0
    if th:
        opts["threaded_holes"] = int(th)
    try:
        options = cad_quote.process_options(file_id, opts, ctx.over)
    except (cad.CadError, pricing.SpecError, ValueError) as exc:
        options = []
        err = str(exc)
    else:
        err = ""
    if not options:
        return new_line(key, name, "part", "manual", group=group, qty=qty, qty_per=qty_per, material=mat, view=view,
                        public_reason="This part needs a quick look before we can price it.", internal_reasons=[err] if err else [])
    want = o.get("process")
    chosen = next((x for x in options if want and x["process"] == want and (o.get("process_material") in (None, "", x["material"]))), None) \
        or next((x for x in options if not x["note"]), options[0])
    q_opts = {**opts, "process": chosen["process"], "material": chosen["material"]}
    r = cad_quote.quote(file_id, q_opts, ctx.over)
    est = r["estimate"]
    b = est["price_breaks"][0]
    five = bool(r["spec"]["operations"] and r["spec"]["operations"][0].get("five_axis"))
    pkey = "cnc_5axis" if five else chosen["process"]
    price, f, why = _price_calibrated(ctx.fs, pkey, b["unit_price"])
    g = geometry or cad_quote.load(file_id)["geometry"]
    cx = cad_quote.complexity_of(g)
    label = chosen["label"]
    density = (ctx.cfg["materials"].get(chosen["material"]) or ctx.cfg["additive"]["materials"].get(chosen["material"]) or {}).get("density")
    if chosen["material"] in ctx.cfg["additive"]["materials"]:
        density = (density or 0) * 0.0361273  # g/cm3 to lb/in3
    facts = portal_read.step_part(g, chosen["material"], "chosen" if chosen["material"] != mat else mat_src, fins, fin_src, label, density)
    if cx.get("level") in ("complex", "very complex"):
        facts.insert(1, portal_read.row("Complexity", f"{cx['level'].capitalize()}: " + "; ".join(cx.get("reasons") or []), "check"))
    if paired:
        facts.insert(0, portal_read.row("Drawing", f"{paired['file']['name']} (tolerances, threads, material and finish read from it)"))
        if tol in ("tight", "precision"):
            facts.append(portal_read.row("Tolerance", f"{tol}, from the drawing"))
    if HOT.search(name) and not re.search(r"inconel|stainless|titanium|17-4", chosen["material"], re.I):
        facts.append(portal_read.row("Material note", "This looks like a hot-section part. Aluminum will not survive turbine temperatures: "
                                                      "consider Inconel 718 or stainless steel for this line.", "check"))
    alts = [{"process": x["process"], "material": x["material"], "label": x["label"], "unit_price": _price_calibrated(
        ctx.fs, "cnc_5axis" if x["five_axis"] else x["process"], x["unit_price"])[0], "note": x["note"]} for x in options]
    route = "instant"
    reason = ""
    if cx.get("level") in ("complex", "very complex") or five:
        route, reason = "estimate", ("A 5-axis part: " if five else "A complex part: ") + "an engineer confirms the machining plan and price."
    if chosen["note"]:
        route, reason = "estimate", f"Priced {chosen['note']}; an engineer confirms it."
    ln = new_line(key, name, "part", route, group=group, qty=qty, qty_per=qty_per, material=chosen["material"], finish=", ".join(fins) or "none",
                  process=chosen["process"], process_label=label, desc=f"{label}, {chosen['material']}", raw_unit_price=b["unit_price"],
                  unit_price=price, unit_cost=b.get("unit_cost"), margin_pct=round((price - b["unit_cost"]) / price * 100, 1) if b.get("unit_cost") else None,
                  lead_days=b.get("lead_time_days"), calibration={"factor": f, "why": why, "process": pkey} if f != 1 else None,
                  facts=facts, view=view, public_reason=reason, internal_reasons=est.get("warnings", [])[:6], spec=r["spec"],
                  options={"processes": alts}, breakdown=_breakdown(est, qty),
                  editable={"qty": True, "material": True, "finish": True, "process": len(alts) > 1})
    if raw_names:
        ln["raw_names"] = raw_names
    return apply_final(ctx, ln)


def bought_line(ctx: Ctx, key: str, name: str, raw_names: list[str], qty_per: int, group: str) -> dict:
    from . import hardware, portal_read

    qty = ctx.qty(key, qty_per)
    hit = {"found": False}
    for raw in raw_names or [name]:
        hit = hardware.price_bought(ctx.db, raw, qty)
        if hit.get("found"):
            break
    out = ctx.cfg.get("outsourcing") or {}
    facts = [portal_read.row("Bought part", (hit.get("item") or {}).get("description") or name)]
    if hit.get("each") is not None:
        mark = 1 + float(out.get("markup", 0.15))
        handling = float(out.get("handling_per_part", 0.75))
        raw_price = round(hit["each"] * mark + handling, 2)
        price, f, why = raw_price, 1.0, ""
        it = hit["item"]
        facts.append(portal_read.row("Catalog part", f"{it['vendor']} {it['part_number']}".strip()))
        if hit.get("pack_qty", 1) > 1:
            facts.append(portal_read.row("Sold in", f"packs of {hit['pack_qty']}; {hit['packs']} pack(s) for {qty}"))
        ln = new_line(key, name, "bought", "instant", group=group, qty=qty, qty_per=qty_per, desc=f"Bought part, {it['vendor']} {it['part_number']}",
                      process="bought", process_label="Bought", raw_unit_price=raw_price, unit_price=price, unit_cost=hit["each"],
                      margin_pct=round((price - hit["each"]) / price * 100, 1) if price else None, lead_days=5, facts=facts,
                      internal_reasons=[f"{it['source']} price, {it['priced_at'] or 'date unknown'}"])
    else:
        pn = hit.get("part_number")
        facts.append(portal_read.row("Catalog part", f"McMaster-Carr {pn}" if pn else "Not matched to a catalog part yet", "check"))
        ln = new_line(key, name, "bought", "manual", group=group, qty=qty, qty_per=qty_per, desc="Bought part", process="bought",
                      process_label="Bought", facts=facts, public_reason="A bought part: we add its price when we confirm.",
                      internal_reasons=["Add it to the hardware library (or connect McMaster-Carr) to price it automatically."], incomplete=True)
    return apply_final(ctx, ln)


def assembly_line(ctx: Ctx, key: str, name: str, made: list[dict], bought: list[dict], geometry: dict, view: dict | None,
                  facts: list[dict]) -> dict:
    """Fit-up, assembly and inspection of one assembly (per set)."""
    rates = ctx.cfg["rates"]
    pieces = sum(int(g.get("qty", 1)) for g in made) + sum(int(g.get("qty", 1)) for g in bought)
    minutes = 15 + 8 * len(made) + 1.5 * pieces
    insp = 10 + 2 * len(made)
    cost = minutes / 60 * rates["assembly"] + insp / 60 * rates["inspection"]
    ga, profit = float(ctx.cfg.get("ga_rate", 0.1)), float(ctx.cfg.get("profit_rate", 0.15))
    raw = round(cost * (1 + ga) * (1 + profit), 2)
    price, f, why = _price_calibrated(ctx.fs, "assembly", raw)
    ln = new_line(key, f"Assembly and inspection, {name}", "assembly", "estimate", group=name, qty=ctx.qty(key, 1), qty_per=1,
                  desc=f"Fit-up and assembly of {pieces} pieces, inspection", process="assembly", process_label="Assembly",
                  raw_unit_price=raw, unit_price=price, unit_cost=round(cost, 2), margin_pct=round((price - cost) / price * 100, 1),
                  calibration={"factor": f, "why": why, "process": "assembly"} if f != 1 else None, facts=facts, view=view,
                  public_reason="An engineer confirms how it goes together (welded, fastened or bonded) and the assembly time.",
                  breakdown={"lot_cost": 0, "per_part": {"assembly": round(minutes / 60 * rates["assembly"], 2),
                                                          "inspection": round(insp / 60 * rates["inspection"], 2)}, "qty": ctx.n})
    return apply_final(ctx, ln)


# ------------------------------------------------------------------ DXF
def flat_lines(ctx: Ctx, dxfs: list[dict], defaults: dict, drawing_mat: str | None) -> list[dict]:
    from . import flat, portal_read
    from . import portal_views as pv
    from .portal import _view, file_path

    req = ctx.req
    if not req.thickness:
        return [new_line("dxf", ", ".join(Path(f["name"]).stem for f in dxfs)[:80], "flat", "needs_input", desc="Flat parts (DXF)",
                         public_reason="Choose the sheet thickness to price your DXF parts.")]
    try:
        parsed = flat.parse_files([(f["name"], file_path(req, f).read_bytes()) for f in dxfs], keep_shapes=True)
    except Exception as exc:  # noqa: BLE001
        return [new_line("dxf", "Flat parts (DXF)", "flat", "manual", public_reason="We could not read these DXF files automatically.",
                         internal_reasons=[str(exc)])]
    mats = flat.materials(ctx.cfg)
    out = []
    by_file = {f["name"]: f for f in dxfs}
    for p in parsed["parts"]:
        shape = p.pop("shape", None)
        f = by_file.get(p.get("file")) or dxfs[0]
        key = f"{f['stored']}#{p['id']}"
        o = ctx.opt(key)
        mat = o.get("material") if o.get("material") in mats else (req.material if req.material in mats else
                                                                   (drawing_mat if drawing_mat in mats else "A36 / 1018 steel"))
        msrc = "chosen" if (o.get("material") in mats or req.material == mat) else ("drawing" if drawing_mat == mat else "default")
        t = float(o.get("thickness") or req.thickness)
        cls = flat.material_class(mat)
        process = "router" if cls in ("wood", "plastic", "composite") and "acrylic" not in mat.lower() else ("waterjet" if t > 0.75 else "laser_cut")
        options = {"material": mat, "thickness": t, "process": process}
        fin = o.get("finish") if o.get("finish") not in (None, "") else (req.finish or "")
        if fin and fin != "none" and fin in ctx.cfg["finishes"]:
            options["finishes"] = [fin]
        qty = ctx.qty(key, int(p.get("qty", 1)))
        part = {**flat.clean_part(p), "qty": 1}
        try:
            r = flat.estimate([part], options, [qty], ctx.over)
        except Exception as exc:  # noqa: BLE001
            out.append(new_line(key, p.get("name") or "Flat part", "flat", "manual", qty=qty, internal_reasons=[str(exc)],
                                public_reason="We will price this part by hand."))
            continue
        b = r["price_breaks"][0]
        price, fct, why = _price_calibrated(ctx.fs, "flat", b["unit_price"])
        view = None
        if shape:
            view = _view(req, ("dxf", f["stored"], p["id"], t), lambda sh=shape, t=t: pv.flat_shape(sh["outer"], sh["holes"], t), "flat")
        label = PROC_LABEL.get(process, process)
        spec = {"kind": "flat_dxf", "name": p.get("name") or "Flat part", "quantities": [qty], "parts": [part], "options": options, "material": mat,
                "source": {"files": []}}
        ln = new_line(key, p.get("name") or "Flat part", "flat", "instant", qty=qty, qty_per=int(p.get("qty", 1)), material=mat,
                      finish=fin or "none", process=process, process_label=label, desc=f"{label}, {mat}, {t:g} in", raw_unit_price=b["unit_price"],
                      unit_price=price, unit_cost=b.get("unit_cost"), margin_pct=round((price - b["unit_cost"]) / price * 100, 1) if b.get("unit_cost") else None,
                      lead_days=b.get("lead_time_days"), calibration={"factor": fct, "why": why, "process": "flat"} if fct != 1 else None,
                      facts=portal_read.flat_parts([p], t, mat, msrc, label)[1:], view=view, spec=spec, breakdown=_breakdown(r, qty),
                      internal_reasons=r.get("warnings", [])[:4], editable={"qty": True, "material": True, "finish": True, "process": False})
        out.append(apply_final(ctx, ln))
    return out
