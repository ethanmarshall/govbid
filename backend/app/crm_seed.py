"""Starter contact list for a new supplier of custom training equipment, test equipment, cable and
electrical assemblies, and machined or fabricated parts to the Navy and its primes.

URLs are filled only where they were checked (October 2026). Blank means: find the supplier portal on their website.
"""

STARTER_ORGS: list[dict] = [
    {
        "name": "Naval Nuclear Laboratory (Fluor Marine Propulsion, LLC)",
        "kind": "prime",
        "website": "https://navalnuclearlab.energy.gov/",
        "supplier_portal": "https://navalnuclearlab.energy.gov/prospective-suppliers/",
        "tags": ["navy", "training equipment", "conflict check"],
        "notes": (
            "Possible buyer of training aids, test equipment, cable assemblies and machined parts through the Fluor Marine "
            "Propulsion small business subcontracting program. You already work there as a subcontractor through another "
            "company: clear any personal and organizational conflict of interest with both employers first, keep the two roles "
            "separate, and go only through the supplier diversity and procurement channels."
        ),
    },
    {
        "name": "General Dynamics Electric Boat",
        "kind": "prime",
        "website": "https://www.gdeb.com/",
        "supplier_portal": "https://www.gdeb.com/suppliers/4_future_suppliers/",
        "tags": ["navy", "shipbuilder"],
        "notes": "Submarine builder that buys fabricated and machined parts, cable assemblies and test fixtures. Start with the prospective supplier page and register your capabilities.",
    },
    {
        "name": "Huntington Ingalls Industries, Newport News Shipbuilding",
        "kind": "prime",
        "website": "https://hii.com/",
        "supplier_portal": "https://supplier.huntingtoningalls.com/",
        "tags": ["navy", "shipbuilder"],
        "notes": "Carrier and submarine builder with a large supplier base for machined parts, electrical assemblies and shop aids. Register through the HII supplier site and ask for the Newport News small business liaison.",
    },
    {
        "name": "Lockheed Martin",
        "kind": "prime",
        "website": "https://www.lockheedmartin.com/",
        "supplier_portal": "https://www.lockheedmartin.com/en-us/suppliers.html",
        "tags": ["defense prime", "small business program"],
        "notes": "Large prime with a small business programs office. Use the suppliers page to register and look for divisions that buy training systems or electrical assemblies.",
    },
    {
        "name": "Northrop Grumman",
        "kind": "prime",
        "website": "https://www.northropgrumman.com/",
        "supplier_portal": "https://www.northropgrumman.com/suppliers",
        "tags": ["defense prime", "small business program"],
        "notes": "Has an Office of Small Business Programs listed on its suppliers page. Register and target the marine systems and test equipment buyers.",
    },
    {
        "name": "RTX (Raytheon)",
        "kind": "prime",
        "website": "https://www.rtx.com/",
        "supplier_portal": "https://www.rtx.com/suppliers",
        "tags": ["defense prime", "small business program"],
        "notes": "Suppliers page links to its small business program. Good fit for cable harnesses, test fixtures and precision machined parts.",
    },
    {
        "name": "DLA Office of Small Business Programs",
        "kind": "agency",
        "website": "https://www.dla.mil/smallbusiness",
        "supplier_portal": "",
        "tags": ["agency", "DIBBS"],
        "notes": "Small business specialists who can explain how to bid DLA spare parts on DIBBS. Ask about DLA Land and Maritime buys that match your NAICS and CAGE.",
    },
    {
        "name": "NAVSEA Office of Small Business Programs",
        "kind": "agency",
        "website": "https://www.navsea.navy.mil/Business-Partnerships/",
        "supplier_portal": "",
        "tags": ["agency", "navy"],
        "notes": "Small business office for Naval Sea Systems Command and its warfare centers. Send a capability statement and ask which centers buy training and test equipment.",
    },
    {
        "name": "Local APEX Accelerator",
        "kind": "apex_sbdc",
        "website": "https://www.napex.us/locations/",
        "supplier_portal": "",
        "tags": ["free help"],
        "notes": "Free counseling on SAM registration, VetCert, bids and finding primes. Use the napex.us locator to find your local office and rename this entry.",
    },
]


def seed(db) -> dict:
    """Insert any starter organizations not already present (matched by name, case-insensitive)."""
    from sqlalchemy import func, select

    from .models_crm import Organization

    added, skipped = [], []
    for row in STARTER_ORGS:
        exists = db.scalar(select(Organization.id).where(func.lower(Organization.name) == row["name"].lower()))
        if exists:
            skipped.append(row["name"])
            continue
        db.add(Organization(stage="identified", source="seed", **row))
        added.append(row["name"])
    db.commit()
    return {"added": len(added), "skipped": len(skipped), "names": added}
