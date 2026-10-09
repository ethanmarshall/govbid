"""Source Approval Requests (SAR): becoming an approved source for a DLA NSN that is restricted to approved sources.

Reference data below comes from the DLA "Source Approval Request (SAR) and Alternate Offer (AO) Guide",
November 2022 (initial release), published at
https://www.dla.mil/Portals/104/Documents/SmallBusiness/DLA%20SAR%20Guide.pdf
(read from the Internet Archive copy captured 2026-08-09, since dla.mil blocks automated downloads):
- Package categories I to IV (guide p. 5 to 6).
- The checklist of required sections by category (guide p. 9).
- Review time "generally ... a minimum of 90 days, and possibly up to 180 days or longer" (guide p. 7).
- Format: one PDF per submission named with the NSN and CAGE, no ZIP or password protection, email to the
  DLA activity; over 8 MB, email to request a DoD SAFE link (guide p. 7).
- Submission addresses by activity (guide Appendix A, p. 25 to 26).
- Eligibility: NSN bought "other than full and open", e.g. AMSC B, C or D; AMSC G is not evaluated (guide p. 4).
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

SAR_GUIDE_URL = "https://www.dla.mil/Portals/104/Documents/SmallBusiness/DLA%20SAR%20Guide.pdf"
SAR_GUIDE_TITLE = "DLA Source Approval Request (SAR) and Alternate Offer (AO) Guide, November 2022"

SAR_STATUSES = ["researching", "gathering_data", "submitted", "under_review", "approved", "disapproved", "withdrawn"]
OPEN_SAR_STATUSES = ["researching", "gathering_data", "submitted", "under_review"]
DLA_ACTIVITIES = ["Aviation", "Land and Maritime", "Troop Support"]

# Guide p. 7: "a minimum of 90 days, and possibly up to 180 days or longer"
REVIEW_MIN_DAYS = 90
REVIEW_LONG_DAYS = 180

# Guide p. 5 to 6, wording kept close to the source.
SAR_CATEGORIES = [
    {"key": "I", "label": "Category I: Actual Item",
     "definition": "You make the exact part. You have manufactured the actual item (within the last 3 to 5 years depending on "
                   "criticality) and provided it to the OEM, one of its subcontractors, the Government, DoD or DLA, and you have "
                   "legal rights to possess, use and redistribute its technical data."},
    {"key": "II", "label": "Category II: Similar Item",
     "definition": "You make a similar item (similar in complexity, design, criticality, materials and application) that was "
                   "provided to the OEM, one of its subcontractors, the Government, DoD or DLA, can prove you can make the actual "
                   "item, and legally possess the OEM's technical data package for the actual part. Several similar items can be "
                   "used together to show capability."},
    {"key": "III", "label": "Category III: New Manufacturer",
     "definition": "You do not meet Category I or II, but legally possess the OEM's technical data, have manufacturing experience "
                   "needing equal or greater capability, and intend to make the part to the approved technical data package."},
    {"key": "IV", "label": "Category IV: Reverse Engineered Part",
     "definition": "You do not meet Categories I to III and do not have the technical data, so you seek approval by reverse "
                   "engineering the item, at your own expense."},
]
CATEGORY_KEYS = [c["key"] for c in SAR_CATEGORIES]

# Guide p. 9 checklist: section, title, categories that require it, short description from p. 10 to 21.
SAR_CHECKLIST = [
    {"key": "TOC", "section": "*", "title": "Table of Contents", "categories": ["I", "II", "III", "IV"],
     "hint": "Name of each section and the page it starts on."},
    {"key": "A", "section": "A", "title": "Cover Letter", "categories": ["I", "II", "III", "IV"],
     "hint": "Category, NSN, nomenclature, platform if known, your part number, estimated unit price with breaks, solicitation number "
             "(alternate offer only), company info with CAGE, point of contact. Attach quality program description, quality control "
             "manual, latest Government or prime survey, and a brochure with capabilities and equipment list."},
    {"key": "B", "section": "B", "title": "Actual Part Drawings", "categories": ["I", "II", "III", "IV"],
     "hint": "Drawings at current revision, parts list, unincorporated changes, materials, processes, specifications and inspection data."},
    {"key": "C", "section": "C", "title": "Actual Part Detailed Manufacturing Plan", "categories": ["I", "II", "III", "IV"],
     "hint": "Copies of the actual process/operation sheets in sequence with special processes and subcontracted operations, signed or "
             "stamped by operator or inspector. Routing sheets alone are not enough."},
    {"key": "D", "section": "D", "title": "Master Tooling Certification", "categories": ["I", "II", "III", "IV"],
     "hint": "Access to required master or special tooling, plus proof of calibration, or a statement that none is required."},
    {"key": "E", "section": "E", "title": "Data Certification (company officer signature)", "categories": ["I", "II", "III", "IV"],
     "hint": "Technical Data Rights Certification text from the guide, on letterhead, signed by an officer, all on one page."},
    {"key": "F", "section": "F", "title": "Actual Part Subcontractor/Vendor List", "categories": ["I", "II", "III", "IV"],
     "hint": "Name, address, phone and CAGE of every subcontractor for forgings, castings, exotic material and special processes."},
    {"key": "G", "section": "G", "title": "Actual Part Shipping Documents", "categories": ["I"],
     "hint": "Recent purchase orders from the prime, OEM or Government with evidence of lot acceptance (signed DD Form 250 for Government)."},
    {"key": "H", "section": "H", "title": "Similar Part Drawings", "categories": ["II"],
     "hint": "Drawings and data for the similar part(s)."},
    {"key": "I", "section": "I", "title": "Similar Part Shipping Documents", "categories": ["II"],
     "hint": "Dated purchase orders and shipping documents for production quantities of the similar part. Explain gaps over three years."},
    {"key": "J", "section": "J", "title": "Comparative Analysis", "categories": ["II"],
     "hint": "Detailed comparison of similar vs actual part: materials, configuration, tolerances, processes, dimensions. A vague analysis hurts."},
    {"key": "K", "section": "K", "title": "Similar Part Manufacturing Plan", "categories": ["II"],
     "hint": "Manufacturing plan and actual operation sheets for the similar part."},
    {"key": "L", "section": "L", "title": "Similar Part Subcontractor/Vendor List", "categories": ["II"],
     "hint": "Subcontractors for special processes used on the similar part."},
    {"key": "M", "section": "M", "title": "Test Plans", "categories": ["I", "II", "III", "IV"],
     "hint": "Acceptance test and inspection procedures and any independent labs. Testing may be at your expense; First Article Testing may be required."},
    {"key": "N", "section": "N", "title": "Licensee Agreement (if applicable)", "categories": ["I", "II", "III", "IV"],
     "hint": "Only if you have a license agreement with the OEM. Otherwise state that none exists."},
    {"key": "O", "section": "O", "title": "Summary of Quality Deficiencies", "categories": ["I", "II"],
     "hint": "Quality deficiencies in the past three years on the qualification or similar part: MRB items, nonconformance reports, scrap rates."},
    {"key": "P", "section": "P", "title": "Inspection Method Sheets", "categories": ["I", "II", "III", "IV"],
     "hint": "In-process and final inspection sheets with characteristics, tolerances, actual measurements, method and inspector stamp."},
    {"key": "Q", "section": "Q", "title": "Technical Briefing (if requested)", "categories": ["III", "IV"],
     "hint": "A statement that you are willing to give a technical briefing."},
    {"key": "R", "section": "R", "title": "Sample Part (if requested)", "categories": ["I", "II", "III", "IV"],
     "hint": "State your ability to supply samples. Do not send samples unless told to in writing."},
    {"key": "S", "section": "S", "title": "Value Added", "categories": ["I", "II", "III", "IV"],
     "hint": "Any undocumented value the prime or OEM adds, or a statement that it adds none."},
    {"key": "T", "section": "T", "title": "Reverse Engineering Manufacturing Plan", "categories": ["IV"],
     "hint": "Level III drawings per ASME Y14 standards, proof the samples came from the Government, materials lab reports, a tabulation of "
             "measured dimensions (at least three parts recommended), tolerance rationale, and a statement that no proprietary data was used."},
]
CHECKLIST_KEYS = [c["key"] for c in SAR_CHECKLIST]
EXTRA_DOC_SECTIONS = {"RE": "Reverse engineering photos and reports", "OTHER": "Other files"}
ITEM_STATES = ["todo", "in_progress", "done", "na"]

# Guide Appendix A (p. 25 to 26)
DLA_SAR_CONTACTS = {
    "Land and Maritime": {"sar_email": "dsccao-sar@dla.mil", "technical": "ve.sar@dla.mil", "rppob": "DSCC.PartRequest@dla.mil",
                          "small_business": "SMBIZLandCols@dla.mil", "note": ""},
    "Aviation": {"sar_email": "dlaavnsmallbus@dla.mil", "technical": "", "rppob": "dscr.boc@dla.mil", "small_business": "dlaavnsmallbus@dla.mil",
                 "note": "Email the Aviation Small Business Office mailbox for SAR submissions and request a DoD SAFE link."},
    "Troop Support": {"sar_email": "TrpSptCandE-sar@dla.mil", "technical": "", "rppob": "DLAValueManagement@dla.mil",
                      "small_business": "dlatroopsupportsbo@dla.mil", "note": ""},
}


class SourceApproval(Base):
    __tablename__ = "source_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nsn: Mapped[str] = mapped_column(String(20), default="", index=True)
    niin: Mapped[str] = mapped_column(String(9), default="", index=True)
    part_number: Mapped[str] = mapped_column(String(80), default="")  # the approved source's part number you are qualifying to
    nomenclature: Mapped[str] = mapped_column(String(200), default="")
    approved_sources: Mapped[list] = mapped_column(JSON, default=list)  # [{"cage": "1A2B3", "part_number": "", "name": ""}]
    dla_activity: Mapped[str] = mapped_column(String(30), default="")
    category: Mapped[str] = mapped_column(String(4), default="")  # I | II | III | IV
    amsc: Mapped[str] = mapped_column(String(2), default="")
    solicitation_number: Mapped[str] = mapped_column(String(80), default="")  # set when sent as an alternate offer
    status: Mapped[str] = mapped_column(String(20), default="researching")
    submitted_date: Mapped[str] = mapped_column(String(10), default="")
    decision_date: Mapped[str] = mapped_column(String(10), default="")
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    approved_part_number: Mapped[str] = mapped_column(String(80), default="")
    approved_cage: Mapped[str] = mapped_column(String(10), default="")
    annual_demand: Mapped[int | None] = mapped_column(Integer, nullable=True)  # manual estimate, units per year
    # {"B": {"status": "done", "note": ""}, ...}
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    # [{"section": "B", "name": "B-drawing.pdf", "original": "drawing.pdf", "size": 1234, "uploaded_at": "..."}]
    files: Mapped[list] = mapped_column(JSON, default=list)
    re_measurements: Mapped[str] = mapped_column(Text, default="")
    re_materials: Mapped[str] = mapped_column(Text, default="")
    re_notes: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
