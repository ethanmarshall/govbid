"""Rates, placeholder prices and reference tables for the electrical quoters (app/electrical.py).

Three quote kinds share this module:
  harness  cable and wire harness assemblies (FSC 5995 style buys)
  panel    control panels and power distribution enclosures (FSC 6110 / 6150 style buys)
  labels   nameplates, tags, labels, wire markers and IUID marks

Every price and minute in the *_default() dicts is a PLACEHOLDER chosen to make the math visible,
not market data. The owner replaces them in the Part quotes rates panels (saved in the shop-rate
config under "harness", "panel" and "labels").

Reference facts used here (checked 2026-10-09):
- Contact size to wire range for MIL-DTL-38999 crimp contacts (M39029/58 pins and /56 sockets):
  22D 22-28 AWG, 22 22-26, 22M 24-28, 20 20-24, 16 16-20, 12 12-14, 10 10 AWG.
  Sources: Milnec M39029 cross reference (https://www.milnec.com/m39029-contact-cross-reference/),
  Glenair SuperNine contacts catalog (https://www.glenair.com/supernine-series-i/pdf/contacts-and-tools/contacts.pdf).
- IPC/WHMA-A-620 product classes: Class 1 general electronic products, Class 2 dedicated service
  electronic products, Class 3 high performance / harsh environment electronic products.
  Source: https://telewiretech.com/blogs/technical-resources/ipc-whma-a-620-class-2-vs-class-3-workmanship-requirements
  The labor multipliers per class are this app's assumptions, not part of the standard.
- UL 508A: UL's Industrial Control Panels program lets enrolled panel manufacturers apply the UL mark
  at their own factory; they must complete UL 508A training and keep a qualified manufacturer
  technical representative (MTR) on staff. Source: https://www.ul.com/offerings/industrial-control-panels-and-panel-shop-program
  UL also visits enrolled shops for follow-up inspections (third-party description, not UL:
  https://industrialmonitordirect.com/blogs/knowledgebase/becoming-a-ul-508a-listed-panel-shop-costs-process-requirements).
- IUID: DFARS 252.211-7003 requires unique item identification for delivered items with a
  government unit acquisition cost of $5,000 or more (and others the contract lists), with marks
  placed and verified per MIL-STD-130 (latest version, Appendix A for verification), Data Matrix per
  ISO/IEC 16022, and UII data reported to the IUID Registry (through the WAWF receiving report for
  end items). Source: https://www.acquisition.gov/dfars/252.211-7003-item-unique-identification-and-valuation.
  MIL-STD-130 Data Matrix marks are commonly verified to a grade of B or better
  (ISO/IEC 15415, AIM DPM-1-2006 or SAE AS9132). Source: https://en.wikipedia.org/wiki/MIL-STD-130
- MIL-DTL-15024 (rev G, 3 March 2018): "Plates, Tags, and Bands for Identification of Equipment,
  General Specification For". Source: https://everyspec.com/MIL-SPECS/MIL-SPECS-MIL-DTL/MIL-DTL-15024G_56365/
"""
from __future__ import annotations

import copy

PLACEHOLDER_NOTE = "Placeholder prices and times. Replace them with your distributor prices and your own time studies before quoting."

# ---------------------------------------------------------------- reference tables (not editable rates)
CONTACT_SIZE_AWG: dict[str, tuple[int, int]] = {
    # contact size -> (largest wire AWG number accepted, smallest wire AWG number accepted)
    "22D": (22, 28), "22": (22, 26), "22M": (24, 28), "20": (20, 24), "16": (16, 20), "12": (12, 14), "10": (10, 10),
}
CONTACT_SIZE_SOURCE = "MIL-DTL-38999 crimp contacts (M39029/58 and /56), per Milnec and Glenair contact tables"

# M39029/58 (pin) and /56 (socket) dash numbers for 38999 Series III contacts -> contact size
M39029_DASH_SIZE = {
    "58-360": "22D", "56-348": "22D", "58-361": "22M", "56-349": "22M", "58-362": "22", "56-350": "22",
    "58-363": "20", "56-351": "20", "58-364": "16", "56-352": "16", "58-365": "12", "56-353": "12",
    "58-528": "10", "56-527": "10",
}

WORKMANSHIP_CLASSES = {
    "class_1": "Class 1: general electronic products (the assembly must function)",
    "class_2": "Class 2: dedicated service electronic products (long life, uninterrupted service desired but not critical)",
    "class_3": "Class 3: high performance / harsh environment products (continued performance required, typical for military)",
}
WORKMANSHIP_SOURCE = "IPC/WHMA-A-620 product classes. The multipliers are your assumptions, not part of the standard."

WIRE_SPECS = {
    "M22759/16": "M22759/16 ETFE insulated, tin plated copper, 150 C",
    "M22759/32": "M22759/32 crosslinked ETFE, tin plated copper, thin wall",
    "M22759/11": "M22759/11 PTFE insulated, silver plated copper, 200 C",
    "M16878/4": "M16878/4 PTFE insulated hookup wire (type E)",
    "UL1007": "UL 1007 PVC hookup wire, 300 V",
    "UL1015": "UL 1015 PVC machine tool wire, 600 V",
    "MIL-W-76": "MIL-W-76 PVC hookup wire",
}
GAUGES = ["4", "6", "8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28"]

TERMINATIONS = {
    "crimp": "Crimp contact inserted in a connector",
    "solder": "Solder cup or solder joint",
    "lug": "Crimp ring or spade lug (no insertion)",
    "splice": "Crimp or solder splice (sealed)",
    "open": "Flying lead, strip only",
}

PANEL_DEVICE_TYPES = {
    "enclosure": "Enclosure",
    "back_panel": "Back panel / subpanel",
    "din_rail": "DIN rail (per meter)",
    "wire_duct": "Wire duct (per meter)",
    "breaker": "Circuit breaker",
    "fuse": "Fuse / fuse holder",
    "disconnect": "Disconnect switch",
    "terminal_block": "Terminal block",
    "relay": "Relay",
    "contactor": "Contactor / starter / overload",
    "power_supply": "Power supply",
    "plc": "PLC / controller CPU",
    "io_module": "I/O module",
    "hmi": "HMI / operator display",
    "pilot_device": "Pilot device (push button, light, selector, E-stop)",
    "meter": "Panel meter / indicator",
    "other": "Other (priced by hand)",
}
LENGTH_PRICED = ("din_rail", "wire_duct")

LABEL_TYPES = {
    "engraved_laminate": "Engraved laminate tag (phenolic or acrylic)",
    "anodized_aluminum": "Anodized aluminum nameplate (laser marked)",
    "photo_anodized_aluminum": "Photo-anodized aluminum nameplate",
    "stainless_steel": "Stainless steel plate, laser engraved",
    "printed_polyester": "Printed polyester label",
    "printed_vinyl": "Printed vinyl label",
    "heat_shrink_marker": "Heat shrink wire marker sleeve",
}


# ---------------------------------------------------------------- editable defaults (all placeholders)
def harness_default() -> dict:
    wire = {
        # $/ft by gauge. Placeholders only: real mil-spec wire prices swing with copper and plating.
        "M22759/16": {"10": 1.60, "12": 1.10, "14": 0.75, "16": 0.50, "18": 0.38, "20": 0.30, "22": 0.24, "24": 0.21, "26": 0.20},
        "M22759/32": {"12": 1.20, "14": 0.80, "16": 0.55, "18": 0.42, "20": 0.33, "22": 0.27, "24": 0.24, "26": 0.22},
        "M22759/11": {"12": 1.60, "14": 1.10, "16": 0.80, "18": 0.60, "20": 0.48, "22": 0.40, "24": 0.36, "26": 0.34},
        "M16878/4": {"12": 1.30, "14": 0.90, "16": 0.62, "18": 0.45, "20": 0.36, "22": 0.30, "24": 0.26, "26": 0.24},
        "UL1007": {"16": 0.16, "18": 0.11, "20": 0.08, "22": 0.06, "24": 0.05, "26": 0.05, "28": 0.05},
        "UL1015": {"10": 0.55, "12": 0.38, "14": 0.25, "16": 0.18, "18": 0.13, "20": 0.10, "22": 0.08},
        "MIL-W-76": {"16": 0.30, "18": 0.24, "20": 0.20, "22": 0.17, "24": 0.15},
    }
    return {
        "note": PLACEHOLDER_NOTE,
        "labor_rate": 55.0,  # harness assembly $/h, burdened
        "test_rate": 70.0,  # electrical test $/h
        "waste_factor": 0.05,  # extra wire for trim, service loops, scrap
        "wire_per_ft": wire,
        "wire_default_per_ft": {"4": 4.0, "6": 2.8, "8": 2.0, "10": 1.4, "12": 1.0, "14": 0.7, "16": 0.45, "18": 0.35, "20": 0.28, "22": 0.22, "24": 0.20, "26": 0.18, "28": 0.18},
        "shield_adder_per_ft": 0.60,  # shielded single or pair over the base wire price
        "twist_adder_per_ft": 0.10,  # twisting labor/material allowance per foot of each conductor
        "placeholder_prices": {"connector": 35.0, "contact": 1.25, "backshell": 28.0, "accessory": 0.50, "other": 5.0},
        "consumables": {"wire_marker_each": 0.25, "heat_shrink_each": 0.30, "cable_tie_each": 0.06, "sleeving_per_ft": 0.80, "lacing_per_ft": 0.12},
        "minutes": {
            "cut_strip_per_end": 0.35,
            "crimp_per_contact": 0.60,
            "solder_per_joint": 1.50,
            "insert_per_contact": 0.35,
            "lug_per_end": 0.80,
            "splice_per_end": 1.50,
            "backshell_per_connector": 8.0,
            "shield_term_per_end": 5.0,
            "mark_per_wire": 0.75,
            "heat_shrink_each": 0.50,
            "sleeving_per_ft": 1.00,
            "layout_base": 15.0,
            "layout_per_branch": 6.0,
            "tie_each": 0.20,
        },
        "ties_per_branch": 6.0,
        "workmanship_multiplier": {"class_1": 0.85, "class_2": 1.0, "class_3": 1.35},
        "test": {"continuity_setup_minutes": 20.0, "continuity_per_circuit_minutes": 0.40,
                 "hipot_setup_minutes": 20.0, "hipot_per_circuit_minutes": 0.25, "hipot_per_harness_minutes": 2.0},
        "formboard_hours_per_lot": 2.0,  # build or adjust the formboard / layout fixture
        "kitting_hours_per_lot": 1.0,
        "first_article_hours": 4.0,
        "supplier_lead_days": 21,
        "harnesses_per_day": 4,
    }


def panel_default() -> dict:
    return {
        "note": PLACEHOLDER_NOTE,
        "labor_rate": 65.0,  # panel build $/h
        "test_rate": 75.0,
        "drafting_rate": 80.0,  # as-built drawings and documentation $/h
        "placeholder_prices": {
            "enclosure": 450.0, "back_panel": 60.0, "din_rail": 8.0, "wire_duct": 14.0, "breaker": 45.0, "fuse": 18.0,
            "disconnect": 180.0, "terminal_block": 3.50, "relay": 25.0, "contactor": 85.0, "power_supply": 140.0,
            "plc": 600.0, "io_module": 300.0, "hmi": 1200.0, "pilot_device": 35.0, "meter": 120.0, "other": 25.0,
        },
        "mount_minutes": {  # mount and hardware per device (rail and duct are per meter below)
            "enclosure": 30.0, "back_panel": 15.0, "breaker": 4.0, "fuse": 4.0, "disconnect": 30.0, "terminal_block": 1.0,
            "relay": 3.0, "contactor": 8.0, "power_supply": 8.0, "plc": 15.0, "io_module": 6.0, "hmi": 20.0,
            "pilot_device": 6.0, "meter": 10.0, "other": 8.0,
        },
        "device_terminations": {  # internal wire landings per device, used only to estimate a wire count
            "breaker": 4.0, "fuse": 2.0, "disconnect": 6.0, "terminal_block": 1.0, "relay": 6.0, "contactor": 8.0,
            "power_supply": 5.0, "plc": 4.0, "io_module": 18.0, "hmi": 4.0, "pilot_device": 3.0, "meter": 4.0, "other": 2.0,
        },
        "din_rail_minutes_per_m": 8.0,  # cut, deburr, drill and mount
        "wire_duct_minutes_per_m": 12.0,  # cut, mount, cover
        "back_panel_layout_minutes": 45.0,  # per panel: layout and drilling pattern
        "cutout_minutes": {"operator_device": 10.0, "hmi": 45.0, "meter": 30.0, "round_hole": 5.0, "rect_cutout": 30.0},
        "wiring": {"minutes_per_wire": 6.0, "consumables_per_wire": 0.60, "wires_per_io_point": 1.5, "io_points_per_module": 16.0},
        "labeling": {"wire_marker_each": 0.15, "marker_minutes": 0.25, "device_tag_each": 1.50, "device_tag_minutes": 1.0,
                     "legend_plate_each": 4.0, "nameplate_each": 18.0, "nameplate_minutes": 5.0},
        "testing": {"point_to_point_minutes_per_wire": 0.5, "power_up_minutes": 30.0, "io_check_minutes_per_point": 1.5},
        "documentation_hours": 4.0,  # per lot: as-built schematics, layout, BOM
        "ul508a": {"label_per_panel": 15.0, "inspection_minutes_per_panel": 30.0, "program_cost_per_lot": 150.0, "design_review_hours": 2.0},
        "crate_per_panel": 85.0,
        "freight_per_lot": 175.0,
        "kitting_hours_per_lot": 2.0,
        "first_article_hours": 4.0,
        "supplier_lead_days": 28,
        "panels_per_day": 1,
    }


def labels_default() -> dict:
    return {
        "note": PLACEHOLDER_NOTE,
        "laser_rate": 85.0,  # $/h laser or printer time
        "labor_rate": 45.0,  # finishing, drilling, applying adhesive, packing
        "materials": {
            # price per square inch, minimum material per piece, marking seconds per character and per square inch of fill
            "engraved_laminate": {"label": LABEL_TYPES["engraved_laminate"], "price_per_sqin": 0.06, "min_material": 0.75,
                                  "seconds_per_char": 1.5, "seconds_per_sqin": 0.0, "handling_seconds": 30.0},
            "anodized_aluminum": {"label": LABEL_TYPES["anodized_aluminum"], "price_per_sqin": 0.10, "min_material": 1.25,
                                  "seconds_per_char": 1.0, "seconds_per_sqin": 0.0, "handling_seconds": 30.0},
            "photo_anodized_aluminum": {"label": LABEL_TYPES["photo_anodized_aluminum"], "price_per_sqin": 0.18, "min_material": 2.0,
                                        "seconds_per_char": 0.0, "seconds_per_sqin": 6.0, "handling_seconds": 45.0},
            "stainless_steel": {"label": LABEL_TYPES["stainless_steel"], "price_per_sqin": 0.22, "min_material": 2.5,
                                "seconds_per_char": 4.0, "seconds_per_sqin": 0.0, "handling_seconds": 40.0},
            "printed_polyester": {"label": LABEL_TYPES["printed_polyester"], "price_per_sqin": 0.03, "min_material": 0.15,
                                  "seconds_per_char": 0.0, "seconds_per_sqin": 0.8, "handling_seconds": 5.0},
            "printed_vinyl": {"label": LABEL_TYPES["printed_vinyl"], "price_per_sqin": 0.02, "min_material": 0.10,
                              "seconds_per_char": 0.0, "seconds_per_sqin": 0.8, "handling_seconds": 5.0},
            "heat_shrink_marker": {"label": LABEL_TYPES["heat_shrink_marker"], "price_per_sqin": 0.0, "min_material": 0.20,
                                   "seconds_per_char": 0.0, "seconds_per_sqin": 0.0, "handling_seconds": 3.0},
        },
        "hole_minutes": 0.5,  # drill and deburr one mounting hole
        "adhesive_per_sqin": 0.01,  # 3M style transfer adhesive backing
        "adhesive_minutes": 0.3,
        "setup_minutes_per_design": 15.0,  # artwork, layout and first piece check per unique design
        "iuid": {"mark_seconds": 30.0,  # laser time to mark one Data Matrix symbol plus its human readable text
                 "generate_minutes": 1.0,  # build the UII string and Data Matrix for one serialized mark
                 "verify_minutes": 1.0,  # grade the mark with a verifier and record the result
                 "registry_minutes": 1.5,  # prepare the UII data for the IUID Registry / WAWF report
                 "verifier_setup_per_lot": 25.0},
        "min_lot_charge": 75.0,
        "lead_days": 7,
        "pieces_per_day": 200,
    }


def harness_catalog(cfg: dict) -> dict:
    h = cfg["harness"]
    specs = sorted(set(WIRE_SPECS) | set(h["wire_per_ft"]))
    return {"wire_specs": [{"id": s, "name": WIRE_SPECS.get(s, s)} for s in specs], "gauges": GAUGES,
            "terminations": TERMINATIONS, "workmanship": WORKMANSHIP_CLASSES, "workmanship_source": WORKMANSHIP_SOURCE,
            "contact_sizes": {k: list(v) for k, v in CONTACT_SIZE_AWG.items()}, "contact_size_source": CONTACT_SIZE_SOURCE,
            "bom_kinds": ["connector", "contact", "backshell", "accessory", "other"], "config": copy.deepcopy(h)}


def panel_catalog(cfg: dict) -> dict:
    return {"device_types": PANEL_DEVICE_TYPES, "length_priced": list(LENGTH_PRICED), "config": copy.deepcopy(cfg["panel"])}


def labels_catalog(cfg: dict) -> dict:
    return {"types": {k: v.get("label", k) for k, v in cfg["labels"]["materials"].items()}, "config": copy.deepcopy(cfg["labels"])}
