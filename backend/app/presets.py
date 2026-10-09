"""Target-market presets: recommended NAICS codes, DLA supply classes, and saved filter sets.

Edit these lists to change what the app recommends and which quick filters appear.
"""

NAICS_TITLES = {
    "335314": "Relay and Industrial Control Manufacturing",
    "334513": "Instruments for Measuring and Controlling Industrial Process Variables",
    "334515": "Instrument Manufacturing for Measuring and Testing Electricity and Electrical Signals",
    "335999": "All Other Miscellaneous Electrical Equipment and Component Manufacturing",
    "334419": "Other Electronic Component Manufacturing",
    "333999": "All Other Miscellaneous General Purpose Machinery Manufacturing",
    "332710": "Machine Shops",
    "332322": "Sheet Metal Work Manufacturing",
    "541330": "Engineering Services",
    "541380": "Testing Laboratories and Services",
    "811310": "Commercial and Industrial Machinery and Equipment Repair and Maintenance",
    "811210": "Electronic and Precision Equipment Repair and Maintenance",
}

PRIMARY_NAICS = "335314"

NAICS_GROUPS = {
    "manufacturing": {
        "label": "Core manufacturing",
        "codes": ["335314", "334513", "334515", "335999", "334419", "333999", "332710", "332322"],
    },
    "services": {
        "label": "Engineering, test and repair",
        "codes": ["541330", "541380", "811310", "811210"],
    },
}

RECOMMENDED_NAICS = NAICS_GROUPS["manufacturing"]["codes"] + NAICS_GROUPS["services"]["codes"]

FSC_TITLES = {
    "6110": "Electrical control equipment",
    "6685": "Pressure, temperature and humidity measuring instruments",
    "6625": "Electrical and electronic test instruments",
    "6130": "Power converters and supplies",
    "5995": "Cable, cord and wire assemblies",
    "5945": "Relays and solenoids",
    "5930": "Switches",
    "5925": "Circuit breakers",
    "6150": "Miscellaneous electric power distribution equipment",
    "6910": "Training aids",
    "6920": "Armament training devices",
    "6940": "Communication training devices",
}
RECOMMENDED_FSC = list(FSC_TITLES)

# Words that mark Navy nuclear power training buys. Matched against title, description,
# agency and solicitation number; each one is also a separate SAM.gov title query when synced.
NAVY_NUCLEAR_TRAINING_KEYWORDS = [
    "Nuclear Power Training",
    "NNPTC",
    "NPTU",
    "Nuclear Power School",
    "Nuclear Field",
    "trainer",
    "training aid",
    "mockup",
    "simulator",
    "test stand",
]
# Sent to SAM.gov as title searches. Kept shorter than the match list to save daily API requests.
NAVY_NUCLEAR_SYNC_TITLES = ["Nuclear Power Training", "NPTU", "NNPTC", "trainer"]

ELIGIBLE = "eligible_now,eligible_once_certified"
TARGET_NAICS = ",".join(RECOMMENDED_NAICS)

SEARCH_PRESETS = [
    {
        "id": "target",
        "name": "My target market",
        "description": "All recommended NAICS codes you can bid now or after VetCert",
        "params": {"naics": TARGET_NAICS, "eligibility": ELIGIBLE},
    },
    {
        "id": "manufacturing",
        "name": "Core manufacturing",
        "description": "Panels, instruments, test sets, harnesses, fabrication",
        "params": {"naics": ",".join(NAICS_GROUPS["manufacturing"]["codes"]), "eligibility": ELIGIBLE},
    },
    {
        "id": "services",
        "name": "Engineering, test and repair",
        "description": "541330, 541380, 811310, 811210",
        "params": {"naics": ",".join(NAICS_GROUPS["services"]["codes"]), "eligibility": ELIGIBLE},
    },
    {
        "id": "veteran",
        "name": "Veteran set-asides",
        "description": "SDVOSB and VA veteran set-asides in your NAICS codes",
        "params": {"naics": TARGET_NAICS, "set_aside": "SDVOSBC,SDVOSBS,VSA,VSS"},
    },
    {
        "id": "navy-nuclear",
        "name": "Navy nuclear training",
        "description": "NNPTC, NPTU and training-equipment buys, any NAICS",
        "params": {"kw": ",".join(NAVY_NUCLEAR_TRAINING_KEYWORDS), "my_naics_only": "false"},
    },
    {
        "id": "sources-sought",
        "name": "Sources sought in my NAICS",
        "description": "Responses here shape future set-asides",
        "params": {"naics": TARGET_NAICS, "notice_type": "Sources Sought"},
    },
    {
        "id": "dibbs",
        "name": "DIBBS watchlist",
        "description": "Imported DLA RFQs on your FSC/NSN watchlist",
        "params": {"source": "dibbs", "my_naics_only": "false"},
    },
]

SYNC_OPTIONS = [
    {"id": "profile", "label": "My profile's NAICS codes"},
    {"id": "manufacturing", "label": "Core manufacturing NAICS", "naics": NAICS_GROUPS["manufacturing"]["codes"]},
    {"id": "services", "label": "Engineering, test and repair NAICS", "naics": NAICS_GROUPS["services"]["codes"]},
    {"id": "navy-nuclear", "label": "Navy nuclear training (title keywords)", "titles": NAVY_NUCLEAR_SYNC_TITLES},
]


def meta() -> dict:
    return {
        "naics_titles": NAICS_TITLES,
        "naics_groups": NAICS_GROUPS,
        "primary_naics": PRIMARY_NAICS,
        "recommended_naics": RECOMMENDED_NAICS,
        "fsc_titles": FSC_TITLES,
        "recommended_fsc": RECOMMENDED_FSC,
        "search_presets": SEARCH_PRESETS,
        "sync_options": SYNC_OPTIONS,
        "navy_nuclear_keywords": NAVY_NUCLEAR_TRAINING_KEYWORDS,
    }
