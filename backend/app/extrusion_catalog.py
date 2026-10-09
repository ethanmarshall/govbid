"""Catalog of T-slot aluminum extrusion profiles, machining operations, hardware and panels.

PRICES IN THIS FILE ARE PLACEHOLDERS. They are round numbers picked only so the estimator runs.
They are not distributor prices and must not be quoted. Replace every one with your distributor's
current price (80/20 dealer, Misumi, Bosch Rexroth, Item, Faztek) in the Extrusion rates panel on
the Part quotes page; saved values live in the shop-rate config under "extrusion.prices".

What was checked (8020.net product pages, fetched 2026-10-09; no prices were copied):
- Profile names, series and sizes: https://8020.net/framing-options/t-slotted-profiles.html lists the
  fractional 10 Series (1010, 1020, 1030, 1050), 15 Series (1515, 1515-LS, 1530, 1530-LS, 1545) and the
  metric 20, 25, 30, 40 and 45 Series (20-2020, 20-2040, 25-2525, 30-3030, 40-4040, 40-4080, 45-4545).
- 80/20 files 2020 (2.00 x 2.00 in) under the 10 Series and 3030 (3.00 x 3.00 in) under the 15 Series
  (https://8020.net/2020.html, https://8020.net/3030.html).
- Weights per inch come from each product page (for example https://8020.net/1515.html: 0.1123 lb/in;
  https://8020.net/1010.html: 0.0424 lb/in; https://8020.net/40-4040.html: 0.1321 lb/in).
- Lengths: the fractional pages list a 242 in maximum length and the metric pages 238.19 in (about
  6,050 mm). Those are the default "full stick" lengths below; set your distributor's stick length.
- Standard machining operation names on the 1010, 1515, 20-2020 and 40-4040 pages: End Tap, Counterbore,
  Access Hole, Mitercut, Mitercut Counterbore, Central Connector Counterbore, Drill Thru & Counterbore
  (80/20 operation numbers such as 7050 access hole on 1515 or 7051 on 1010 vary by series; pick the
  exact number in the 80/20 configurator when ordering). "Drill thru" alone is a generic operation
  most suppliers and shops offer, not an 80/20 catalog name.
- Misumi part numbers (HFS5-2020, HFS6-3030, HFS8-4040 ...) follow Misumi's HFS naming; weights for
  them are left blank here. Hardware and panel names are generic descriptions, not supplier part numbers.
"""
from __future__ import annotations

import copy

PLACEHOLDER_NOTE = ("Placeholder prices, not distributor quotes. Replace every price with your supplier's "
                    "current price before quoting.")

# Hardware is sized by profile family: the slot and bolt size differ between series.
FAMILIES = {
    "10": "Fractional 10 Series (1 in, 1/4-20 hardware)",
    "15": "Fractional 15 Series (1.5 in, 5/16-18 hardware)",
    "MS": "Metric small (20, 25, 30 mm; Misumi 5 and 6 series)",
    "ML": "Metric large (40, 45 mm; Misumi 8 series)",
}

# id, vendor, series, family, size, weight lb/in (None = not checked), placeholder price per inch
_PROFILES: list[tuple[str, str, str, str, str, float | None, float]] = [
    ("1010", "80/20", "10", "10", "1.00 x 1.00 in", 0.0424, 0.25),
    ("1020", "80/20", "10", "10", "1.00 x 2.00 in", 0.0768, 0.42),
    ("1030", "80/20", "10", "10", "1.00 x 3.00 in", 0.1112, 0.60),
    ("2020", "80/20", "10", "10", "2.00 x 2.00 in", 0.1198, 0.65),
    ("1515", "80/20", "15", "15", "1.50 x 1.50 in", 0.1123, 0.55),
    ("1515-LS", "80/20", "15", "15", "1.50 x 1.50 in, Lite smooth", 0.0860, 0.45),
    ("1530", "80/20", "15", "15", "1.50 x 3.00 in", 0.2025, 0.95),
    ("1530-LS", "80/20", "15", "15", "1.50 x 3.00 in, Lite smooth", 0.1640, 0.80),
    ("1545", "80/20", "15", "15", "1.50 x 4.50 in", 0.2927, 1.35),
    ("3030", "80/20", "15", "15", "3.00 x 3.00 in", 0.3132, 1.50),
    ("20-2020", "80/20", "20", "MS", "20 x 20 mm", 0.0247, 0.18),
    ("20-2040", "80/20", "20", "MS", "20 x 40 mm", 0.0428, 0.28),
    ("25-2525", "80/20", "25", "MS", "25 x 25 mm", 0.0415, 0.25),
    ("30-3030", "80/20", "30", "MS", "30 x 30 mm", 0.0487, 0.30),
    ("40-4040", "80/20", "40", "ML", "40 x 40 mm", 0.1321, 0.60),
    ("40-4080", "80/20", "40", "ML", "40 x 80 mm", 0.2317, 1.05),
    ("45-4545", "80/20", "45", "ML", "45 x 45 mm", 0.1143, 0.65),
    ("HFS5-2020", "Misumi", "5", "MS", "20 x 20 mm", None, 0.18),
    ("HFS5-2040", "Misumi", "5", "MS", "20 x 40 mm", None, 0.28),
    ("HFS6-3030", "Misumi", "6", "MS", "30 x 30 mm", None, 0.30),
    ("HFS6-3060", "Misumi", "6", "MS", "30 x 60 mm", None, 0.50),
    ("HFS8-4040", "Misumi", "8", "ML", "40 x 40 mm", None, 0.60),
    ("HFS8-4080", "Misumi", "8", "ML", "40 x 80 mm", None, 1.05),
]

# Machining operations: id -> (label, placeholder price each, note)
MACHINING_OPS: dict[str, tuple[str, float, str]] = {
    "end_tap": ("End tap", 2.50, "Tap the profile's center hole(s) at one end. Count each end."),
    "counterbore": ("Counterbore", 3.00, "Counterbore for an anchor or other fastener. Count each one."),
    "access_hole": ("Access hole", 2.50, "Hole for a wrench to reach an anchor fastener. Count each one."),
    "drill_thru": ("Drill thru", 3.00, "Generic through hole across the profile."),
    "drill_thru_cbore": ("Drill thru & counterbore", 4.00, "Through hole with counterbore (80/20 catalog name)."),
    "miter_cut": ("Mitercut", 6.00, "Angled cut. Count each mitered end."),
    "miter_cbore": ("Mitercut counterbore", 4.00, "Counterbore on a mitered end."),
    "central_connector_cbore": ("Central connector counterbore", 4.00, "Counterbore for a central connector."),
}

# Hardware: base id -> (label, assembly class, placeholder price each by family {10, 15, MS, ML})
# Assembly class drives labor: joint, fastener, accessory or none.
_HARDWARE: list[tuple[str, str, str, dict[str, float]]] = [
    ("TNUT-DROP", "Drop-in T-nut", "fastener", {"10": 0.60, "15": 0.80, "MS": 0.50, "ML": 0.70}),
    ("TNUT-SLIDE", "Slide-in T-nut", "fastener", {"10": 0.40, "15": 0.55, "MS": 0.35, "ML": 0.50}),
    ("TNUT-ECON", "Economy T-nut", "fastener", {"10": 0.25, "15": 0.35, "MS": 0.25, "ML": 0.35}),
    ("SCREW-BHSCS", "Button head socket cap screw", "none", {"10": 0.20, "15": 0.25, "MS": 0.15, "ML": 0.25}),
    ("ANCHOR", "Anchor fastener assembly", "joint", {"10": 2.00, "15": 2.50, "MS": 2.00, "ML": 2.50}),
    ("BRKT-4H", "Corner bracket, 4-hole", "joint", {"10": 3.00, "15": 4.00, "MS": 2.50, "ML": 3.50}),
    ("BRKT-5H", "Corner bracket, 5-hole", "joint", {"10": 4.00, "15": 5.00, "MS": 3.00, "ML": 4.50}),
    ("BRKT-GUSSET", "Gusseted corner bracket", "joint", {"10": 5.00, "15": 7.00, "MS": 4.00, "ML": 6.00}),
    ("PLATE-L", "Joining plate, L", "joint", {"10": 5.00, "15": 7.00, "MS": 4.00, "ML": 6.00}),
    ("PLATE-T", "Joining plate, T", "joint", {"10": 5.00, "15": 7.00, "MS": 4.00, "ML": 6.00}),
    ("PLATE-FLAT", "Joining plate, flat (straight)", "joint", {"10": 4.00, "15": 6.00, "MS": 3.50, "ML": 5.00}),
    ("ENDCAP", "End cap", "accessory", {"10": 0.75, "15": 1.00, "MS": 0.60, "ML": 0.90}),
    ("FOOT", "Leveling foot", "accessory", {"10": 6.00, "15": 8.00, "MS": 5.00, "ML": 7.00}),
    ("CASTER", "Caster, swivel", "accessory", {"10": 15.00, "15": 20.00, "MS": 14.00, "ML": 18.00}),
    ("CASTER-LOCK", "Caster, swivel with brake", "accessory", {"10": 20.00, "15": 25.00, "MS": 18.00, "ML": 23.00}),
    ("RETAINER", "Panel retainer (gasket or clip)", "fastener", {"10": 0.50, "15": 0.60, "MS": 0.40, "ML": 0.50}),
    ("HINGE", "Hinge", "accessory", {"10": 8.00, "15": 12.00, "MS": 7.00, "ML": 10.00}),
    ("HANDLE", "Handle", "accessory", {"10": 8.00, "15": 10.00, "MS": 7.00, "ML": 9.00}),
]

# Panels: id -> (label, material key, thickness in, placeholder price per square foot)
PANELS: dict[str, tuple[str, str, float, float]] = {
    "PANEL-PC-125": ("Polycarbonate, clear, 1/8 in", "PC", 0.125, 6.00),
    "PANEL-PC-187": ("Polycarbonate, clear, 3/16 in", "PC", 0.1875, 8.00),
    "PANEL-PC-250": ("Polycarbonate, clear, 1/4 in", "PC", 0.25, 10.00),
    "PANEL-ACR-125": ("Acrylic, clear, 1/8 in", "ACR", 0.125, 5.00),
    "PANEL-ACR-187": ("Acrylic, clear, 3/16 in", "ACR", 0.1875, 6.50),
    "PANEL-ACR-250": ("Acrylic, clear, 1/4 in", "ACR", 0.25, 8.00),
    "PANEL-ACM-118": ("Aluminum composite (ACM), 3 mm", "ACM", 0.118, 5.00),
    "PANEL-ACM-157": ("Aluminum composite (ACM), 4 mm", "ACM", 0.157, 6.00),
}
PANEL_MATERIALS = {"PC": "Polycarbonate", "ACR": "Acrylic", "ACM": "Aluminum composite (ACM)"}


def profile_rows() -> list[dict]:
    return [{"id": i, "vendor": v, "series": s, "family": f, "size": size, "weight_lb_per_in": w,
             "metric": f in ("MS", "ML")} for i, v, s, f, size, w, _ in _PROFILES]


def hardware_rows() -> list[dict]:
    out = []
    for base, label, cls, _ in _HARDWARE:
        for fam in FAMILIES:
            out.append({"id": f"{base}-{fam}", "base": base, "family": fam, "assembly": cls,
                        "name": f"{label}, {FAMILIES[fam].split(' (')[0]}"})
    return out


def default_prices() -> dict:
    """Placeholder prices keyed by catalog id: profiles $/in, hardware $/each, panels $/sq ft, machining $/op."""
    return {
        "profiles": {i: p for i, *_, p in _PROFILES},
        "hardware": {f"{base}-{fam}": prices[fam] for base, _, _, prices in _HARDWARE for fam in FAMILIES},
        "panels": {k: v[3] for k, v in PANELS.items()},
    }


def default_config() -> dict:
    """Default shop-rate settings for extrusion builds (stored as pricing.DEFAULT_CONFIG['extrusion'])."""
    return {
        "note": PLACEHOLDER_NOTE,
        # "cut_to_length": the supplier cuts and machines each piece (price per inch + cut charge).
        # "stock": you buy full sticks and cut them in house (sticks are nested first-fit decreasing).
        "pricing_mode": "cut_to_length",
        "stock_length_in": {"fractional": 242.0, "metric": 238.19},
        "full_stick_price_factor": 1.0,  # stick price = stock length x price per inch x this factor
        "kerf_in": 0.125,
        "end_trim_in": 0.5,  # trimmed off each stick before cutting
        "cut_charge": 3.0,  # supplier charge per cut (cut_to_length mode)
        "inhouse_cut_minutes": 2.0,  # saw time per piece at the fabrication rate (stock mode)
        "machining": {k: v[1] for k, v in MACHINING_OPS.items()},  # $ per operation
        "assembly_minutes": {"per_build": 15.0, "per_joint": 4.0, "per_fastener": 0.5, "per_panel": 10.0, "per_accessory": 2.0},
        "inspection_minutes_per_build": 10.0,
        "kitting_hours_per_lot": 0.5,  # cut list, kitting and staging, at the fabrication rate
        "supplier_order_charge": 50.0,  # inbound freight and handling from the extrusion distributor, per lot
        "crate_per_build": 35.0,  # added to the packaging level's per-part charge
        "panel_waste_factor": 0.15,
        "supplier_lead_days": 7,
        "builds_per_day": 4,
        "prices": default_prices(),
    }


def catalog(config: dict | None = None) -> dict:
    """The catalog with current prices from the extrusion config (placeholders until the owner edits them).

    Ids found in config prices but not in the built-in catalog are returned as custom items.
    """
    ext = (config or {}).get("extrusion") or default_config()
    prices = ext.get("prices") or default_prices()
    profiles = []
    known = set()
    for p in profile_rows():
        p = copy.deepcopy(p)
        p["price_per_in"] = float(prices.get("profiles", {}).get(p["id"], 0.0))
        p["name"] = f"{p['id']} {p['vendor']} {p['series']} series, {p['size']}"
        profiles.append(p)
        known.add(p["id"])
    for pid, price in (prices.get("profiles") or {}).items():
        if pid not in known:
            profiles.append({"id": pid, "vendor": "custom", "series": "", "family": "", "size": "", "weight_lb_per_in": None,
                             "metric": False, "price_per_in": float(price), "name": f"{pid} (custom profile)"})
    hardware = []
    known = set()
    for h in hardware_rows():
        h["unit_price"] = float(prices.get("hardware", {}).get(h["id"], 0.0))
        hardware.append(h)
        known.add(h["id"])
    for hid, price in (prices.get("hardware") or {}).items():
        if hid not in known:
            hardware.append({"id": hid, "base": hid, "family": "", "assembly": "none", "name": f"{hid} (custom item)", "unit_price": float(price)})
    panels = []
    for pid, (label, mat, thk, _) in PANELS.items():
        panels.append({"id": pid, "name": label, "material": mat, "thickness_in": thk,
                       "price_per_sqft": float(prices.get("panels", {}).get(pid, 0.0))})
    for pid, price in (prices.get("panels") or {}).items():
        if pid not in PANELS:
            panels.append({"id": pid, "name": f"{pid} (custom panel)", "material": "", "thickness_in": None, "price_per_sqft": float(price)})
    machining = [{"id": k, "name": v[0], "price": float((ext.get("machining") or {}).get(k, v[1])), "note": v[2]}
                 for k, v in MACHINING_OPS.items()]
    return {"profiles": profiles, "hardware": hardware, "panels": panels, "machining": machining,
            "families": FAMILIES, "note": PLACEHOLDER_NOTE}
