"""Box build defaults: component types and the editable shop-rate config "box_build" (all placeholders).

Kept apart from app/box_build.py so app/pricing.py can load the defaults without importing the pricing model."""
from __future__ import annotations

PLACEHOLDER = "Every price, minute and rate here is a placeholder. Replace them with your own numbers and real supplier quotes."

# type -> label, default termination method. Prices, minutes, terminations and mates per type live in config.
COMPONENT_TYPES: dict[str, tuple[str, str]] = {
    "toggle_switch": ("Toggle switch", "solder"),
    "rocker_switch": ("Rocker switch", "quick_connect"),
    "pushbutton": ("Pushbutton", "solder"),
    "rotary_switch": ("Rotary switch", "solder"),
    "keyswitch": ("Key switch", "solder"),
    "circular_connector": ("Circular connector (MIL-DTL-38999, MIL-DTL-26482, MS)", "crimp"),
    "dsub_connector": ("D-sub or Micro-D connector", "crimp"),
    "panel_port": ("Panel feed-through (USB, Ethernet, BNC, SMA)", "none"),
    "power_entry": ("Power entry module or IEC inlet", "quick_connect"),
    "terminal_block": ("Terminal block or terminal strip", "screw"),
    "led_indicator": ("LED indicator", "solder"),
    "panel_lamp": ("Panel lamp or indicator light", "quick_connect"),
    "display": ("Display (LCD, TFT, OLED, touchscreen)", "none"),
    "knob": ("Knob", "none"),
    "potentiometer": ("Potentiometer or encoder", "solder"),
    "fuse_holder": ("Fuse holder", "solder"),
    "circuit_breaker": ("Circuit breaker", "screw"),
    "fan": ("Fan (with guard or filter)", "crimp"),
    "power_supply": ("Power supply or DC-DC converter", "screw"),
    "relay": ("Relay", "quick_connect"),
    "meter": ("Panel meter", "screw"),
    "buzzer": ("Buzzer or speaker", "solder"),
    "battery": ("Battery or battery holder", "solder"),
    "sensor": ("Sensor", "crimp"),
    "computer_module": ("Single-board computer or module", "none"),
    "cable_assembly": ("Purchased cable assembly", "none"),
    "heatsink": ("Heatsink", "none"),
    "hardware": ("Hardware (screws, nuts, standoffs, spacers)", "none"),
    "other": ("Other", "none"),
}
TERMINATION_METHODS = ("solder", "crimp", "screw", "quick_connect", "none")


def default_config() -> dict:
    comp = {  # placeholder price, mount minutes, wire terminations and cable mates per item
        "toggle_switch": (12.0, 4.0, 3, 0), "rocker_switch": (4.0, 3.0, 2, 0), "pushbutton": (8.0, 4.0, 2, 0),
        "rotary_switch": (15.0, 6.0, 6, 0), "keyswitch": (25.0, 6.0, 2, 0), "circular_connector": (60.0, 10.0, 8, 0),
        "dsub_connector": (6.0, 6.0, 9, 0), "panel_port": (15.0, 5.0, 0, 2), "power_entry": (20.0, 6.0, 3, 0),
        "terminal_block": (3.0, 2.0, 2, 0), "led_indicator": (2.0, 3.0, 2, 0), "panel_lamp": (8.0, 4.0, 2, 0),
        "display": (60.0, 20.0, 0, 2), "knob": (3.0, 1.0, 0, 0), "potentiometer": (5.0, 4.0, 3, 0),
        "fuse_holder": (4.0, 4.0, 2, 0), "circuit_breaker": (25.0, 5.0, 2, 0), "fan": (15.0, 8.0, 2, 0),
        "power_supply": (60.0, 15.0, 5, 0), "relay": (10.0, 4.0, 5, 0), "meter": (40.0, 10.0, 4, 0),
        "buzzer": (4.0, 3.0, 2, 0), "battery": (5.0, 4.0, 2, 0), "sensor": (30.0, 8.0, 3, 0),
        "computer_module": (75.0, 10.0, 0, 3), "cable_assembly": (10.0, 2.0, 0, 2), "heatsink": (10.0, 8.0, 0, 0),
        "hardware": (0.15, 0.5, 0, 0), "other": (10.0, 5.0, 0, 0),
    }
    return {
        "note": PLACEHOLDER,
        "labor_rate": 60.0,  # integration and wiring $/h
        "test_rate": 75.0,  # test and inspection $/h
        "engineering_rate": 95.0,  # work instructions, test procedures, fixture design $/h
        "material_burden": 0.08,  # purchasing, receiving and handling on bought material
        "class3_labor_factor": 1.25,  # IPC Class 3 workmanship on integration and wiring labor (your assumption)
        "enclosures": {  # catalog boxes: base + $/cubic inch of outside volume, supplier lead days
            "diecast_aluminum": {"label": "Die-cast aluminum box", "base": 20.0, "per_in3": 0.08, "lead_days": 10},
            "extruded_aluminum": {"label": "Extruded aluminum enclosure", "base": 25.0, "per_in3": 0.06, "lead_days": 10},
            "sheet_steel": {"label": "Sheet steel enclosure (NEMA 1/12)", "base": 60.0, "per_in3": 0.05, "lead_days": 14},
            "stainless_nema4x": {"label": "Stainless steel NEMA 4X enclosure", "base": 150.0, "per_in3": 0.12, "lead_days": 21},
            "polycarbonate": {"label": "Polycarbonate NEMA 4X enclosure", "base": 30.0, "per_in3": 0.05, "lead_days": 10},
            "abs_plastic": {"label": "ABS plastic project box", "base": 8.0, "per_in3": 0.02, "lead_days": 7},
            "rack_chassis": {"label": "19 in rack-mount chassis", "base": 120.0, "per_in3": 0.03, "lead_days": 21},
            "rugged_case": {"label": "Rugged transit case with panel", "base": 80.0, "per_in3": 0.04, "lead_days": 21},
        },
        "enclosure_mods": {
            "setup_minutes_per_lot": 60.0,  # layout, program or template for the cutouts
            "round_hole_minutes": 4.0, "rect_cutout_minutes": 20.0, "connector_cutout_minutes": 12.0,
            "display_window_minutes": 35.0, "vent_pattern_minutes": 30.0,
            "pem_minutes": 0.5, "pem_each": 0.30, "gasket_each": 8.0, "gasket_minutes": 10.0,
            "emi_gasket_each": 15.0, "emi_gasket_minutes": 15.0, "assembly_fasteners": 8.0,
        },
        "finishes": {  # outside service per enclosure with a lot minimum, plus lead days
            "powder_coat": {"label": "Powder coat", "per_unit": 35.0, "lot_min": 150.0, "lead_days": 5},
            "paint": {"label": "Wet paint (customer color)", "per_unit": 45.0, "lot_min": 200.0, "lead_days": 7},
            "anodize": {"label": "Anodize (MIL-PRF-8625)", "per_unit": 25.0, "lot_min": 125.0, "lead_days": 5},
            "chem_film": {"label": "Chem film (MIL-DTL-5541)", "per_unit": 12.0, "lot_min": 100.0, "lead_days": 4},
        },
        "silkscreen": {"setup_per_color_side": 75.0, "per_color_side": 2.50, "minutes_per_color_side": 2.0},
        "pcb_fab": {
            "per_sqin": {"1": 0.10, "2": 0.15, "4": 0.35, "6": 0.60, "8": 0.90, "10": 1.30, "12": 1.70, "14": 2.10, "16": 2.50},
            "tooling_per_lot": {"1": 50.0, "2": 75.0, "4": 150.0, "6": 250.0, "8": 350.0, "10": 450.0, "12": 550.0, "14": 650.0, "16": 750.0},
            "panel_waste": 0.15,  # panel rails and spacing
            "etest_each": 0.50,
            "lot_min": 100.0,
            "lead_days": 10, "class3_lead_days": 5,
            "finish_factor": {"HASL lead-free": 1.0, "HASL tin-lead": 1.0, "ENIG": 1.15, "immersion silver": 1.10, "immersion tin": 1.10, "OSP": 0.95, "hard gold": 1.40},
            "copper_factor": {"1": 1.0, "2": 1.25, "3": 1.5, "4": 1.8},
            "class3_factor": 1.35, "impedance_factor": 1.10, "impedance_nre": 100.0, "via_in_pad_factor": 1.25,
            "blind_buried_factor": 1.60, "nonstandard_thickness_factor": 1.10,
        },
        "pcba": {
            "setup_per_side": 150.0,  # line setup and programming per side per lot
            "feeder_per_unique": 2.0,  # feeder setup per unique SMT part per lot
            "stencil_per_side": 60.0,
            "smt_per_placement": 0.03, "fine_pitch_each": 0.15, "bga_each": 1.50, "xray_per_board": 3.0, "aoi_per_board": 0.50,
            "tht_minutes_per_joint": 0.10, "tht_minutes_per_part": 0.25, "hand_rate": 55.0,
            "class3_factor": 1.30,  # assembly cost at IPC-A-610 / J-STD-001 Class 3
            "conformal_minutes": 5.0, "conformal_mask_minutes": 1.5, "conformal_per_sqin": 0.02,
            "flying_probe_nre": 300.0, "flying_probe_each": 3.0,
            "program_setup_minutes": 30.0, "test_setup_minutes": 30.0,
            "inspection_minutes": 3.0,
            "attrition": 0.02,  # extra parts bought for setup loss
            "placeholder_per_smt": 0.10, "placeholder_per_tht": 0.50,  # parts cost when there is no BOM
            "lead_days": 10, "mount_minutes": 5.0,
        },
        "components": {k: {"label": COMPONENT_TYPES[k][0], "price": v[0], "minutes": v[1], "terminations": v[2], "mates": v[3]} for k, v in comp.items()},
        "termination_minutes": {"solder": 1.5, "crimp": 1.0, "screw": 1.0, "quick_connect": 0.6},
        "wiring": {"minutes_per_wire": 3.0, "dress_minutes_per_wire": 0.5, "wire_per_ft": 0.25, "default_length_in": 12.0,
                   "mate_minutes": 0.5, "tie_each": 0.06, "ties_per_wire": 0.5, "marker_each": 0.25, "marker_minutes": 0.25},
        "integration": {"fastener_minutes": 0.5, "fastener_each": 0.15, "ground_point_minutes": 4.0, "ground_point_each": 1.50,
                        "peripheral_install_minutes": 10.0, "peripheral_kit_minutes": 2.0, "final_inspection_minutes": 15.0,
                        "serialize_minutes": 3.0, "serial_label_each": 1.0, "esd_per_unit": 1.0, "kitting_hours_per_lot": 2.0,
                        "techs": 1.0, "hours_per_day": 7.0},
        "test": {"firmware_setup_minutes": 30.0, "functional_setup_minutes": 30.0, "hipot_minutes": 5.0, "ground_bond_minutes": 3.0,
                 "safety_setup_minutes": 20.0, "burn_in_rack_per_hour": 0.50, "burn_in_handling_minutes": 10.0,
                 "ess_thermal_per_unit": 150.0, "ess_vibration_per_unit": 200.0, "ess_lot_setup": 500.0, "ess_days": 5.0},
        "lab_tests": {  # outside lab, per lot; wide ranges in practice, so get a lab quote
            "mil_std_461": {"label": "MIL-STD-461 EMI/EMC testing", "per_lot": 15000.0, "days": 30.0},
            "mil_std_810": {"label": "MIL-STD-810 environmental testing", "per_lot": 12000.0, "days": 30.0},
            "mil_std_167": {"label": "MIL-STD-167-1 shipboard vibration", "per_lot": 8000.0, "days": 30.0},
            "mil_s_901": {"label": "MIL-DTL-901 shipboard shock", "per_lot": 20000.0, "days": 45.0},
        },
        "nre": {"work_instructions_hours": 8.0, "test_procedure_hours": 8.0, "first_article_hours": 6.0, "drawing_package_hours": 8.0},
        "component_lead_days": 21,
        "freight_per_lot": 95.0,
        "crate_per_unit": 45.0,
    }
