"""Built-in catalog of standards, specifications and data items a small defense supplier meets.

Scope: custom training equipment, electrical and electronic assemblies, cable harnesses, machined,
welded, sheet metal and 3D printed parts for the Navy and DLA. This is a starting set, not all of
ASSIST. Any other document ID still works through lookup, and a full exported list can be imported.

Each entry: id (base document ID with no revision letter), title, category, summary (when a supplier
meets it), publisher, free. Revision letters are deliberately not stored here: always use the
revision the contract cites.

Status notes (cancelled / superseded) appear only where they were checked against the cancellation
notice (EverySpec copies of the DoD notices, October 2026).
"""
from __future__ import annotations

DOD = "DoD (free on ASSIST)"
NAVSEA_TP = "NAVSEA technical publication (request through the contracting officer)"

# publisher -> is the document free to obtain
PUBLISHER_FREE = {
    DOD: True,
    NAVSEA_TP: True,
    "NIST (free)": True,
    "eCFR (free)": True,
    "acquisition.gov (free)": True,
    "DoD CIO (free)": True,
    "S1000D (free download)": True,
    "ADL Initiative (free)": True,
    "IPPC (free)": True,
}

CATEGORIES = [
    "Drawings, TDP and configuration management",
    "Electrical power and EMI/EMC",
    "Connectors, wire and cable",
    "Electronic assemblies, PCBs and soldering",
    "Components",
    "Shipboard equipment (Navy)",
    "Environmental and reliability testing",
    "Mechanical, fasteners and threads",
    "Materials (metals and plastics)",
    "Finishes, plating and coatings",
    "Welding, brazing and NDT",
    "Quality, inspection and counterfeit prevention",
    "Packaging, marking and IUID",
    "Technical manuals, training data and human factors",
    "Safety and electrical codes",
    "Additive manufacturing",
    "Data item descriptions (DIDs)",
    "Cybersecurity",
]

_RAW: list[tuple[str, str, list[tuple[str, str, str]]]] = []


def _g(category: str, publisher: str, rows: list[tuple[str, str, str]]) -> None:
    assert category in CATEGORIES, category
    _RAW.append((category, publisher, rows))


# ------------------------------------------------------------------ Drawings, TDP and CM
C = "Drawings, TDP and configuration management"
_g(C, DOD, [
    ("MIL-STD-31000", "Technical Data Packages", "Cited when you must deliver drawings, 3D models and lists as a TDP; the TDP option selection worksheet in the contract says exactly which elements are due."),
    ("MIL-STD-100", "Engineering Drawing Practices", "Applies when you prepare drawings for delivery to DoD; it adds DoD rules on top of ASME Y14.100."),
    ("MIL-HDBK-61", "Configuration Management Guidance", "Guidance you meet when the contract requires configuration management, baselines, engineering change proposals or status accounting."),
    ("MIL-STD-961", "Defense and Program-Unique Specifications Format and Content", "Applies when the contract asks you to write a performance or detail specification for a delivered item."),
    ("MIL-STD-962", "Defense Standards Format and Content", "Format rules for defense standards; useful mainly when you write or revise a program standard for the customer."),
    ("MIL-STD-881", "Work Breakdown Structures for Defense Materiel Items", "Cited when the contract requires a contract work breakdown structure for cost and schedule reporting."),
])
_g(C, "ASME", [
    ("ASME Y14.5", "Dimensioning and Tolerancing", "The GD&T rules behind every dimension and feature control frame on a DoD drawing; work to the edition the drawing or contract names."),
    ("ASME Y14.100", "Engineering Drawing Practices", "Defines what a complete engineering drawing must contain; MIL-STD-100 builds on it."),
    ("ASME Y14.24", "Types and Applications of Engineering Drawings", "Defines detail, assembly, altered item, source control and specification control drawings; tells you what kind of drawing to deliver."),
    ("ASME Y14.34", "Associated Lists", "Rules for parts lists, data lists and index lists that go with a drawing package."),
    ("ASME Y14.35", "Revision of Engineering Drawings and Associated Documents", "Rules for revision letters, revision blocks and change history on drawings you deliver or modify."),
    ("ASME Y14.41", "Digital Product Definition Data Practices", "Applies when the TDP is model based (3D models with PMI) instead of, or in addition to, 2D drawings."),
    ("ASME Y14.38", "Abbreviations and Acronyms for Use on Drawings and Related Documents", "The approved abbreviation list for notes and title blocks on drawings."),
    ("ASME Y14.1", "Decimal Inch Drawing Sheet Size and Format", "Sheet sizes, title blocks and zones for inch drawings."),
    ("ASME Y14.2", "Line Conventions and Lettering", "Line types, weights and lettering used on engineering drawings."),
    ("ASME Y14.3", "Orthographic and Pictorial Views", "How views, sections and auxiliary views are laid out on a drawing."),
    ("ASME Y14.6", "Screw Thread Representation", "How threads are drawn and called out on drawings."),
    ("ASME Y14.8", "Castings, Forgings, and Molded Parts", "Drawing practices for cast, forged and molded parts, including draft and parting lines."),
    ("ASME Y14.31", "Undimensioned Drawings", "Applies when a drawing or pattern is used at true scale without dimensions, such as some sheet metal flat patterns or artwork."),
    ("ASME Y14.36", "Surface Texture Symbols", "How surface finish requirements are shown on drawings; read with ASME B46.1."),
    ("ASME Y14.37", "Product Definition for Composite Parts", "Drawing practices for composite parts, including ply tables."),
    ("ASME Y14.43", "Dimensioning and Tolerancing Principles for Gages and Fixtures", "Applies when you design or deliver inspection gages and fixtures."),
    ("ASME Y14.44", "Reference Designations for Electrical and Electronics Parts and Equipment", "Rules for reference designators (R1, J2, A3) on schematics, harness drawings and assemblies."),
    ("ASME Y14.47", "Model Organization Practices", "How 3D CAD models are organized when the model is the deliverable."),
])
_g(C, "IEEE", [
    ("IEEE 315", "Graphic Symbols for Electrical and Electronics Diagrams (Including Reference Designation Letters)", "The symbol set expected on schematics and wiring diagrams you deliver."),
])
_g(C, "ISA", [
    ("ANSI/ISA-5.1", "Instrumentation Symbols and Identification", "Symbols and tag numbering for P&IDs and instrumentation drawings."),
])
_g(C, "SAE", [
    ("EIA-649", "Configuration Management Standard", "The industry configuration management standard DoD uses with MIL-HDBK-61; often cited in the SOW."),
    ("EIA-649-1", "Configuration Management Requirements for Defense Contracts", "Contract-ready CM requirements a buyer can put on a defense contract; tailored by the SOW."),
    ("GEIA-STD-0007", "Logistics Product Data", "Applies when the contract requires logistics product data (provisioning, maintenance tasks) in a standard format."),
])
_g(C, "ISO", [
    ("ISO 10007", "Quality management: Guidelines for configuration management", "General configuration management guidance often referenced by ISO 9001 shops."),
    ("ISO 10303-242", "Product data representation and exchange, Part 242: Managed model-based 3D engineering (STEP AP242)", "The STEP format many buyers ask for when CAD models are delivered in a neutral format."),
    ("ISO 1101", "Geometrical product specifications (GPS): Geometrical tolerancing", "ISO counterpart to ASME Y14.5; met when a drawing is toleranced to ISO GPS instead of ASME."),
])

# ------------------------------------------------------------------ Electrical power and EMI/EMC
C = "Electrical power and EMI/EMC"
_g(C, DOD, [
    ("MIL-STD-461", "Requirements for the Control of Electromagnetic Interference Characteristics of Subsystems and Equipment", "Cited when your electronic equipment must pass conducted and radiated emissions and susceptibility tests (CE102, RE102, CS114 and so on)."),
    ("MIL-STD-464", "Electromagnetic Environmental Effects Requirements for Systems", "System-level E3 requirements; a supplier usually meets it through the MIL-STD-461 tailoring the prime flows down."),
    ("MIL-HDBK-419", "Grounding, Bonding, and Shielding for Electronic Equipments and Facilities", "Design guidance for grounding and bonding of electronic equipment and facilities."),
    ("MIL-HDBK-1857", "Grounding, Bonding and Shielding Design Practices", "Design practices for bonding and shielding in equipment and cable harnesses."),
    ("MIL-STD-188-124", "Grounding, Bonding and Shielding for Common Long Haul/Tactical Communication Systems", "Applies to grounding and shielding of communications equipment and facilities."),
    ("MIL-STD-220", "Method of Insertion Loss Measurement", "Test method for filter insertion loss, met when you supply or test EMI filters."),
    ("MIL-STD-704", "Aircraft Electric Power Characteristics", "Defines the aircraft power your equipment must run on; cited for airborne or aircraft support equipment."),
    ("MIL-STD-1275", "Characteristics of 28 Volt DC Input Power to Utilization Equipment in Military Vehicles", "Applies when your equipment runs on military ground vehicle 28 VDC power."),
    ("MIL-HDBK-235", "Military Operational Electromagnetic Environment Profiles", "Defines electromagnetic environments equipment may see in service; used when tailoring EMI requirements."),
    ("MIL-HDBK-237", "Electromagnetic Environmental Effects and Spectrum Supportability Guidance for the Acquisition Process", "Program-level E3 and spectrum guidance; read it when a transmitter or receiver is part of the delivery."),
])
_g(C, "IEC", [
    ("IEC 61000-4-2", "Electromagnetic compatibility (EMC), Part 4-2: Electrostatic discharge immunity test", "Commercial ESD immunity test often required for COTS-based training equipment."),
    ("IEC 61000-4-3", "Electromagnetic compatibility (EMC), Part 4-3: Radiated, radio-frequency, electromagnetic field immunity test", "Commercial radiated immunity test for equipment built to commercial EMC requirements."),
    ("IEC 61000-4-4", "Electromagnetic compatibility (EMC), Part 4-4: Electrical fast transient/burst immunity test", "Commercial fast transient immunity test on power and signal ports."),
    ("IEC 61000-4-5", "Electromagnetic compatibility (EMC), Part 4-5: Surge immunity test", "Commercial surge immunity test on power and signal ports."),
    ("CISPR 11", "Industrial, scientific and medical equipment: Radio-frequency disturbance characteristics, limits and methods of measurement", "Commercial emissions limits for industrial equipment such as control panels and test benches."),
    ("CISPR 32", "Electromagnetic compatibility of multimedia equipment: Emission requirements", "Commercial emissions limits for computer, display and audio-visual equipment."),
])
_g(C, "IEEE", [
    ("ANSI C63.4", "Methods of Measurement of Radio-Noise Emissions from Low-Voltage Electrical and Electronic Equipment in the Range of 9 kHz to 40 GHz", "The test method behind FCC Part 15 emissions testing."),
    ("IEEE 519", "Standard for Harmonic Control in Electric Power Systems", "Cited when equipment with drives or rectifiers must keep harmonic distortion on facility power within limits."),
])
_g(C, "eCFR (free)", [
    ("47 CFR Part 15", "Radio Frequency Devices (FCC Part 15)", "Applies to commercial digital electronics and intentional radiators sold in the US; often required for COTS-based trainers."),
])

# ------------------------------------------------------------------ Connectors, wire and cable
C = "Connectors, wire and cable"
_g(C, DOD, [
    ("MIL-DTL-38999", "Connectors, Electrical, Circular, Miniature, High Density, Quick Disconnect, Environment Resistant, Removable Crimp Contacts", "The most common military circular connector family (D38999); met whenever a harness drawing calls D38999 parts."),
    ("MIL-DTL-5015", "Connectors, Electrical, Circular Threaded, AN Type", "Older threaded circular connectors (MS3100 and similar) still common on ground and shipboard equipment."),
    ("MIL-DTL-26482", "Connectors, Electrical, (Circular, Miniature, Quick Disconnect, Environment Resisting), Receptacles and Plugs", "Bayonet circular connectors (MS3470 and similar) used on many harnesses."),
    ("MIL-DTL-83723", "Connectors, Electrical, (Circular, Environment Resisting), Receptacles and Plugs", "Environment resisting circular connectors used in aircraft and support equipment."),
    ("MIL-DTL-24308", "Connectors, Electric, Rectangular, Nonenvironmental, Miniature, Polarized Shell, Rack and Panel", "Military D-subminiature connectors (M24308) used on electronic equipment."),
    ("MIL-DTL-83513", "Connectors, Electrical, Rectangular, Microminiature, Polarized Shell", "Micro-D connectors (M83513) for dense, lightweight interconnects."),
    ("MIL-DTL-55302", "Connectors, Printed Circuit Subassembly and Accessories", "Board-to-board and card edge connectors used on military circuit card assemblies."),
    ("MIL-PRF-39012", "Connectors, Coaxial, Radio Frequency", "RF coaxial connectors (M39012) for RF cable assemblies."),
    ("MIL-DTL-17", "Cables, Radio Frequency, Flexible and Semirigid", "Military RF coaxial cable (M17) used in RF cable assemblies."),
    ("MIL-DTL-28840", "Connectors, Electrical, Circular, Threaded, High Density, High Shock Shipboard", "High shock circular connectors for Navy shipboard electronics."),
    ("MIL-DTL-55116", "Connectors, Miniature Audio, Five-Pin and Six-Pin", "Audio connectors used on military radio handsets and headsets."),
    ("MIL-DTL-24643", "Cables, Electric, Low Smoke Halogen-Free, for Shipboard Use", "Low smoke shipboard cable; met when you supply or install cable on Navy ships."),
    ("MIL-DTL-24640", "Cables, Electric, Lightweight, Low Smoke, for Shipboard Use", "Lightweight low smoke shipboard cable for Navy installations."),
    ("MIL-DTL-915", "Cable, Electrical, for Shipboard Use", "General shipboard cable specification for special purpose cables."),
    ("MIL-DTL-27500", "Cable, Power, Electrical and Cable Special Purpose, Electrical Shielded and Unshielded", "Multi-conductor shielded and jacketed cable (M27500) used in harnesses."),
    ("MIL-W-22759", "Wire, Electrical, Fluoropolymer-Insulated, Copper or Copper Alloy", "Legacy ID still printed on many harness drawings; the document is now SAE AS22759, so buy M22759 wire to the AS22759 slash sheet."),
    ("MIL-DTL-16878", "Wire, Electrical, Insulated, General Specification for", "Hookup wire for internal wiring of electronic equipment (M16878)."),
    ("MIL-DTL-81381", "Wire, Electric, Polyimide-Insulated, Copper or Copper Alloy", "Polyimide insulated wire (M81381) found on older aircraft and equipment drawings."),
    ("MIL-DTL-76", "Wire and Cable, Hookup, Electrical, Insulated", "General hookup wire and cable specification."),
    ("MIL-STD-681", "Identification Coding and Application of Hookup and Lead Wire", "Wire color coding and marking rules for hookup and lead wire in equipment."),
    ("MIL-DTL-22520", "Crimping Tools, Wire Termination, General Specification for", "Defines M22520 crimp tools and locators; met when your crimp process must use qualified tools (SAE also publishes AS22520 with the same title)."),
    ("MIL-HDBK-522", "Guidelines for Inspection of Aircraft Electrical Wiring Interconnect Systems", "Inspection guidance for aircraft wiring; useful for harness inspection criteria."),
    ("A-A-52081", "Tape, Lacing and Tying, Polyester", "Lacing tape used to bundle harnesses when the drawing calls out lacing instead of ties."),
])
_g(C, "SAE", [
    ("AS22759", "Wire, Electrical, Fluoropolymer-Insulated, Copper or Copper Alloy", "Current home of the M22759 wire family (formerly MIL-W-22759); the slash sheet number sets insulation, plating and rating."),
    ("AS81044", "Wire, Electric, Crosslinked Polyalkene, Crosslinked Alkane-Imide Polymer, or Polyarylene Insulated, Copper or Copper Alloy", "M81044 wire family used in airframe and equipment wiring."),
    ("AS50881", "Wiring, Aerospace Vehicle", "Wiring installation rules (routing, clamping, bend radius, marking) often flowed to harness builders."),
    ("AMS-DTL-23053", "Insulation Sleeving, Electrical, Heat Shrinkable", "Heat shrink sleeving (M23053) called out on harness drawings."),
    ("AS7928", "Terminals, Lug: Splices, Conductor: Crimp Style, Copper", "Crimp lugs and splices (MS25036 and similar parts) used in harnesses."),
    ("AS81824", "Splice, Electric, Permanent, Crimp Style, Copper, Insulated, Environment Resistant", "Environment resistant crimp splices for wire repairs and harnesses."),
    ("AS39029", "Contacts, Electrical Connector, General Specification for", "M39029 crimp contacts used in D38999 and other military connectors."),
    ("AS85049", "Connector Accessories, Electrical, General Specification for", "Backshells, strain reliefs and other connector accessories (M85049)."),
    ("AS23190", "Straps, Clamps, and Mounting Hardware, Plastic and Metal for Cable Harness Tying and Support", "Cable ties and clamps used on harnesses."),
])
_g(C, "IPC", [
    ("IPC/WHMA-A-620", "Requirements and Acceptance for Cable and Wire Harness Assemblies", "The workmanship standard for cable and harness builds; class 3 is common on military work."),
    ("IPC-D-620", "Design and Critical Process Requirements for Cable and Wiring Harnesses", "Design rules for harnesses; pairs with IPC/WHMA-A-620 for acceptance."),
])
_g(C, "ECIA", [
    ("EIA-364", "Electrical Connector/Socket Test Procedures Including Environmental Classifications", "Connector test methods (durability, contact resistance, mating force) referenced by connector specs."),
])
_g(C, "UL", [
    ("UL 758", "Appliance Wiring Material", "Covers UL style (AWM) wire used inside commercial equipment and panels."),
    ("UL 1977", "Component Connectors for Use in Data, Signal, Control and Power Applications", "Applies to connectors used inside UL listed or recognized equipment."),
    ("UL 486A-486B", "Wire Connectors", "Lugs and wire connectors used in panels built to UL or NEC requirements."),
])
_g(C, "TIA", [
    ("TIA-568", "Commercial Building Telecommunications Cabling Standard", "Network cabling requirements when you install or supply Ethernet cabling."),
])

# ------------------------------------------------------------------ Electronic assemblies, PCBs and soldering
C = "Electronic assemblies, PCBs and soldering"
_g(C, "IPC", [
    ("J-STD-001", "Requirements for Soldered Electrical and Electronic Assemblies", "The soldering process standard for circuit cards and harness terminations; class 3 and the space addendum appear on military work."),
    ("IPC-A-610", "Acceptability of Electronic Assemblies", "Visual acceptance criteria for circuit card assemblies; used for inspection and rework decisions."),
    ("IPC-A-600", "Acceptability of Printed Boards", "Acceptance criteria for bare printed boards from your fabricator."),
    ("IPC-6011", "Generic Performance Specification for Printed Boards", "General performance requirements that the IPC-601x sectional specs build on."),
    ("IPC-6012", "Qualification and Performance Specification for Rigid Printed Boards", "Fabrication requirements for rigid boards; put it and the class on your PCB fab notes."),
    ("IPC-6013", "Qualification and Performance Specification for Flexible/Rigid-Flexible Printed Boards", "Fabrication requirements for flex and rigid-flex boards."),
    ("IPC-6018", "Qualification and Performance Specification for High Frequency (Microwave) Printed Boards", "Fabrication requirements for RF and microwave boards."),
    ("IPC-2221", "Generic Standard on Printed Board Design", "Board design rules for spacing, conductor sizing and layout."),
    ("IPC-2222", "Sectional Design Standard for Rigid Organic Printed Boards", "Design rules specific to rigid boards."),
    ("IPC-2223", "Sectional Design Standard for Flexible/Rigid-Flexible Printed Boards", "Design rules specific to flex and rigid-flex boards."),
    ("IPC-2152", "Standard for Determining Current Carrying Capacity in Printed Board Design", "Trace width and temperature rise data for power traces."),
    ("IPC-7351", "Generic Requirements for Surface Mount Design and Land Pattern Standard", "Land pattern (footprint) rules for surface mount parts."),
    ("IPC-7711/7721", "Rework, Modification and Repair of Electronic Assemblies", "Approved rework and repair methods for circuit card assemblies."),
    ("IPC-CC-830", "Qualification and Performance of Electrical Insulating Compound for Printed Wiring Assemblies", "Conformal coating material qualification; the usual reference for coating materials."),
    ("IPC-HDBK-830", "Guidelines for Design, Selection and Application of Conformal Coatings", "How to select and apply conformal coating."),
    ("IPC-4101", "Specification for Base Materials for Rigid and Multilayer Printed Boards", "Laminate slash sheets you cite on fab drawings (for example FR-4 types)."),
    ("IPC-2581", "Generic Requirements for Printed Board Assembly Products Manufacturing Description Data and Transfer Methodology", "Neutral data format for sending board design data to fabricators."),
    ("IPC-1601", "Printed Board Handling and Storage Guidelines", "Handling, packaging and baking of bare boards before assembly."),
    ("IPC-TM-650", "Test Methods Manual", "The test methods referenced throughout IPC specifications."),
    ("IPC-7095", "Design and Assembly Process Implementation for BGAs", "Design and process guidance for ball grid array assemblies."),
    ("IPC-1752", "Materials Declaration Management Standard", "Format for declaring materials and substances in parts and assemblies."),
    ("IPC-1791", "Trusted Electronic Designer, Fabricator and Assembler Requirements", "Trusted supplier requirements for defense electronics; may be cited for sensitive programs."),
    ("J-STD-002", "Solderability Tests for Component Leads, Terminations, Lugs, Terminals and Wires", "Solderability testing of parts and wires."),
    ("J-STD-003", "Solderability Tests for Printed Boards", "Solderability testing of bare board finishes."),
    ("J-STD-004", "Requirements for Soldering Fluxes", "Flux classification (for example ROL0) used in J-STD-001 processes."),
    ("J-STD-005", "Requirements for Soldering Pastes", "Solder paste requirements for SMT assembly."),
    ("J-STD-006", "Requirements for Electronic Grade Solder Alloys and Fluxed and Non-Fluxed Solid Solders for Electronic Soldering Applications", "Solder alloy and wire requirements, such as Sn63Pb37."),
])
_g(C, "IPC/JEDEC", [
    ("J-STD-020", "Moisture/Reflow Sensitivity Classification for Nonhermetic Surface Mount Devices", "Moisture sensitivity levels (MSL) of plastic parts you reflow."),
    ("J-STD-033", "Handling, Packing, Shipping and Use of Moisture/Reflow Sensitive Surface Mount Devices", "Floor life, dry storage and bake rules for moisture sensitive parts."),
])
_g(C, DOD, [
    ("MIL-PRF-31032", "Printed Circuit Board/Printed Wiring Board, General Specification for", "Military qualified printed board specification; cited when boards must come from a QML source."),
    ("MIL-PRF-55110", "Printed Wiring Board, Rigid, General Specification for", "Older military rigid board specification still on many legacy drawings."),
    ("MIL-PRF-50884", "Printed Wiring Board, Flexible or Rigid-Flex, General Specification for", "Military flex and rigid-flex board specification on legacy drawings."),
    ("MIL-I-46058", "Insulating Compound, Electrical (for Coating Printed Circuit Assemblies)", "Conformal coating spec still printed on old drawings; it is inactive for new design (Notice 1), so new work usually cites IPC-CC-830."),
    ("MIL-STD-2000", "Standard Requirements for Soldered Electrical and Electronic Assemblies", "Older military soldering standard that still appears on legacy drawings; check whether the contract allows J-STD-001 instead."),
    ("MIL-STD-454", "Standard General Requirements for Electronic Equipment", "General design requirements for military electronic equipment, cited on older equipment specs."),
    ("MIL-HDBK-454", "General Guidelines for Electronic Equipment", "Design guidelines (parts, materials, workmanship) for military electronic equipment."),
    ("MIL-STD-1686", "Electrostatic Discharge Control Program for Protection of Electrical and Electronic Parts, Assemblies and Equipment", "Military ESD control program requirements; many buyers now accept ANSI/ESD S20.20."),
    ("MIL-HDBK-263", "Electrostatic Discharge Control Handbook for Protection of Electrical and Electronic Parts, Assemblies and Equipment", "ESD handbook that supports MIL-STD-1686."),
])
_g(C, "ANSI/ESD (ESD Association)", [
    ("ANSI/ESD S20.20", "Protection of Electrical and Electronic Parts, Assemblies and Equipment (Excluding Electrically Initiated Explosive Devices)", "The ESD control program most buyers expect for electronics assembly and handling."),
    ("ANSI/ESD S541", "Packaging Materials for ESD Sensitive Items", "ESD packaging requirements for shipping sensitive parts and assemblies."),
    ("ANSI/ESD S8.1", "Symbols: ESD Awareness", "ESD warning symbols for labels and packaging."),
    ("ESD TR20.20", "ESD Handbook", "Implementation guidance for an S20.20 ESD program."),
])
_g(C, "SAE", [
    ("GEIA-STD-0005-1", "Performance Standard for Aerospace and High Performance Electronic Systems Containing Lead-free Solder", "Applies when lead-free parts or solder are used in defense electronics; requires a lead-free control plan."),
    ("GEIA-STD-0005-2", "Standard for Mitigating the Effects of Tin Whiskers in Aerospace and High Performance Electronic Systems", "Tin whisker mitigation requirements for pure tin finishes."),
])
_g(C, "UL", [
    ("UL 796", "Printed Wiring Boards", "UL recognition of bare boards used in UL listed equipment."),
])

# ------------------------------------------------------------------ Components
C = "Components"
_g(C, DOD, [
    ("MIL-PRF-38534", "Hybrid Microcircuits, General Specification for", "Qualification requirements for hybrid microcircuits from QML sources."),
    ("MIL-PRF-38535", "Integrated Circuits (Microcircuits) Manufacturing, General Specification for", "Qualified microcircuits (QML); met when a parts list calls SMD or QML ICs."),
    ("MIL-PRF-19500", "Semiconductor Devices, General Specification for", "Military qualified diodes and transistors (JAN, JANTX, JANTXV)."),
    ("MIL-STD-883", "Test Method Standard, Microcircuits", "Microcircuit test methods referenced by MIL-PRF-38535 and screening requirements."),
    ("MIL-STD-750", "Test Methods for Semiconductor Devices", "Semiconductor test methods referenced by MIL-PRF-19500."),
    ("MIL-STD-202", "Test Method Standard: Electronic and Electrical Component Parts", "Environmental and electrical test methods for passive components."),
    ("MIL-STD-1285", "Marking of Electrical and Electronic Parts", "How military parts are marked; useful when checking incoming parts."),
    ("MIL-STD-3018", "Parts Management", "Cited when the contract requires a parts management program or plan."),
    ("MIL-HDBK-512", "Parts Management", "Guidance for setting up a parts management program under MIL-STD-3018."),
    ("MIL-STD-11991", "General Standard for Parts, Materials, and Processes", "Army parts, materials and processes requirements, including obsolescence and approval of nonstandard parts."),
    ("MIL-PRF-55342", "Resistors, Chip, Fixed, Film, Nonestablished Reliability, Established Reliability, and Space Level", "Military chip resistors (RM and M55342 part numbers)."),
    ("MIL-PRF-55681", "Capacitors, Chip, Multiple Layer, Fixed, Ceramic Dielectric, Established Reliability and Nonestablished Reliability", "Military ceramic chip capacitors (CDR types)."),
    ("MIL-PRF-55365", "Capacitors, Fixed, Electrolytic (Tantalum), Chip, Nonestablished Reliability, Established Reliability", "Military tantalum chip capacitors (CWR types)."),
    ("MIL-PRF-39003", "Capacitors, Fixed, Electrolytic (Solid Electrolyte), Tantalum, Established Reliability", "Leaded solid tantalum capacitors (CSR types)."),
    ("MIL-PRF-123", "Capacitors, Fixed, Ceramic Dielectric (Temperature Stable and General Purpose), High Reliability", "High reliability ceramic capacitors (CKS types)."),
    ("MIL-PRF-39014", "Capacitors, Fixed, Ceramic Dielectric (General Purpose), Established Reliability and Nonestablished Reliability", "Leaded ceramic capacitors (CKR types)."),
    ("MIL-PRF-39007", "Resistors, Fixed, Wire-Wound (Power Type), Nonestablished Reliability, Established Reliability, and Space Level", "Power wirewound resistors (RWR types)."),
    ("MIL-PRF-55182", "Resistors, Fixed, Film, Nonestablished Reliability, Established Reliability, and Space Level", "Precision film resistors (RNC, RNR types)."),
    ("MIL-PRF-83401", "Resistor Networks, Fixed, Film and Capacitor-Resistor Networks", "Military resistor networks."),
    ("MIL-PRF-39016", "Relays, Electromagnetic, Established Reliability", "Established reliability relays (M39016)."),
    ("MIL-PRF-6106", "Relays, Electromagnetic", "General military electromagnetic relays."),
    ("MIL-PRF-83536", "Relays, Electromagnetic, Established Reliability, 25 Amperes and Below", "Military power relays up to 25 A (M83536)."),
    ("MIL-PRF-28750", "Relays, Solid State", "Military solid state relays."),
    ("MIL-DTL-3950", "Switches, Toggle, Environmentally Sealed", "Sealed toggle switches (MS24524 and similar) for panels."),
    ("MIL-DTL-22885", "Switches, Push Button, Illuminated", "Illuminated push button switches for control panels."),
    ("MIL-PRF-27", "Transformers and Inductors (Audio, Power, and High-Power Pulse)", "Military transformers and inductors; met when you build or buy magnetics to M27 slash sheets."),
    ("MIL-PRF-23419", "Fuses, Instrument Type", "Military instrument fuses (FM types)."),
    ("MIL-PRF-3098", "Crystal Units, Quartz", "Military quartz crystals."),
    ("MIL-PRF-55310", "Oscillators, Crystal Controlled", "Military crystal oscillators."),
])

# ------------------------------------------------------------------ Shipboard equipment (Navy)
C = "Shipboard equipment (Navy)"
_g(C, DOD, [
    ("MIL-STD-167-1", "Mechanical Vibrations of Shipboard Equipment (Type I: Environmental and Type II: Internally Excited)", "Vibration test that shipboard equipment must pass before installation."),
    ("MIL-STD-167-2", "Mechanical Vibrations of Shipboard Equipment (Reciprocating Machinery and Propulsion System and Shafting) Types III, IV, and V", "Vibration requirements for shipboard machinery and propulsion."),
    ("MIL-DTL-901", "Shock Tests, H.I. (High-Impact) Shipboard Machinery, Equipment, and Systems, Requirements for", "High impact shock qualification for equipment installed on Navy ships (grade A or B)."),
    ("MIL-STD-740-1", "Airborne Sound Measurements and Acceptance Criteria of Shipboard Equipment", "Airborne noise test and limits for shipboard equipment."),
    ("MIL-STD-740-2", "Structureborne Vibratory Acceleration Measurements and Acceptance Criteria of Shipboard Equipment", "Structureborne noise test and limits for shipboard equipment."),
    ("MIL-STD-1399-300", "Interface Standard for Shipboard Systems, Section 300: Electric Power, Alternating Current", "Defines ship AC power your equipment must accept, including voltage and frequency tolerances and transients."),
    ("MIL-STD-2003", "Electric Plant Installation Standard Methods for Surface Ships and Submarines", "Standard methods for installing cable, equipment and penetrations aboard ship."),
    ("MIL-STD-2042", "Fiber Optic Cable Topology Installation Standard Methods for Naval Ships", "Standard methods for installing shipboard fiber optic cable plants."),
    ("MIL-STD-1310", "Shipboard Bonding, Grounding, and Other Techniques for Electromagnetic Compatibility, Electromagnetic Pulse (EMP) Mitigation, and Safety", "Grounding and bonding rules for equipment installed on Navy ships."),
    ("MIL-STD-1605", "Procedures for Conducting a Shipboard Electromagnetic Interference (EMI) Survey (Surface Ships)", "Shipboard EMI survey procedure, cited when installations need an EMI survey."),
    ("MIL-DTL-2036", "Enclosures for Electric and Electronic Equipment, Naval Shipboard", "Enclosure requirements (drip-proof, watertight and so on) for shipboard electronics."),
    ("MIL-DTL-917", "Electric Power Equipment, Basic Requirements (Naval Shipboard Use)", "Basic requirements for shipboard electric power equipment such as motors and controllers."),
    ("MIL-DTL-16036", "Switchgear, Power, Low Voltage, Naval Shipboard", "Low voltage shipboard switchgear requirements."),
    ("MIL-STD-108", "Definitions of and Basic Requirements for Enclosures for Electronic Equipment", "Defines enclosure terms such as drip-proof, splash-proof and watertight that shipboard specs use."),
    ("MIL-HDBK-2036", "Preparation of Electronic Equipment Specifications", "Navy handbook for writing electronic equipment specifications; explains common shipboard requirements."),
    ("MIL-DTL-15024", "Plates, Tags and Bands for Identification of Equipment", "Nameplates and identification plates for shipboard and other equipment."),
    ("MIL-STD-777", "Schedule of Piping, Valves, Fittings, and Associated Piping Components for Naval Surface Ships", "Approved piping materials and components for surface ship systems."),
    ("MIL-STD-101", "Color Code for Pipelines and for Compressed Gas Cylinders", "Color coding for pipelines and gas cylinders."),
    ("MIL-STD-1330", "Precision Cleaning and Testing of Shipboard Oxygen, Helium, Helium-Oxygen, Nitrogen, and Hydrogen Systems", "Cleanliness requirements when parts go into shipboard gas systems."),
])

# ------------------------------------------------------------------ Environmental and reliability testing
C = "Environmental and reliability testing"
_g(C, DOD, [
    ("MIL-STD-810", "Environmental Engineering Considerations and Laboratory Tests", "Lab test methods for temperature, humidity, shock, vibration, salt fog, sand and dust; the contract names the methods and procedures."),
    ("MIL-HDBK-310", "Global Climatic Data for Developing Military Products", "Climate data used to set temperature and humidity test levels."),
    ("MIL-HDBK-781", "Reliability Test Methods, Plans, and Environments for Engineering, Development, Qualification, and Production", "Reliability demonstration test plans (MTBF tests)."),
    ("MIL-HDBK-2164", "Environmental Stress Screening Process for Electronic Equipment", "Environmental stress screening (thermal cycling, random vibration) of production electronics."),
    ("MIL-HDBK-344", "Environmental Stress Screening (ESS) of Electronic Equipment", "Planning and evaluating ESS programs for electronics."),
    ("MIL-HDBK-217", "Reliability Prediction of Electronic Equipment", "Parts count and stress methods for MTBF predictions, still widely requested."),
    ("MIL-HDBK-338", "Electronic Reliability Design Handbook", "Reliability design guidance for electronics."),
    ("MIL-HDBK-189", "Reliability Growth Management", "Reliability growth planning and tracking during development."),
    ("MIL-STD-1629", "Procedures for Performing a Failure Mode, Effects and Criticality Analysis", "FMECA method still named in many SOWs and CDRLs."),
    ("MIL-HDBK-470", "Designing and Developing Maintainable Products and Systems", "Maintainability design and analysis guidance."),
    ("MIL-STD-3034", "Reliability-Centered Maintenance (RCM) Process", "Navy RCM process used to develop maintenance requirements for equipment."),
    ("MIL-HDBK-502", "Product Support Analysis", "Product support and logistics analysis guidance."),
])
_g(C, "RTCA", [
    ("RTCA DO-160", "Environmental Conditions and Test Procedures for Airborne Equipment", "Environmental test standard for equipment installed on aircraft."),
])
_g(C, "ASTM", [
    ("ASTM B117", "Standard Practice for Operating Salt Spray (Fog) Apparatus", "Salt fog corrosion test commonly used to accept finishes and coatings."),
])
_g(C, "IEC", [
    ("IEC 60068", "Environmental testing (series)", "Commercial environmental test methods, used when equipment is qualified to commercial rather than MIL-STD-810 methods."),
    ("IEC 60812", "Failure modes and effects analysis (FMEA and FMECA)", "Commercial FMEA/FMECA method, an alternative to MIL-STD-1629 when allowed."),
])

# ------------------------------------------------------------------ Mechanical, fasteners and threads
C = "Mechanical, fasteners and threads"
_g(C, "ASME", [
    ("ASME B1.1", "Unified Inch Screw Threads (UN and UNR Thread Form)", "Thread form and classes for inch threads you machine or call out."),
    ("ASME B1.2", "Gages and Gaging for Unified Inch Screw Threads", "Thread gaging rules for inspecting inch threads."),
    ("ASME B1.13M", "Metric Screw Threads: M Profile", "Thread form and tolerances for metric threads."),
    ("ASME B1.20.1", "Pipe Threads, General Purpose, Inch", "NPT pipe threads on fittings and ports."),
    ("ASME B18.2.1", "Square, Hex, Heavy Hex, and Askew Head Bolts and Hex, Heavy Hex, Hex Flange, Lobed Head, and Lag Screws (Inch Series)", "Dimensions for inch bolts and hex cap screws."),
    ("ASME B18.2.2", "Nuts for General Applications: Machine Screw Nuts, Hex, Square, Hex Flange, and Coupling Nuts (Inch Series)", "Dimensions for inch nuts."),
    ("ASME B18.3", "Socket Cap, Shoulder, Set Screws, and Hex Keys (Inch Series)", "Dimensions for socket head cap screws and set screws."),
    ("ASME B18.6.3", "Machine Screws, Tapping Screws, and Metallic Drive Screws (Inch Series)", "Dimensions for machine and tapping screws."),
    ("ASME B18.8.2", "Taper Pins, Dowel Pins, Straight Pins, Grooved Pins, and Spring Pins (Inch Series)", "Dimensions for pins used in assemblies."),
    ("ASME B18.21.1", "Washers: Helical Spring-Lock, Tooth Lock, and Plain Washers (Inch Series)", "Dimensions for lock washers."),
    ("ASME B18.22.1", "Plain Washers", "Dimensions for plain washers."),
    ("ASME B46.1", "Surface Texture (Surface Roughness, Waviness, and Lay)", "Defines Ra and other roughness parameters for surface finish callouts on machined parts."),
    ("ASME B4.1", "Preferred Limits and Fits for Cylindrical Parts", "Inch fits (clearance, transition, interference) for shafts and bores."),
    ("ASME B4.2", "Preferred Metric Limits and Fits", "Metric fits for shafts and bores."),
])
_g(C, DOD, [
    ("FED-STD-H28", "Screw-Thread Standards for Federal Services", "Federal thread standard often cited on older government drawings."),
    ("MIL-DTL-1222", "Studs, Bolts, Screws and Nuts for Applications Where a High Degree of Reliability is Required", "High reliability fasteners for Navy machinery and shipboard applications."),
    ("MS33540", "Safety Wiring and Cotter Pinning, General Practices for", "Safety wire and cotter pin practices on legacy drawings."),
])
_g(C, "SAE", [
    ("AS8879", "Screw Threads, UNJ Profile, Inch, Controlled Radius Root with Increased Minor Diameter", "UNJ threads common on aerospace fasteners."),
    ("NASM1312", "Fastener Test Methods", "Test methods for fasteners such as tensile, shear and torque."),
    ("SAE J429", "Mechanical and Material Requirements for Externally Threaded Fasteners", "Grade 5 and grade 8 bolt requirements."),
    ("SAE J995", "Mechanical and Material Requirements for Steel Nuts", "Strength grades for steel nuts."),
])
_g(C, "ASTM", [
    ("ASTM F593", "Standard Specification for Stainless Steel Bolts, Hex Cap Screws, and Studs", "Stainless steel bolts and screws, common on corrosion resistant assemblies."),
    ("ASTM F594", "Standard Specification for Stainless Steel Nuts", "Stainless steel nuts that pair with F593 bolts."),
    ("ASTM A193", "Standard Specification for Alloy-Steel and Stainless Steel Bolting for High Temperature or High Pressure Service and Other Special Purpose Applications", "Bolting for pressure and high temperature service (B7, B8 grades)."),
    ("ASTM A194", "Standard Specification for Carbon Steel, Alloy Steel, and Stainless Steel Nuts for Bolts for High Pressure or High Temperature Service, or Both", "Nuts for A193 bolting."),
    ("ASTM A307", "Standard Specification for Carbon Steel Bolts, Studs, and Threaded Rod 60 000 PSI Tensile Strength", "General purpose carbon steel bolts."),
    ("ASTM A563", "Standard Specification for Carbon and Alloy Steel Nuts", "Carbon and alloy steel nuts for structural and general use."),
    ("ASTM F436", "Standard Specification for Hardened Steel Washers Inch and Metric Dimensions", "Hardened washers for structural bolting."),
    ("ASTM F3125", "Standard Specification for High Strength Structural Bolts and Assemblies, Steel and Alloy Steel, Heat Treated", "Structural bolts (A325 and A490 grades) for steel frames and platforms."),
])
_g(C, "ISO", [
    ("ISO 2768-1", "General tolerances, Part 1: Tolerances for linear and angular dimensions without individual tolerance indications", "Default tolerances on metric drawings that say 'ISO 2768-m' and similar."),
    ("ISO 286-1", "Geometrical product specifications (GPS): ISO code system for tolerances on linear sizes, Part 1", "Metric hole and shaft tolerance classes such as H7 and g6."),
    ("ISO 898-1", "Mechanical properties of fasteners made of carbon steel and alloy steel, Part 1: Bolts, screws and studs", "Metric property classes such as 8.8 and 10.9."),
    ("ISO 3506-1", "Mechanical properties of corrosion-resistant stainless steel fasteners, Part 1: Bolts, screws and studs", "Metric stainless fastener grades such as A2-70 and A4-80."),
])

# ------------------------------------------------------------------ Materials
C = "Materials (metals and plastics)"
_g(C, "ASTM", [
    ("ASTM A36", "Standard Specification for Carbon Structural Steel", "Common structural steel plate and shapes for frames, brackets and weldments."),
    ("ASTM A29", "Standard Specification for General Requirements for Steel Bars, Carbon and Alloy, Hot-Wrought", "General requirements for hot rolled carbon and alloy bar."),
    ("ASTM A108", "Standard Specification for Steel Bar, Carbon and Alloy, Cold-Finished", "Cold finished bar such as 1018 and 12L14 used for machined parts."),
    ("ASTM A240", "Standard Specification for Chromium and Chromium-Nickel Stainless Steel Plate, Sheet, and Strip for Pressure Vessels and for General Applications", "Stainless sheet and plate such as 304 and 316 for enclosures and sheet metal."),
    ("ASTM A276", "Standard Specification for Stainless Steel Bars and Shapes", "Stainless bar stock for machined parts."),
    ("ASTM A479", "Standard Specification for Stainless Steel Bars and Shapes for Use in Boilers and Other Pressure Vessels", "Stainless bar for pressure-retaining parts."),
    ("ASTM A564", "Standard Specification for Hot-Rolled and Cold-Finished Age-Hardening Stainless Steel Bars and Shapes", "17-4 PH and other precipitation hardening stainless bar."),
    ("ASTM A582", "Standard Specification for Free-Machining Stainless Steel Bars", "303 and other free machining stainless bar."),
    ("ASTM A666", "Standard Specification for Annealed or Cold-Worked Austenitic Stainless Steel Sheet, Strip, Plate, and Flat Bar", "Austenitic stainless sheet in annealed or cold worked tempers."),
    ("ASTM A500", "Standard Specification for Cold-Formed Welded and Seamless Carbon Steel Structural Tubing in Rounds and Shapes", "Square, rectangular and round structural tube for frames."),
    ("ASTM A513", "Standard Specification for Electric-Resistance-Welded Carbon and Alloy Steel Mechanical Tubing", "Mechanical tubing for frames and fabricated parts."),
    ("ASTM A516", "Standard Specification for Pressure Vessel Plates, Carbon Steel, for Moderate- and Lower-Temperature Service", "Pressure vessel plate."),
    ("ASTM A1008", "Standard Specification for Steel, Sheet, Cold-Rolled, Carbon, Structural, High-Strength Low-Alloy, High-Strength Low-Alloy with Improved Formability, Required Hardness, Solution Hardened, and Bake Hardenable", "Cold rolled steel sheet for sheet metal parts and enclosures."),
    ("ASTM A1011", "Standard Specification for Steel, Sheet and Strip, Hot-Rolled, Carbon, Structural, High-Strength Low-Alloy, High-Strength Low-Alloy with Improved Formability, and Ultra-High Strength", "Hot rolled steel sheet and strip."),
    ("ASTM A653", "Standard Specification for Steel Sheet, Zinc-Coated (Galvanized) or Zinc-Iron Alloy-Coated (Galvannealed) by the Hot-Dip Process", "Galvanized sheet for enclosures and brackets."),
    ("ASTM A53", "Standard Specification for Pipe, Steel, Black and Hot-Dipped, Zinc-Coated, Welded and Seamless", "General purpose steel pipe."),
    ("ASTM A106", "Standard Specification for Seamless Carbon Steel Pipe for High-Temperature Service", "Seamless pipe for pressure and temperature service."),
    ("ASTM A312", "Standard Specification for Seamless, Welded, and Heavily Cold Worked Austenitic Stainless Steel Pipes", "Stainless pipe."),
    ("ASTM A269", "Standard Specification for Seamless and Welded Austenitic Stainless Steel Tubing for General Service", "Stainless tubing for fluid lines."),
    ("ASTM B209", "Standard Specification for Aluminum and Aluminum-Alloy Sheet and Plate", "Aluminum sheet and plate such as 5052 and 6061 for sheet metal and machined plate."),
    ("ASTM B211", "Standard Specification for Aluminum and Aluminum-Alloy Rolled or Cold Finished Bar, Rod, and Wire", "Aluminum bar and rod for machined parts."),
    ("ASTM B221", "Standard Specification for Aluminum and Aluminum-Alloy Extruded Bars, Rods, Wire, Profiles, and Tubes", "Aluminum extrusions such as 6061 and 6063."),
    ("ASTM B241", "Standard Specification for Aluminum and Aluminum-Alloy Seamless Pipe and Seamless Extruded Tube", "Seamless aluminum pipe and tube."),
    ("ASTM B26", "Standard Specification for Aluminum-Alloy Sand Castings", "Aluminum sand castings."),
    ("ASTM B85", "Standard Specification for Aluminum-Alloy Die Castings", "Aluminum die castings."),
    ("ASTM B16", "Standard Specification for Free-Cutting Brass Rod, Bar and Shapes for Use in Screw Machines", "C36000 free cutting brass for machined fittings and contacts."),
    ("ASTM B36", "Standard Specification for Brass Plate, Sheet, Strip, And Rolled Bar", "Brass sheet and strip."),
    ("ASTM B152", "Standard Specification for Copper Sheet, Strip, Plate, and Rolled Bar", "Copper sheet and plate, including bus bar stock."),
    ("ASTM B187", "Standard Specification for Copper, Bus Bar, Rod, and Shapes and General Purpose Rod, Bar, and Shapes", "Copper bus bar for power distribution."),
    ("ASTM B88", "Standard Specification for Seamless Copper Water Tube", "Copper tube for water and cooling lines."),
    ("ASTM B150", "Standard Specification for Aluminum Bronze Rod, Bar, and Shapes", "Aluminum bronze bar for bushings and wear parts."),
    ("ASTM B505", "Standard Specification for Copper Alloy Continuous Castings", "Bronze bar stock for bearings and bushings."),
    ("ASTM B348", "Standard Specification for Titanium and Titanium Alloy Bars and Billets", "Titanium bar for machined parts."),
    ("ASTM B265", "Standard Specification for Titanium and Titanium Alloy Strip, Sheet, and Plate", "Titanium sheet and plate."),
    ("ASTM B164", "Standard Specification for Nickel-Copper Alloy Rod, Bar, and Wire", "Monel 400 bar, common on Navy seawater parts."),
    ("ASTM B127", "Standard Specification for Nickel-Copper Alloy Plate, Sheet, and Strip", "Monel 400 sheet and plate."),
    ("ASTM E8", "Standard Test Methods for Tension Testing of Metallic Materials", "Tensile test method behind most mill certs and weld qualifications."),
    ("ASTM E18", "Standard Test Methods for Rockwell Hardness of Metallic Materials", "Rockwell hardness testing of parts and heat treated material."),
    ("ASTM E10", "Standard Test Method for Brinell Hardness of Metallic Materials", "Brinell hardness testing."),
    ("ASTM E384", "Standard Test Method for Microindentation Hardness of Materials", "Vickers and Knoop microhardness testing."),
    ("ASTM E140", "Standard Hardness Conversion Tables for Metals", "Converting between hardness scales and approximate tensile strength."),
    ("ASTM E29", "Standard Practice for Using Significant Digits in Test Data to Determine Conformance with Specifications", "How to round test results when checking against a spec limit."),
    ("ASTM D4000", "Standard Classification System for Specifying Plastic Materials", "Call-out system for plastics on drawings."),
    ("ASTM D4066", "Standard Classification System for Nylon Injection and Extrusion Materials (PA)", "Nylon material call-outs."),
    ("ASTM D6778", "Standard Classification System and Basis for Specification for Polyoxymethylene Molding and Extrusion Materials (POM)", "Acetal (Delrin type) material call-outs."),
    ("ASTM D3935", "Standard Specification for Polycarbonate (PC) Unfilled and Reinforced Material", "Polycarbonate material call-outs."),
    ("ASTM D4101", "Standard Specification for Polypropylene Injection and Extrusion Materials", "Polypropylene material call-outs."),
    ("ASTM D709", "Standard Specification for Laminated Thermosetting Materials", "G-10, FR-4 and other laminate sheet used for insulators and panels."),
    ("ASTM D2000", "Standard Classification System for Rubber Products in Automotive Applications", "Rubber and gasket material call-outs."),
    ("ASTM D638", "Standard Test Method for Tensile Properties of Plastics", "Tensile testing of plastics, including printed test coupons."),
    ("ASTM D790", "Standard Test Methods for Flexural Properties of Unreinforced and Reinforced Plastics and Electrical Insulating Materials", "Flexural testing of plastics."),
    ("ASTM D256", "Standard Test Methods for Determining the Izod Pendulum Impact Resistance of Plastics", "Impact testing of plastics."),
    ("ASTM D648", "Standard Test Method for Deflection Temperature of Plastics Under Flexural Load in the Edgewise Position", "Heat deflection temperature of plastics."),
])
_g(C, DOD, [
    ("MIL-STD-889", "Dissimilar Metals", "Galvanic compatibility rules; check it when different metals touch in a wet or marine environment."),
    ("MIL-HDBK-5", "Metallic Materials and Elements for Aerospace Vehicle Structures", "Cancelled (Notice 1, 2004) and superseded by MMPDS; older drawings and stress reports still cite it."),
])
_g(C, "Battelle (MMPDS)", [
    ("MMPDS", "Metallic Materials Properties Development and Standardization", "Design allowables for metals (successor to MIL-HDBK-5), used in structural analysis."),
])
_g(C, "SAE", [
    ("AMS-QQ-A-250", "Aluminum and Aluminum Alloy Plate and Sheet", "SAE version of the old QQ-A-250 aluminum sheet and plate spec still on many drawings."),
    ("AMS2770", "Heat Treatment of Wrought Aluminum Alloy Parts", "Heat treatment of aluminum parts (for example to T6)."),
    ("AMS2772", "Heat Treatment of Aluminum Alloy Raw Materials", "Heat treatment of aluminum mill products."),
    ("AMS2759", "Heat Treatment of Steel Parts, General Requirements", "Heat treatment of steel parts; slash sheets cover specific steels."),
    ("AMS2750", "Pyrometry", "Furnace calibration and temperature uniformity rules your heat treat source must meet."),
])

# ------------------------------------------------------------------ Finishes, plating and coatings
C = "Finishes, plating and coatings"
_g(C, DOD, [
    ("MIL-STD-171", "Finishing of Metal and Wood Surfaces", "Finish system codes used on older drawings for metal and wood parts."),
    ("MIL-STD-7179", "Finishes, Coatings, and Sealants for the Protection of Aerospace Weapons Systems", "Finish requirements for aerospace equipment and support equipment."),
    ("MIL-DTL-5541", "Chemical Conversion Coatings on Aluminum and Aluminum Alloys", "Chem film (Alodine type) on aluminum; type I hexavalent or type II trivalent, class 1A or 3."),
    ("MIL-DTL-81706", "Chemical Conversion Materials for Coating Aluminum and Aluminum Alloys", "Qualified chemicals used to apply MIL-DTL-5541 coatings."),
    ("MIL-A-8625", "Anodic Coatings for Aluminum and Aluminum Alloys", "Anodizing (type II sulfuric, type III hard coat) of aluminum parts; validated as current by Notice 1 (2019)."),
    ("MIL-DTL-45204", "Gold Plating, Electrodeposited", "Gold plating for contacts and RF parts."),
    ("MIL-DTL-13924", "Coating, Oxide, Black, for Ferrous Metals", "Black oxide on steel parts."),
    ("MIL-DTL-16232", "Phosphate Coating, Heavy, Manganese or Zinc Base", "Phosphate coating on steel parts."),
    ("TT-C-490", "Chemical Conversion Coatings and Pretreatments for Metallic Substrates (Base for Organic Coatings)", "Pretreatment before painting steel and other metals."),
    ("MIL-DTL-14072", "Finishes for Ground Based Electronic Equipment", "Finish requirements for ground electronics enclosures and parts."),
    ("FED-STD-595", "Colors Used in Government Procurement", "Paint color numbers (for example 26173) called out on drawings; SAE now publishes it as AMS-STD-595."),
    ("MIL-DTL-53039", "Coating, Aliphatic Polyurethane, Single Component, Chemical Agent Resistant", "CARC topcoat for Army and Marine Corps equipment."),
    ("MIL-DTL-64159", "Camouflage Coating, Water Dispersible Aliphatic Polyurethane, Chemical Agent Resistant", "Water dispersible CARC topcoat."),
    ("MIL-DTL-53072", "Chemical Agent Resistant Coating (CARC) System Application Procedures and Quality Control Inspection", "How the CARC system is applied and inspected."),
    ("MIL-DTL-53022", "Primer, Epoxy Coating, Corrosion Inhibiting, Lead and Chromate Free", "Epoxy primer used under CARC."),
    ("MIL-DTL-53030", "Primer Coating, Epoxy, Water Based, Lead and Chromate Free", "Water based epoxy primer used under CARC."),
    ("MIL-PRF-23377", "Primer Coatings: Epoxy, High-Solids", "Epoxy primer for aircraft and support equipment."),
    ("MIL-PRF-85285", "Coating: Polyurethane, Aircraft and Support Equipment", "Polyurethane topcoat for aircraft and support equipment."),
    ("MIL-DTL-24441", "Paint, Epoxy-Polyamide, General Specification for", "Navy epoxy paint system for shipboard surfaces."),
    ("MIL-PRF-81733", "Sealing and Coating Compound, Corrosion Inhibitive", "Corrosion inhibiting sealant for faying surfaces and fasteners."),
    ("MIL-PRF-16173", "Corrosion Preventive Compound, Solvent Cutback, Cold-Application", "Temporary corrosion preventive for stored or shipped metal parts."),
])
_g(C, "SAE", [
    ("AMS2700", "Passivation of Corrosion Resistant Steels", "Passivation of stainless parts after machining."),
    ("AMS-QQ-N-290", "Nickel Plating (Electrodeposited)", "SAE adoption of QQ-N-290 for electroplated nickel."),
    ("AMS-C-26074", "Coatings, Electroless Nickel Requirements for", "Electroless nickel plating; same title as the older MIL-C-26074."),
    ("AMS-STD-595", "Colors Used in Government Procurement", "SAE adoption of FED-STD-595 color numbers."),
])
_g(C, "ASTM", [
    ("ASTM A967", "Standard Specification for Chemical Passivation Treatments for Stainless Steel Parts", "Passivation of stainless parts (nitric or citric)."),
    ("ASTM A380", "Standard Practice for Cleaning, Descaling, and Passivation of Stainless Steel Parts, Equipment, and Systems", "Cleaning and passivation practice for stainless fabrications."),
    ("ASTM B912", "Standard Specification for Passivation of Stainless Steels Using Electropolishing", "Passivation by electropolishing."),
    ("ASTM B733", "Standard Specification for Autocatalytic (Electroless) Nickel-Phosphorus Coatings on Metal", "Electroless nickel plating."),
    ("ASTM B633", "Standard Specification for Electrodeposited Coatings of Zinc on Iron and Steel", "Zinc plating on steel parts and fasteners."),
    ("ASTM B456", "Standard Specification for Electrodeposited Coatings of Copper Plus Nickel Plus Chromium and Nickel Plus Chromium", "Decorative chrome plating."),
    ("ASTM B488", "Standard Specification for Electrodeposited Coatings of Gold for Engineering Uses", "Engineering gold plating."),
    ("ASTM B545", "Standard Specification for Electrodeposited Coatings of Tin", "Tin plating."),
    ("ASTM B700", "Standard Specification for Electrodeposited Coatings of Silver for Engineering Use", "Silver plating for electrical contacts and bus bars."),
    ("ASTM B689", "Standard Specification for Electroplated Engineering Nickel Coatings", "Engineering nickel plating."),
    ("ASTM A123", "Standard Specification for Zinc (Hot-Dip Galvanized) Coatings on Iron and Steel Products", "Hot dip galvanizing of fabricated steel."),
    ("ASTM A153", "Standard Specification for Zinc Coating (Hot-Dip) on Iron and Steel Hardware", "Hot dip galvanizing of hardware and fasteners."),
    ("ASTM D3359", "Standard Test Methods for Rating Adhesion by Tape Test", "Paint adhesion test (cross-hatch tape test)."),
    ("ASTM D7091", "Standard Practice for Nondestructive Measurement of Dry Film Thickness of Nonmagnetic Coatings Applied to Ferrous Metals and Nonmagnetic, Nonconductive Coatings Applied to Non-Ferrous Metals", "Paint thickness measurement."),
    ("ASTM D523", "Standard Test Method for Specular Gloss", "Gloss measurement for painted surfaces."),
])
_g(C, "AMPP (SSPC)", [
    ("SSPC-SP 1", "Solvent Cleaning", "Surface preparation step before blasting or painting steel."),
    ("SSPC-SP 10", "Near-White Blast Cleaning (joint with NACE No. 2)", "Blast cleaning level often required before Navy and industrial coatings."),
])

# ------------------------------------------------------------------ Welding, brazing and NDT
C = "Welding, brazing and NDT"
_g(C, "AWS", [
    ("AWS D1.1", "Structural Welding Code: Steel", "Welding code for steel frames, brackets and weldments."),
    ("AWS D1.2", "Structural Welding Code: Aluminum", "Welding code for aluminum structures."),
    ("AWS D1.3", "Structural Welding Code: Sheet Steel", "Welding code for sheet steel up to about 3/16 inch."),
    ("AWS D1.6", "Structural Welding Code: Stainless Steel", "Welding code for stainless structures."),
    ("AWS D9.1", "Sheet Metal Welding Code", "Welding of sheet metal for ducts, enclosures and similar work."),
    ("AWS D17.1", "Specification for Fusion Welding for Aerospace Applications", "Aerospace fusion welding; the replacement named in the MIL-STD-2219 cancellation."),
    ("AWS D17.2", "Specification for Resistance Welding for Aerospace Applications", "Aerospace spot and seam welding."),
    ("AWS A2.4", "Standard Symbols for Welding, Brazing, and Nondestructive Examination", "Weld symbols on your drawings."),
    ("AWS A3.0", "Standard Welding Terms and Definitions", "Welding vocabulary used in codes and procedures."),
    ("AWS B2.1", "Specification for Welding Procedure and Performance Qualification", "Qualifying weld procedures (WPS/PQR) and welders when the contract does not name a code."),
    ("AWS B4.0", "Standard Methods for Mechanical Testing of Welds", "Bend, tensile and other tests of weld coupons."),
    ("AWS C3.4", "Specification for Torch Brazing", "Torch brazing process requirements."),
    ("AWS A5.1", "Specification for Carbon Steel Electrodes for Shielded Metal Arc Welding", "Stick electrodes such as E7018."),
    ("AWS A5.9", "Specification for Bare Stainless Steel Welding Electrodes and Rods", "Stainless filler such as ER308L and ER316L."),
    ("AWS A5.10", "Specification for Bare Aluminum and Aluminum-Alloy Welding Electrodes and Rods", "Aluminum filler such as ER4043 and ER5356."),
    ("AWS A5.18", "Specification for Carbon Steel Electrodes and Rods for Gas Shielded Arc Welding", "MIG and TIG carbon steel filler such as ER70S-6."),
    ("AWS QC1", "Standard for AWS Certification of Welding Inspectors", "Certified Welding Inspector (CWI) requirements."),
])
_g(C, "ASME", [
    ("ASME BPVC Section IX", "Welding, Brazing, and Fusing Qualifications", "Weld procedure and welder qualification for pressure work, often accepted for general work too."),
    ("ASME BPVC Section V", "Nondestructive Examination", "NDE methods referenced by the pressure vessel and piping codes."),
    ("ASME BPVC Section VIII", "Rules for Construction of Pressure Vessels", "Applies if you build pressure vessels or receivers."),
    ("ASME B31.1", "Power Piping", "Piping code for power and steam systems."),
    ("ASME B31.3", "Process Piping", "Piping code for process and fluid systems."),
])
_g(C, DOD, [
    ("MIL-STD-1689", "Fabrication, Welding, and Inspection of Ships Structure", "Welding and inspection of ship structure, including foundations and brackets welded to hull structure."),
    ("MIL-STD-22", "Welded Joint Design", "Standard weld joint designs referenced by Navy welding requirements."),
    ("MIL-STD-1595", "Qualification of Aircraft, Missile and Aerospace Fusion Welders", "Welder qualification for aerospace work; SAE also publishes it as AMS-STD-1595 with the same title."),
    ("MIL-STD-2219", "Fusion Welding for Aerospace Applications", "Cancelled (Notice 2, 2009); future acquisitions may refer to AWS D17.1."),
    ("MIL-STD-248", "Welding and Brazing Procedure and Performance Qualification", "Cancelled (Notice 1, 1997); replaced by NAVSEA S9074-AQ-GIB-010/248."),
    ("MIL-STD-271", "Requirements for Nondestructive Testing Methods", "Cancelled (Notice 2, 1998); references now point to NAVSEA T9074-AS-GIB-010/271."),
    ("MIL-STD-278", "Welding and Casting", "Cancelled (Notice 3, 1998); future acquisitions refer to NAVSEA S9074-AR-GIB-010/278."),
    ("MIL-STD-2035", "Nondestructive Testing Acceptance Criteria", "Navy acceptance criteria for RT, UT, MT, PT and VT inspections."),
    ("MIL-STD-1907", "Inspection, Liquid Penetrant and Magnetic Particle, Soundness Requirements for Materials, Parts, and Weldments", "Acceptance criteria (grades) for PT and MT indications."),
    ("MIL-STD-410", "Nondestructive Testing Personnel Qualification and Certification", "Cancelled (Notice 2); NAS 410 is the named replacement."),
    ("MIL-STD-6866", "Inspection, Liquid Penetrant", "Cancelled and replaced by ASTM E1417 (Notice 2)."),
    ("MIL-STD-453", "Inspection, Radiographic", "Cancelled (Notice 2, 1996); future acquisitions should refer to ASTM E1742."),
    ("MIL-STD-1949", "Inspection, Magnetic Particle", "Superseded by ASTM E1444; older drawings still cite it."),
])
_g(C, NAVSEA_TP, [
    ("S9074-AQ-GIB-010/248", "Requirements for Welding and Brazing Procedure and Performance Qualification", "Navy welding and brazing qualification requirements that replaced MIL-STD-248."),
    ("T9074-AS-GIB-010/271", "Requirements for Nondestructive Testing Methods", "Navy NDT method requirements that replaced MIL-STD-271."),
    ("S9074-AR-GIB-010/278", "Requirements for Fabrication Welding and Inspection, and Casting Inspection and Repair for Machinery, Piping, and Pressure Vessels", "Navy fabrication welding requirements that replaced MIL-STD-278."),
])
_g(C, "ASTM", [
    ("ASTM E1417", "Standard Practice for Liquid Penetrant Testing", "Penetrant inspection process (replacement for MIL-STD-6866)."),
    ("ASTM E1444", "Standard Practice for Magnetic Particle Testing", "Magnetic particle inspection process."),
    ("ASTM E1742", "Standard Practice for Radiographic Examination", "Radiographic inspection process (replacement for MIL-STD-453)."),
    ("ASTM E165", "Standard Practice for Liquid Penetrant Testing for General Industry", "Penetrant testing for general industry."),
    ("ASTM E709", "Standard Guide for Magnetic Particle Testing", "Guide to magnetic particle testing."),
    ("ASTM E164", "Standard Practice for Contact Ultrasonic Testing of Weldments", "Ultrasonic testing of welds."),
    ("ASTM E2375", "Standard Practice for Ultrasonic Testing of Wrought Products", "Ultrasonic testing of bar, plate and forgings."),
])
_g(C, "AIA (NAS)", [
    ("NAS 410", "NAS Certification and Qualification of Nondestructive Test Personnel", "NDT inspector certification for aerospace and defense work."),
])
_g(C, "ASNT", [
    ("ASNT SNT-TC-1A", "Personnel Qualification and Certification in Nondestructive Testing", "Recommended practice for certifying NDT inspectors at commercial shops."),
])
_g(C, "ISO", [
    ("ISO 9712", "Non-destructive testing: Qualification and certification of NDT personnel", "International NDT personnel certification."),
])

# ------------------------------------------------------------------ Quality
C = "Quality, inspection and counterfeit prevention"
_g(C, "ISO", [
    ("ISO 9001", "Quality management systems: Requirements", "The baseline quality system; often an evaluation strength or a requirement in Section C."),
    ("ISO 9000", "Quality management systems: Fundamentals and vocabulary", "Definitions used by ISO 9001."),
    ("ISO 19011", "Guidelines for auditing management systems", "How to run internal and supplier audits."),
    ("ISO 14001", "Environmental management systems: Requirements with guidance for use", "Environmental management system, occasionally requested by Navy activities."),
    ("ISO 10012", "Measurement management systems: Requirements for measurement processes and measuring equipment", "Calibration and measurement system requirements."),
    ("ISO/IEC 17025", "General requirements for the competence of testing and calibration laboratories", "Accreditation standard for the labs that calibrate your gages or test your parts."),
    ("ISO 2859-1", "Sampling procedures for inspection by attributes, Part 1", "ISO attribute sampling tables, similar to ANSI/ASQ Z1.4."),
])
_g(C, "SAE", [
    ("AS9100", "Quality Management Systems: Requirements for Aviation, Space, and Defense Organizations", "ISO 9001 plus aerospace and defense requirements; asked for by many primes."),
    ("AS9102", "Aerospace First Article Inspection Requirement", "First article inspection report format (forms 1, 2 and 3)."),
    ("AS9103", "Variation Management of Key Characteristics", "Control of key characteristics flagged on drawings."),
    ("AS9120", "Quality Management Systems: Requirements for Aviation, Space, and Defense Distributors", "Quality system for distributors and stocking resellers."),
    ("AS9145", "Requirements for Advanced Product Quality Planning and Production Part Approval Process", "APQP and PPAP for aerospace and defense production parts."),
    ("AS5553", "Counterfeit Electrical, Electronic, and Electromechanical (EEE) Parts; Avoidance, Detection, Mitigation, and Disposition", "Counterfeit parts program for anyone building electronics; ties to DFARS 252.246-7007 and -7008."),
    ("AS6081", "Fraudulent/Counterfeit Electronic Parts: Avoidance, Detection, Mitigation, and Disposition, Distributors", "Counterfeit avoidance for independent distributors you buy from."),
    ("AS6171", "Test Methods Standard; General Requirements, Suspect/Counterfeit, Electrical, Electronic, and Electromechanical Parts", "Test methods to detect suspect counterfeit parts."),
    ("AS6174", "Counterfeit Materiel; Assuring Acquisition of Authentic and Conforming Materiel", "Counterfeit prevention for non-electronic materiel such as fasteners and metals."),
    ("AS6496", "Fraudulent/Counterfeit Electronic Parts: Avoidance, Detection, Mitigation, and Disposition, Authorized/Franchised Distribution", "Counterfeit avoidance for franchised distributors."),
])
_g(C, "IDEA", [
    ("IDEA-STD-1010", "Acceptability of Electronic Components Distributed in the Open Market", "Inspection criteria for parts bought from the open market."),
])
_g(C, "NCSL International", [
    ("ANSI/NCSL Z540.3", "Requirements for the Calibration of Measuring and Test Equipment", "Calibration program requirements often cited in DoD quality clauses."),
])
_g(C, "ASQ", [
    ("ANSI/ASQ Z1.4", "Sampling Procedures and Tables for Inspection by Attributes", "Attribute sampling tables used for receiving and final inspection."),
    ("ANSI/ASQ Z1.9", "Sampling Procedures and Tables for Inspection by Variables for Percent Nonconforming", "Variables sampling tables."),
])
_g(C, DOD, [
    ("MIL-STD-1916", "DoD Preferred Methods for Acceptance of Product", "DoD sampling and process control methods for product acceptance."),
    ("MIL-HDBK-1916", "Companion Document to MIL-STD-1916", "Explains how to apply MIL-STD-1916."),
    ("MIL-STD-105", "Sampling Procedures and Tables for Inspection by Attributes", "Cancelled (Notice 1, 1995); superseded by MIL-STD-1916 and ANSI/ASQ Z1.4, though old drawings still cite it."),
    ("MIL-Q-9858", "Quality Program Requirements", "Older quality program requirement still seen on legacy drawings and contracts; most buyers now accept ISO 9001 or AS9100."),
    ("MIL-I-45208", "Inspection System Requirements", "Older inspection system requirement still seen on legacy contracts."),
    ("MIL-STD-45662", "Calibration Systems Requirements", "Older calibration system requirement still seen on legacy contracts; ANSI/NCSL Z540.3 or ISO/IEC 17025 are the usual references today."),
])

# ------------------------------------------------------------------ Packaging, marking and IUID
C = "Packaging, marking and IUID"
_g(C, DOD, [
    ("MIL-STD-2073-1", "Standard Practice for Military Packaging", "Military preservation and packing; the contract gives the method of preservation and packing level or an SPI."),
    ("MIL-STD-129", "Military Marking for Shipment and Storage", "Shipping labels, bar codes and container marking for everything you ship to DoD."),
    ("MIL-STD-130", "Identification Marking of U.S. Military Property", "Part marking and IUID 2D data matrix marks; required with DFARS 252.211-7003."),
    ("MIL-STD-3010", "Test Procedures for Packaging Materials and Containers", "Test methods for packaging materials."),
    ("MIL-STD-147", "Palletized Unit Loads", "How to build palletized loads for DoD shipments."),
    ("MIL-STD-1188", "Commercial Packaging of Supplies and Equipment", "Superseded by ASTM D3951, but still printed on some older contracts and drawings."),
    ("FED-STD-101", "Test Procedures for Packaging Materials", "Federal packaging material test methods."),
    ("MIL-PRF-131", "Barrier Materials, Watervaporproof, Greaseproof, Flexible, Heat-Sealable", "Moisture barrier bag material for method 50 type packs."),
    ("MIL-PRF-81705", "Barrier Materials, Flexible, Electrostatic Protective, Heat-Sealable", "ESD protective bags for electronics."),
    ("MIL-DTL-117", "Bags, Heat-Sealable", "Heat sealable bags used in military packs."),
    ("MIL-D-3464", "Desiccants, Activated, Bagged, Packaging Use and Static Dehumidification", "Desiccant bags in sealed packs."),
    ("MIL-I-8835", "Indicator, Humidity, Card, Chemically Impregnated", "Humidity indicator cards in sealed packs."),
    ("MIL-PRF-61002", "Pressure-Sensitive Adhesive Labels for Bar Coding", "Label stock for MIL-STD-129 bar code labels."),
    ("PPP-B-601", "Boxes, Wood, Cleated-Plywood", "Plywood shipping boxes for heavy items."),
    ("PPP-B-621", "Boxes, Wood, Nailed and Lock-Corner", "Wood shipping boxes."),
])
_g(C, "ASTM", [
    ("ASTM D3951", "Standard Practice for Commercial Packaging", "The usual packaging requirement when the contract allows commercial packaging."),
    ("ASTM D4169", "Standard Practice for Performance Testing of Shipping Containers and Systems", "Drop and vibration testing of shipping packs."),
    ("ASTM D5118", "Standard Practice for Fabrication of Fiberboard Shipping Boxes", "Fiberboard box construction."),
])
_g(C, "IPPC (free)", [
    ("ISPM 15", "Regulation of Wood Packaging Material in International Trade", "Heat treatment marking for wood pallets and crates shipped overseas or to many DoD sites."),
])
_g(C, "ISO", [
    ("ISO/IEC 15434", "Information technology: Automatic identification and data capture techniques: Syntax for high-capacity ADC media", "Data syntax inside IUID data matrix marks."),
    ("ISO/IEC 16022", "Information technology: Automatic identification and data capture techniques: Data Matrix bar code symbology specification", "The Data Matrix symbol used for IUID."),
    ("ISO/IEC 15415", "Information technology: Automatic identification and data capture techniques: Bar code symbol print quality test specification, Two-dimensional symbols", "Grading the print quality of 2D marks."),
])
_g(C, "ANSI (MH10)", [
    ("ANSI MH10.8.2", "Data Application Identifier Standard", "Data identifiers used in IUID and MIL-STD-129 bar codes."),
])
_g(C, "SAE", [
    ("AS9132", "Data Matrix Quality Requirements for Parts Marking", "Quality requirements for direct part marked Data Matrix symbols."),
])
_g(C, "UL", [
    ("UL 969", "Marking and Labeling Systems", "Durability of adhesive labels and nameplates on UL equipment."),
])

# ------------------------------------------------------------------ Technical manuals, training data and human factors
C = "Technical manuals, training data and human factors"
_g(C, DOD, [
    ("MIL-STD-40051-1", "Preparation of Digital Technical Information for Interactive Electronic Technical Manuals (IETMs)", "Cited when you must deliver an Army style IETM."),
    ("MIL-STD-40051-2", "Preparation of Digital Technical Information for Page-Based Technical Manuals (TMs)", "Cited when you must deliver a page-based technical manual."),
    ("MIL-STD-38784", "Standard Practice for Manuals, Technical: General Style and Format Requirements", "General style and format for technical manuals, common on Navy and Air Force work."),
    ("MIL-PRF-32216", "Evaluation of Commercial Off-the-Shelf (COTS) Manuals and Preparation of Supplemental Data", "Applies when you deliver commercial manuals plus supplemental data instead of a full military manual."),
    ("MIL-PRF-29612", "Training Data Products", "Defines training data products (course materials, lesson plans, test packages) delivered with training equipment."),
    ("MIL-HDBK-29612-1", "Guidance for Acquisition of Training Data Products and Services", "Explains how the government orders training data; helps you read training CDRLs."),
    ("MIL-HDBK-29612-2", "Instructional Systems Development/Systems Approach to Training and Education", "The ISD/SAT process behind training courseware deliverables."),
    ("MIL-STD-1472", "Human Engineering", "Design criteria for controls, displays, labels, reach and workspace; often cited for trainers and consoles."),
    ("MIL-STD-46855", "Human Engineering Requirements for Military Systems, Equipment, and Facilities", "Human engineering program and analysis requirements."),
    ("MIL-HDBK-46855", "Human Engineering Program Process and Procedures", "Guidance for running a human engineering program."),
    ("MIL-HDBK-759", "Human Engineering Design Guidelines", "Design guidelines that supplement MIL-STD-1472."),
    ("MIL-HDBK-1908", "Definitions of Human Factors Terms", "Human factors vocabulary."),
    ("MIL-STD-1474", "Noise Limits", "Noise limits for military equipment operators and maintainers."),
])
_g(C, "S1000D (free download)", [
    ("S1000D", "International specification for technical publications using a common source database", "Data module based technical publications, used by some Navy and aviation programs."),
])
_g(C, "ADL Initiative (free)", [
    ("SCORM", "Sharable Content Object Reference Model", "Packaging standard for e-learning content delivered to a learning management system."),
])
_g(C, "ASD", [
    ("ASD-STE100", "Simplified Technical English", "Controlled English rules sometimes required for maintenance manuals."),
])

# ------------------------------------------------------------------ Safety and electrical codes
C = "Safety and electrical codes"
_g(C, "NFPA", [
    ("NFPA 70", "National Electrical Code", "Wiring and installation rules for facilities and for equipment installed in buildings."),
    ("NFPA 70E", "Standard for Electrical Safety in the Workplace", "Safe work practices, arc flash and shock protection when your people work on energized equipment."),
    ("NFPA 70B", "Standard for Electrical Equipment Maintenance", "Electrical maintenance program requirements for facility equipment."),
    ("NFPA 79", "Electrical Standard for Industrial Machinery", "Electrical design of machines and trainers with motors, drives and controls."),
])
_g(C, "UL", [
    ("UL 508A", "Industrial Control Panels", "Building and listing industrial control panels; common for training equipment control cabinets."),
    ("UL 508", "Industrial Control Equipment", "Component standard for contactors, relays and motor controllers used in panels."),
    ("UL 61010-1", "Safety Requirements for Electrical Equipment for Measurement, Control, and Laboratory Use, Part 1: General Requirements", "Safety standard for test, measurement and lab equipment, including many electronic trainers."),
    ("UL 62368-1", "Audio/video, information and communication technology equipment, Part 1: Safety requirements", "Safety standard for computers, displays and IT equipment."),
    ("UL 94", "Tests for Flammability of Plastic Materials for Parts in Devices and Appliances", "Plastic flammability ratings (V-0, V-1, HB) for enclosures and printed parts."),
    ("UL 50", "Enclosures for Electrical Equipment, Non-Environmental Considerations", "Construction requirements for electrical enclosures."),
    ("UL 50E", "Enclosures for Electrical Equipment, Environmental Considerations", "Enclosure type ratings (Type 1, 4, 4X, 12) for environmental protection."),
    ("UL 489", "Molded-Case Circuit Breakers, Molded-Case Switches and Circuit-Breaker Enclosures", "Branch circuit breakers used in panels."),
    ("UL 1077", "Supplementary Protectors for Use in Electrical Equipment", "Supplementary protectors that are not branch circuit breakers."),
    ("UL 248-1", "Low-Voltage Fuses, Part 1: General Requirements", "Fuses used in equipment and panels."),
    ("UL 1449", "Surge Protective Devices", "Surge protective devices in panels and equipment."),
    ("UL 1642", "Lithium Batteries", "Lithium cells used in equipment."),
    ("UL 2054", "Household and Commercial Batteries", "Battery packs used in equipment."),
    ("UL 1310", "Class 2 Power Units", "Class 2 power supplies and wall adapters."),
    ("UL 44", "Thermoset-Insulated Wires and Cables", "Building wire types such as XHHW."),
    ("UL 83", "Thermoplastic-Insulated Wires and Cables", "Building wire types such as THHN and MTW."),
    ("UL 1004-1", "Rotating Electrical Machines, General Requirements", "Motors used in equipment."),
])
_g(C, "NEMA", [
    ("NEMA 250", "Enclosures for Electrical Equipment (1000 Volts Maximum)", "NEMA enclosure type ratings (1, 4, 4X, 12)."),
    ("ANSI Z535.4", "Product Safety Signs and Labels", "Format of DANGER, WARNING and CAUTION labels on equipment."),
    ("ANSI Z535.1", "Safety Colors", "Safety color definitions used on signs and labels."),
])
_g(C, "IEC", [
    ("IEC 60529", "Degrees of protection provided by enclosures (IP Code)", "IP ratings such as IP65 for enclosures."),
    ("IEC 60204-1", "Safety of machinery: Electrical equipment of machines, Part 1: General requirements", "International counterpart to NFPA 79 for machine electrical design."),
    ("IEC 61508", "Functional safety of electrical/electronic/programmable electronic safety-related systems", "Functional safety for safety-related control systems."),
])
_g(C, "ISO", [
    ("ISO 13849-1", "Safety of machinery: Safety-related parts of control systems, Part 1: General principles for design", "Performance levels for machine safety circuits (e-stops, interlocks)."),
    ("ISO 12100", "Safety of machinery: General principles for design, Risk assessment and risk reduction", "Machine risk assessment method."),
])
_g(C, "IEEE", [
    ("IEEE C2", "National Electrical Safety Code", "Utility and outdoor power line safety rules."),
    ("IEEE 1584", "Guide for Performing Arc-Flash Hazard Calculations", "Arc flash calculations behind NFPA 70E labels."),
])
_g(C, "LIA", [
    ("ANSI Z136.1", "Safe Use of Lasers", "Laser safety program requirements when equipment contains lasers."),
])
_g(C, DOD, [
    ("MIL-STD-882", "System Safety", "Hazard analysis and risk assessment; the SOW names which tasks you perform."),
    ("MIL-STD-1425", "Safety Design Requirements for Military Lasers and Associated Support Equipment", "Safety design rules for military laser equipment, including laser trainers."),
])
_g(C, "eCFR (free)", [
    ("29 CFR 1910", "Occupational Safety and Health Standards (general industry)", "OSHA rules for your shop and for your people working on government sites."),
    ("29 CFR 1910.147", "The control of hazardous energy (lockout/tagout)", "Lockout/tagout program for servicing machines and equipment."),
    ("29 CFR 1910 Subpart S", "Electrical (OSHA general industry)", "OSHA electrical safety rules for design and safe work practices."),
    ("29 CFR 1926", "Safety and Health Regulations for Construction", "OSHA construction rules when you install equipment as construction work."),
])

# ------------------------------------------------------------------ Additive manufacturing
C = "Additive manufacturing"
_g(C, "ISO/ASTM", [
    ("ISO/ASTM 52900", "Additive manufacturing: General principles, Fundamentals and vocabulary", "AM vocabulary used in purchase orders and specs."),
    ("ISO/ASTM 52901", "Additive manufacturing: General principles, Requirements for purchased AM parts", "What a buyer and supplier must agree on when ordering printed parts."),
    ("ISO/ASTM 52910", "Additive manufacturing: Design, Requirements, guidelines and recommendations", "Design guidance for printed parts."),
    ("ISO/ASTM 52911-1", "Additive manufacturing: Design, Part 1: Laser-based powder bed fusion of metals", "Design rules for metal laser powder bed fusion parts."),
    ("ISO/ASTM 52911-2", "Additive manufacturing: Design, Part 2: Laser-based powder bed fusion of polymers", "Design rules for polymer powder bed fusion parts."),
    ("ISO/ASTM 52915", "Specification for additive manufacturing file format (AMF)", "AMF file format for print data."),
    ("ISO/ASTM 52920", "Additive manufacturing: Qualification principles, Requirements for industrial additive manufacturing processes and production sites", "Qualification of an AM production site."),
])
_g(C, "ASTM", [
    ("ASTM F3122", "Standard Guide for Evaluating Mechanical Properties of Metal Materials Made via Additive Manufacturing Processes", "Which test methods to use on printed metal parts."),
    ("ASTM F2924", "Standard Specification for Additive Manufacturing Titanium-6 Aluminum-4 Vanadium with Powder Bed Fusion", "Ti-6Al-4V powder bed fusion parts."),
    ("ASTM F3001", "Standard Specification for Additive Manufacturing Titanium-6 Aluminum-4 Vanadium ELI (Extra Low Interstitial) with Powder Bed Fusion", "Ti-6Al-4V ELI powder bed fusion parts."),
    ("ASTM F3055", "Standard Specification for Additive Manufacturing Nickel Alloy (UNS N07718) with Powder Bed Fusion", "Inconel 718 powder bed fusion parts."),
    ("ASTM F3184", "Standard Specification for Additive Manufacturing Stainless Steel Alloy (UNS S31603) with Powder Bed Fusion", "316L stainless powder bed fusion parts."),
    ("ASTM F3318", "Standard for Additive Manufacturing: Finished Part Properties, Specification for AlSi10Mg with Powder Bed Fusion, Laser Beam", "AlSi10Mg aluminum powder bed fusion parts."),
    ("ASTM F3091", "Standard Specification for Powder Bed Fusion of Plastic Materials", "Polymer powder bed fusion (SLS) parts."),
    ("ASTM F3049", "Standard Guide for Characterizing Properties of Metal Powders Used for Additive Manufacturing Processes", "Metal powder testing and certification."),
    ("ASTM F3301", "Standard for Additive Manufacturing: Post Processing Methods, Thermal Post-Processing Metal Parts Made Via Powder Bed Fusion", "Stress relief, HIP and heat treatment of printed metal parts."),
])
_g(C, "AWS", [
    ("AWS D20.1", "Specification for Fabrication of Metal Components using Additive Manufacturing", "Qualification and inspection requirements for metal AM parts."),
])
_g(C, "SAE", [
    ("AMS7003", "Laser Powder Bed Fusion Process", "Process controls for laser powder bed fusion of aerospace parts."),
])

# ------------------------------------------------------------------ DIDs
C = "Data item descriptions (DIDs)"
_g(C, DOD, [
    ("DI-SESS-81000", "Product Drawings/Models and Associated Lists", "The usual DID for production drawings and models in a TDP."),
    ("DI-SESS-81001", "Conceptual Design Drawings/Models", "Conceptual design drawings early in a development effort."),
    ("DI-SESS-81002", "Developmental Design Drawings/Models and Associated Lists", "Developmental drawings for prototypes."),
    ("DI-SESS-81003", "Commercial Drawings/Models and Associated Lists", "Delivering your commercial drawings as is."),
    ("DI-SESS-81010", "Source Control Drawing Approval Request", "Requesting approval of a source control drawing."),
    ("DI-SESS-81022", "Configuration Audit Summary Report and Certification", "Report after a functional or physical configuration audit."),
    ("DI-SESS-81248", "Interface Control Document (ICD)", "Documenting interfaces between your equipment and others."),
    ("DI-SESS-81359", "Parts List", "Stand-alone parts list deliverable."),
    ("DI-SESS-81495", "Failure Modes, Effects, and Criticality Analysis Report", "FMECA report."),
    ("DI-SESS-81496", "Reliability and Maintainability (R&M) Block Diagrams and Mathematical Models Report", "R&M block diagrams and models."),
    ("DI-SESS-81497", "Reliability and Maintainability Predictions Report", "MTBF and MTTR predictions."),
    ("DI-SESS-81613", "Reliability and Maintainability (R&M) Program Plan", "R&M program plan."),
    ("DI-SESS-81315", "Failure Analysis and Corrective Action Report (FACAR)", "Failure reporting and corrective action report."),
    ("DI-SESS-81517", "Training Situation Document", "Training data product describing the training situation."),
    ("DI-SESS-81518", "Instructional Performance Requirements Document", "Training tasks and performance requirements."),
    ("DI-SESS-81519", "Instructional Media Requirements Document", "Which media each lesson needs."),
    ("DI-SESS-81520", "Instructional Media Design Package", "Design of the instructional media."),
    ("DI-SESS-81521", "Training Program Structure Document", "Course and curriculum structure."),
    ("DI-SESS-81522", "Course Conduct Support Document", "Course conduct support materials."),
    ("DI-SESS-81523", "Training Conduct Support Document", "Instructor and trainee guides and similar material."),
    ("DI-SESS-81524", "Training Evaluation Document", "Training evaluation results."),
    ("DI-SESS-81525", "Test Package", "Trainee tests and answer keys."),
    ("DI-SESS-81526", "Instructional Media Package", "The finished instructional media."),
    ("DI-SESS-81527", "Training System Support Document", "Support data for a training system."),
    ("DI-NDTI-80566", "Test Plan", "Test plan deliverable."),
    ("DI-NDTI-80603", "Test Procedure", "Step by step test procedure."),
    ("DI-NDTI-80808", "Test Plans/Procedures", "Combined test plan and procedures."),
    ("DI-NDTI-80809", "Test/Inspection Report", "Results of tests and inspections."),
    ("DI-NDTI-81307", "First Article Qualification Test Plan and Procedures", "First article test plan."),
    ("DI-CMAN-80639", "Engineering Change Proposal (ECP)", "Proposing a change to an approved configuration."),
    ("DI-CMAN-80640", "Request for Deviation (RFD)", "Asking to deliver something that departs from requirements."),
    ("DI-CMAN-80642", "Notice of Revision (NOR)", "Proposed revisions to drawings tied to an ECP."),
    ("DI-CMAN-80643", "Specification Change Notice (SCN)", "Proposed changes to a specification."),
    ("DI-CMAN-80858", "Contractor's Configuration Management Plan", "Your configuration management plan."),
    ("DI-CMAN-80776", "Technical Data Package", "A full technical data package deliverable."),
    ("DI-QCIC-80107", "Quality Program Plan", "Your quality program plan."),
    ("DI-QCIC-80553", "Acceptance Test Plan", "Acceptance test plan."),
    ("DI-QCIC-80736", "Quality Deficiency Report", "Report of a quality deficiency."),
    ("DI-QCIC-80798", "Calibration Certificate", "Calibration certificates for equipment."),
    ("DI-QCIC-81009", "Technical Data Package Quality Control Program Plan", "Quality control of the TDP itself."),
    ("DI-QCIC-81110", "Inspection and Test Plan", "Inspection and test plan."),
    ("DI-QCIC-81187", "Quality Assessment Report", "Quality assessment report."),
    ("DI-QCIC-80125", "Government Industry Data Exchange Program (GIDEP) Alert/Safe-Alert Report", "Reporting a GIDEP alert, for example on counterfeit parts."),
    ("DI-MISC-80508", "Technical Report: Study/Services", "A common catch-all technical report format."),
    ("DI-MISC-80711", "Scientific and Technical Reports", "Scientific and technical report format."),
    ("DI-MISC-80678", "Certification/Data Report", "Certifications and data such as material certs and CoCs."),
    ("DI-MISC-80526", "Parts Management Plan", "Parts management plan."),
    ("DI-MISC-80875", "Welding Procedures", "Weld procedure specifications."),
    ("DI-MISC-80876", "Welding Procedure Qualification Test Report", "Procedure qualification records."),
    ("DI-MGMT-80227", "Contractor's Progress, Status and Management Report", "Monthly status report."),
    ("DI-MGMT-81334", "Contract Work Breakdown Structure", "Contract WBS."),
    ("DI-MGMT-81650", "Integrated Master Schedule (IMS)", "Integrated master schedule."),
    ("DI-MGMT-81861", "Integrated Program Management Report (IPMR)", "Earned value and schedule reporting on larger contracts."),
    ("DI-MGMT-81803", "Item Unique Identification (IUID) Marking Plan", "Plan for IUID marking of delivered items."),
    ("DI-MGMT-81858", "Item Unique Identification (IUID) Marking and Verification Report", "Report of IUID marks applied and verified."),
    ("DI-MGMT-81808", "Contractor's Risk Management Plan", "Risk management plan."),
    ("DI-MGMT-81772", "Lead-Free Control Plan (LFCP)", "Lead-free control plan under GEIA-STD-0005-1."),
    ("DI-SAFT-80101", "System Safety Hazard Analysis Report (SSHA)", "Hazard analysis report under MIL-STD-882."),
    ("DI-SAFT-80102", "Safety Assessment Report (SAR)", "Safety assessment report under MIL-STD-882."),
    ("DI-SAFT-80106", "Health Hazard Assessment Report (HHAR)", "Health hazard assessment report."),
    ("DI-EMCS-80199", "Electromagnetic Interference Control Procedures (EMICP)", "EMI control procedures under MIL-STD-461."),
    ("DI-EMCS-80200", "Electromagnetic Interference Test Report (EMITR)", "EMI test report under MIL-STD-461."),
    ("DI-EMCS-80201", "Electromagnetic Interference Test Procedures (EMITP)", "EMI test procedures under MIL-STD-461."),
    ("DI-ENVR-80708", "Shock Test Report", "Report of MIL-DTL-901 shock testing."),
    ("DI-ENVR-80709", "High-Impact Shock Test Procedures", "Procedures for MIL-DTL-901 shock testing."),
    ("DI-ENVR-81647", "Mechanical Vibrations of Shipboard Equipment Measurement Test Data", "Data from MIL-STD-167-1 vibration testing."),
    ("DI-ENVR-81014", "Environmental Stress Screening (ESS) Procedures and Implementation Plan", "ESS procedures."),
    ("DI-ENVR-81663", "Environmental Stress Screening (ESS) Report", "ESS results."),
    ("DI-HFAC-80743", "Human Engineering Test Plan", "Human engineering test plan."),
    ("DI-HFAC-81742", "Human Engineering Program Plan (HEPP)", "Human engineering program plan."),
    ("DI-PACK-80120", "Preservation and Packing Data", "Packaging data for items you deliver."),
    ("DI-PACK-80121", "Special Packaging Instructions (SPI)", "Special packaging instructions (DD Form 2169)."),
    ("DI-PACK-80455", "Packaging Plan", "Packaging plan."),
    ("DI-TMSS-80527", "Commercial Off-the-Shelf (COTS) Manuals and Associated Supplemental Data", "Commercial manuals plus supplemental data."),
    ("DI-TMSS-80528", "Supplemental Data for Commercial Off-the-Shelf (COTS) Manuals", "Supplemental data to accompany commercial manuals."),
    ("DI-IPSC-81427", "Software Development Plan (SDP)", "Software development plan."),
    ("DI-IPSC-81433", "Software Requirements Specification (SRS)", "Software requirements."),
    ("DI-IPSC-81438", "Software Test Plan (STP)", "Software test plan."),
    ("DI-IPSC-81440", "Software Test Report (STR)", "Software test results."),
    ("DI-IPSC-81441", "Software Product Specification (SPS)", "Delivered software and its source."),
    ("DI-IPSC-81442", "Software Version Description (SVD)", "What is in a software release."),
    ("DI-IPSC-81443", "Software User Manual (SUM)", "Software user manual."),
])

# ------------------------------------------------------------------ Cybersecurity
C = "Cybersecurity"
_g(C, "NIST (free)", [
    ("NIST SP 800-171", "Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations", "Required by DFARS 252.204-7012 whenever you handle CUI such as controlled drawings; check which revision the contract names."),
    ("NIST SP 800-171A", "Assessing Security Requirements for Controlled Unclassified Information", "Assessment procedures used for SPRS scores and CMMC level 2 assessments."),
    ("NIST SP 800-172", "Enhanced Security Requirements for Protecting Controlled Unclassified Information", "Enhanced requirements behind CMMC level 3; rarely applies to small suppliers."),
    ("NIST SP 800-172A", "Assessing Enhanced Security Requirements for Controlled Unclassified Information", "Assessment procedures for SP 800-172."),
    ("NIST SP 800-53", "Security and Privacy Controls for Information Systems and Organizations", "Federal control catalog; applies if you operate a system on behalf of the government."),
    ("NIST SP 800-88", "Guidelines for Media Sanitization", "How to wipe or destroy drives and media that held CUI."),
    ("NIST SP 800-161", "Cybersecurity Supply Chain Risk Management Practices for Systems and Organizations", "Supply chain risk management practices."),
    ("NIST SP 800-218", "Secure Software Development Framework (SSDF)", "Secure software development practices when you deliver software."),
    ("NIST SP 800-82", "Guide to Operational Technology (OT) Security", "Security for control systems such as PLC-based trainers."),
    ("FIPS 140-3", "Security Requirements for Cryptographic Modules", "Validated encryption required for protecting CUI under SP 800-171."),
    ("FIPS 199", "Standards for Security Categorization of Federal Information and Information Systems", "Security categorization of federal systems."),
    ("FIPS 200", "Minimum Security Requirements for Federal Information and Information Systems", "Baseline security requirements for federal systems."),
    ("NIST CSF", "The NIST Cybersecurity Framework (CSF)", "General cybersecurity framework, useful for organizing a small company security program."),
])
_g(C, "eCFR (free)", [
    ("32 CFR 170", "Cybersecurity Maturity Model Certification (CMMC) Program", "The CMMC program rule: levels, assessments and affirmations."),
])
_g(C, "acquisition.gov (free)", [
    ("DFARS 252.204-7012", "Safeguarding Covered Defense Information and Cyber Incident Reporting", "Clause that makes NIST SP 800-171 and 72-hour incident reporting mandatory."),
    ("DFARS 252.204-7021", "Contractor Compliance with the Cybersecurity Maturity Model Certification Level Requirements", "Clause that requires the CMMC level stated in the solicitation."),
])
_g(C, "ISO", [
    ("ISO/IEC 27001", "Information security, cybersecurity and privacy protection: Information security management systems, Requirements", "Information security management system certification."),
])
_g(C, "IEC", [
    ("IEC 62443", "Security for industrial automation and control systems (series)", "Security for industrial control systems and components."),
])


def _build() -> list[dict]:
    out: list[dict] = []
    for category, publisher, rows in _RAW:
        for doc_id, title, summary in rows:
            out.append({
                "id": doc_id,
                "title": title,
                "category": category,
                "summary": summary,
                "publisher": publisher,
                "free": PUBLISHER_FREE.get(publisher, False),
            })
    return out


CATALOG: list[dict] = _build()
