"""Starting outlines for proposal packages and technical data packages.

Each section lists the compliance-matrix categories it should absorb, so a package
created from an analyzed opportunity arrives with every requirement already assigned.
"""

PROPOSAL_SECTIONS = [
    # volume, number, title, guidance, matrix categories, page break before
    ("Cover", "", "Cover letter",
     "One page. Solicitation number and title, company name, UEI, CAGE, socioeconomic status, point of contact, "
     "offer validity period, acknowledgment of all amendments, and a short statement of why you are the right choice. "
     "Check every submission-format requirement assigned here before you submit.",
     ["Submission"], False),
    ("Volume I: Technical", "1.0", "Executive summary",
     "Half a page to a page. Restate the customer's need in their words, your solution in one paragraph, "
     "and three to five discriminators tied to the evaluation factors.",
     [], True),
    ("Volume I: Technical", "2.0", "Understanding of the requirement",
     "Show you understand the scope, environment and risks. Reference the PWS/SOW paragraphs. Avoid restating the SOW word for word.",
     [], False),
    ("Volume I: Technical", "3.0", "Technical approach",
     "Answer each PWS/SOW requirement in the same order and numbering the solicitation uses. "
     "For each: what you will do, how, with what tools or people, and the result the government gets.",
     ["Technical / performance"], False),
    ("Volume I: Technical", "4.0", "Management approach and schedule",
     "Organization chart, lines of communication with the COR/CO, schedule or phase-in plan, reporting, delivery and risk management.",
     ["Reporting", "Delivery"], False),
    ("Volume I: Technical", "5.0", "Staffing and key personnel",
     "Labor categories and staffing levels, key personnel qualifications, recruiting and retention, and backup coverage.",
     [], False),
    ("Volume I: Technical", "6.0", "Quality control plan",
     "Inspection methods, frequency, who performs them, how defects are corrected and prevented, and records kept.",
     [], False),
    ("Volume II: Past performance", "1.0", "Past performance references",
     "Recent and relevant contracts: contract number, customer, POC with phone and email, period, value, scope, "
     "and how it relates to this requirement. Address any problems and corrective action.",
     ["Past performance"], True),
    ("Volume III: Price", "1.0", "Price narrative and assumptions",
     "Basis of the price, labor categories mapped to the wage determination if one applies, assumptions, and exceptions (ideally none). "
     "Pricing itself goes in the required CLIN schedule.",
     ["Pricing"], True),
    ("Volume IV: Representations and certifications", "1.0", "Representations, certifications and forms",
     "Signed SF 1449 or SF 33, SF 30 for each amendment, SAM confirmation, and any solicitation-specific representations.",
     ["Eligibility / reps"], True),
]

PROPOSAL_ITEMS = [
    ("", "Signed SF 1449 / SF 33 (offer form)", "", "Forms"),
    ("", "SF 30 amendment acknowledgments", "", "Forms"),
    ("", "Price schedule / CLIN pricing sheet", "", "Price"),
    ("", "Key personnel resumes", "", "Technical"),
    ("", "Past performance questionnaires sent to references", "", "Past performance"),
    ("", "Capability statement", "", "Marketing"),
]

TDP_SECTIONS = [
    ("Transmittal", "", "Transmittal letter",
     "Contract number, CLIN and CDRL lines being delivered, list of enclosures, distribution statement, and point of contact.",
     ["Submission"], False),
    ("Technical Data Package", "1.0", "Package overview and scope",
     "What was built or delivered, contract and CLIN references, TDP type and elements selected per the contract's MIL-STD-31000 option selection worksheet.",
     [], True),
    ("Technical Data Package", "2.0", "Configuration and revision status",
     "As-built configuration, top-level drawing and revision, approved ECPs and deviations, and confirmation that drawings match the delivered product.",
     [], False),
    ("Technical Data Package", "3.0", "Drawings and models index",
     "Drawing number, title, revision, sheet count, file name and format (native and neutral) for every drawing and model. Cite the drawing standard and edition used (for example ASME Y14.100 and Y14.5).",
     ["Technical / performance"], False),
    ("Technical Data Package", "4.0", "Associated lists",
     "Parts lists, data lists and index lists per ASME Y14.34.",
     [], False),
    ("Technical Data Package", "5.0", "Specifications and procurement data",
     "Material and process specifications, source control and specification control drawings, and approved sources for purchased parts.",
     [], False),
    ("Technical Data Package", "6.0", "Test procedures and results",
     "Procedures used, results summary, deviations, and references to the signed test and inspection reports.",
     ["Reporting"], False),
    ("Technical Data Package", "7.0", "Quality records and certifications",
     "Certificates of conformance, material certifications, first article results and inspection records.",
     ["Eligibility / reps"], False),
    ("Technical Data Package", "8.0", "Manuals and instructions",
     "Operation, maintenance and installation instructions, and the manual standard they follow.",
     [], False),
    ("Technical Data Package", "9.0", "Markings, distribution and data rights",
     "Distribution statement, export control notice, data rights legends, and IUID marking data where required.",
     ["Delivery"], False),
]

TDP_ITEMS = [
    ("A001", "Product drawings/models and associated lists", "DI-SESS-81000", "Drawings"),
    ("A002", "Test procedure", "DI-NDTI-80603", "Test"),
    ("A003", "Test/inspection report", "DI-NDTI-80809", "Test"),
    ("A004", "Technical report", "DI-MISC-80508", "Reports"),
    ("", "Certificates of conformance and material certifications", "", "Quality"),
    ("", "Operation and maintenance manual", "", "Manuals"),
]

TEMPLATES = {
    "proposal": (PROPOSAL_SECTIONS, PROPOSAL_ITEMS),
    "tdp": (TDP_SECTIONS, TDP_ITEMS),
    "blank": ([], []),
}
