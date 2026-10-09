"""Curated FAR and DFARS clause flowdown table for DoD supply and service work.

Every entry below was checked against the clause text on acquisition.gov on 2026-10-08
(FAR FAC 2026-01, effective 03/13/2026; DFARS Part 252 as published that day). The
"paragraph" field quotes or closely paraphrases the subcontracts paragraph of each clause, and
"source_url" points at the page that was read. Thresholds that the clauses cite by reference were
read from these FAR sections on the same day:

  FAR 3.1004(a)   52.203-13 threshold: $7.5 million, performance period of 120 days or more
                  https://www.acquisition.gov/far/3.1004
  FAR 9.405-2(b)  subcontracts in excess of $45,000 (other than COTS)
                  https://www.acquisition.gov/far/9.405-2
  FAR 22.1303(a)  $200,000 or more (52.222-35, 52.222-37)
                  https://www.acquisition.gov/far/22.1303
  FAR 22.1408(a)  exceeds $20,000 (52.222-36)
                  https://www.acquisition.gov/far/22.1408
  FAR 22.807(b)(1) Equal Opportunity clause exemption for transactions of $10,000 or less
                  https://www.acquisition.gov/far/22.807
  FAR 19.702(a)   subcontracting plans above $900,000 ($2 million for construction)
                  https://www.acquisition.gov/far/19.702
  FAR 2.101       simplified acquisition threshold: $350,000
                  https://www.acquisition.gov/far/2.101

Commercial subcontracts: FAR 52.244-6(c)(1) (Oct 2025) and 52.212-5(e)(1) (Mar 2026) list the only
FAR clauses a prime must flow to subcontracts for commercial products or services, and DFARS
252.244-7000(a) (Nov 2023) says not to include other FAR clauses, and to include DFARS clauses
only when the clause itself says so.

Thresholds change with inflation adjustments and the FAR overhaul. Always confirm against the
clause dates in your prime contract.
"""
from __future__ import annotations

from typing import Callable

FAR = "https://www.acquisition.gov/far/"
DFARS = "https://www.acquisition.gov/dfars/part-252-solicitation-provisions-and-contract-clauses#DFARS_"

THRESHOLDS = {
    "far_3_1004": 7_500_000.0,
    "far_9_405_2": 45_000.0,
    "far_22_1303": 200_000.0,
    "far_22_1408": 20_000.0,
    "far_22_807": 10_000.0,
    "far_19_702": 900_000.0,
    "far_19_702_construction": 2_000_000.0,
    "sat": 350_000.0,
}

COMMERCIAL_NOTE = (
    "Subcontracts for commercial products or commercial services only carry the FAR clauses listed in "
    "FAR 52.244-6(c)(1) (or 52.212-5(e)(1) when your prime contract is a commercial contract), and DFARS "
    "252.244-7000 says to include a DFARS clause in a commercial subcontract only when that clause says so. "
    "You may add a minimal number of other clauses needed to meet your own contract obligations (52.244-6(c)(2))."
)

# FAR clauses named in the commercial flowdown lists of 52.244-6(c)(1) or 52.212-5(e)(1).
FAR_COMMERCIAL_LIST = {
    "52.203-13", "52.203-19", "52.204-21", "52.204-23", "52.204-25", "52.204-27", "52.219-8",
    "52.222-21", "52.222-26", "52.222-35", "52.222-36", "52.222-37", "52.222-40", "52.222-41",
    "52.222-50", "52.222-54", "52.224-3", "52.232-40", "52.247-64",
}

# Subcontract questions the checker understands. Missing keys use these defaults.
SUBCONTRACT_DEFAULTS = {
    "value": 0.0,                       # subcontract or PO value, dollars
    "commercial": False,                # commercial product or commercial service
    "cots": False,                      # commercially available off-the-shelf item
    "prime_commercial": False,          # your prime contract is itself for commercial products/services
    "services": False,                  # subcontract is for services
    "supplies": True,                   # subcontract is for supplies
    "construction": False,
    "maintenance_repair": False,        # maintenance and repair services
    "involves_fci": False,              # Federal contract information on the vendor's systems
    "involves_cui": False,              # CUI / covered defense information
    "operationally_critical": False,    # operationally critical support (252.204-7012)
    "international": False,             # any work or supplies outside the United States
    "us_work": True,                    # any work performed in the United States
    "performance_days": 0,              # length of the subcontract period of performance
    "small_business": False,            # vendor is a small business
    "further_subcontracting": False,    # vendor will itself subcontract parts of the work
    "pii": False,                       # vendor handles PII or a Privacy Act system of records
    "electronic_parts": False,          # electronic parts or assemblies containing them
    "original_manufacturer": False,     # vendor is the original manufacturer of those parts
    "specialty_metals": False,          # items containing specialty metals
    "iuid": False,                      # items that need IUID marking under 252.211-7003(c)(1)
    "ocean_shipping": False,            # vendor will ship supplies by sea
    "resale_no_value_added": False,     # you resell the vendor's item without adding value
    "contingency_support": False,       # shipped in direct support of contingency ops, exercises, deployed forces
    "sca_covered": False,               # Service Contract Labor Standards apply to the work
}

Rule = Callable[[dict], "tuple[bool | None, str]"]


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _norm(sub: dict | None) -> dict:
    s = dict(SUBCONTRACT_DEFAULTS)
    for k, v in (sub or {}).items():
        if k in s and v is not None and v != "":
            s[k] = v
    s["value"] = float(s.get("value") or 0)
    s["performance_days"] = int(float(s.get("performance_days") or 0))
    for k, v in SUBCONTRACT_DEFAULTS.items():
        if isinstance(v, bool):
            s[k] = bool(s[k])
    if s["cots"]:
        s["commercial"] = True
    if s["involves_cui"]:
        s["involves_fci"] = True
    return s


# ---------------------------------------------------------------- rules
def _always(s):
    return True, "Required in all subcontracts."


def _always_incl_commercial(s):
    return True, "Required in all subcontracts, including commercial ones."


def r_203_13(s):
    t = THRESHOLDS["far_3_1004"]
    if s["value"] > t and s["performance_days"] > 120:
        return True, f"Value over {_money(t)} and performance period over 120 days."
    return False, f"Only for subcontracts over {_money(t)} with a performance period over 120 days."


def r_204_21(s):
    if s["cots"]:
        return False, "Not required for COTS items."
    if s["involves_fci"]:
        return True, "Federal contract information may reside on or pass through the vendor's systems."
    return False, "Only when federal contract information may reside on or pass through the vendor's systems."


def r_209_6(s):
    t = THRESHOLDS["far_9_405_2"]
    if s["prime_commercial"]:
        return False, "Not required when your prime contract is for commercial products or services."
    if s["cots"]:
        return False, "Not required for COTS items."
    if s["value"] > t:
        return True, f"Subcontract exceeds {_money(t)} (FAR 9.405-2(b)) and is not for COTS items."
    return False, f"Only for subcontracts over {_money(t)} (FAR 9.405-2(b))."


def r_219_8(s):
    if s["further_subcontracting"]:
        return True, "The subcontract offers further subcontracting opportunities."
    return False, "Only for subcontracts that offer further subcontracting opportunities."


def r_219_9(s):
    t = THRESHOLDS["far_19_702_construction"] if s["construction"] else THRESHOLDS["far_19_702"]
    if s["small_business"]:
        return False, "Small business subcontractors do not need their own subcontracting plan."
    if s["value"] > t and s["further_subcontracting"]:
        return True, (f"Large business subcontract over {_money(t)} with further subcontracting: the vendor must adopt "
                      "its own subcontracting plan. This only applies if your prime contract has a plan (small business primes are exempt).")
    return False, f"Only for other-than-small subcontracts over {_money(t)} with further subcontracting possibilities."


def r_eo(s):
    t = THRESHOLDS["far_22_807"]
    if not s["us_work"]:
        return False, "Work entirely outside the United States is exempt (FAR 22.807(b)(2))."
    if s["value"] > t:
        return True, f"Over {_money(t)}, so the Equal Opportunity clause applies (FAR 22.807(b)(1))."
    return False, (f"Subcontracts of {_money(t)} or less are exempt unless your total subcontracts with this vendor in 12 months "
                   f"exceed {_money(t)} (FAR 22.807(b)(1)).")


def r_222_35(s):
    t = THRESHOLDS["far_22_1303"]
    if s["value"] >= t:
        return True, f"Valued at or above {_money(t)} (FAR 22.1303)."
    return False, f"Only at or above {_money(t)} (FAR 22.1303)."


def r_222_36(s):
    t = THRESHOLDS["far_22_1408"]
    if s["value"] > t:
        return True, f"Over {_money(t)} (FAR 22.1408(a))."
    return False, f"Only over {_money(t)} (FAR 22.1408(a))."


def r_222_40(s):
    if s["value"] > 10_000 and s["us_work"]:
        return True, "Over $10,000 and performed at least partly in the United States."
    return False, "Only over $10,000 and performed wholly or partly in the United States."


def r_222_41(s):
    if s["services"] and s["sca_covered"]:
        return True, "Service subcontract subject to the Service Contract Labor Standards."
    if s["services"]:
        return None, "Service subcontract: flow down if the Service Contract Labor Standards cover the work."
    return False, "Only for service subcontracts subject to the Service Contract Labor Standards."


def r_222_50(s):
    extra = ""
    if s["international"] and s["value"] > 700_000 and not s["cots"]:
        extra = " The compliance plan and certification in paragraph (h) also apply to the portion over $700,000 performed or acquired outside the United States."
    return True, "Required in all subcontracts and contracts with agents." + extra


def r_222_54(s):
    if not (s["services"] or s["construction"]):
        return False, "Only for subcontracts for services or construction."
    if s["value"] <= 3_500:
        return False, "Only for subcontracts over $3,500."
    if not s["us_work"]:
        return False, "Only when work is performed in the United States."
    return True, "Services or construction over $3,500 with work in the United States."


def r_224_3(s):
    if s["pii"]:
        return True, "Vendor employees will handle PII or a system of records."
    return False, "Only when vendor employees handle PII or a Privacy Act system of records."


def r_232_40(s):
    if s["small_business"]:
        return True, "Vendor is a small business."
    return False, "Only for subcontracts with small businesses."


def r_246_2(s):
    return None, ("No subcontracts paragraph. Paragraph (d) makes you require subcontractors to furnish facilities and help "
                  "for Government inspection at their plants, so it is common to flow inspection rights to suppliers.")


def r_247_64(s):
    if not s["commercial"]:
        return True, "Required in all non-commercial subcontracts and purchase orders."
    if s["construction"] or s["resale_no_value_added"] or s["contingency_support"]:
        return True, "Commercial, but an exception in paragraph (e)(4) applies (construction, resale without added value, or contingency support)."
    return False, "Commercial subcontracts are excluded by paragraph (e)(4) unless an exception applies."


def r_7012(s):
    if s["involves_cui"] or s["operationally_critical"]:
        return True, "Covered defense information or operationally critical support. Flow down without alteration."
    return False, "Only when the subcontract involves covered defense information or operationally critical support."


def r_7020(s):
    if s["cots"]:
        return False, "Not required for COTS items."
    msg = "Required in all subcontracts except COTS."
    if s["involves_cui"]:
        msg += " Before award, confirm the vendor has a current NIST SP 800-171 assessment posted in SPRS (paragraph (g)(2))."
    return True, msg


def r_7021(s):
    if s["cots"]:
        return False, "Not required for COTS items."
    if s["involves_fci"]:
        return True, "Vendor will process, store or transmit FCI or CUI. Confirm the vendor's CMMC status before award (paragraph (f)(2))."
    return False, "Only when the vendor will process, store or transmit FCI or CUI."


def r_7003(s):
    if s["iuid"]:
        return True, "Vendor supplies items that need IUID marking."
    return False, "Only when the vendor supplies items that need IUID marking under paragraph (c)(1)."


def r_7006(s):
    t = 1_000_000
    if s["commercial"]:
        return False, "Commercial subcontracts are not covered."
    if s["value"] > t:
        return True, "Non-commercial subcontract over $1 million: the vendor must agree to the arbitration restrictions."
    return False, "Only for non-commercial subcontracts over $1 million."


def r_7008(s):
    if s["supplies"] or s["maintenance_repair"] or s["construction"]:
        return True, "Subcontract is for supplies, maintenance and repair services, or construction materials."
    return False, "Only for supplies, maintenance and repair services, or construction materials."


def r_7009(s):
    if s["specialty_metals"]:
        return True, "Items contain specialty metals. Flow paragraphs (a) through (c) and (e)(2)."
    return False, "Only for items containing specialty metals."


def r_7001(s):
    if s["value"] > 500_000:
        return True, "Over $500,000."
    return False, "Only over $500,000."


def r_7007(s):
    if s["electronic_parts"]:
        return True, "Electronic parts or assemblies. Flow paragraphs (a) through (e) only."
    return False, "Only for electronic parts or assemblies containing electronic parts."


def r_7008b(s):
    if s["electronic_parts"] and not s["original_manufacturer"]:
        return True, "Electronic parts from a source other than the original manufacturer."
    if s["electronic_parts"]:
        return False, "Not required when the vendor is the original manufacturer."
    return False, "Only for electronic parts or assemblies containing electronic parts."


def r_7023(s):
    if not s["ocean_shipping"]:
        return False, "Only when the vendor will transport supplies by sea."
    covered = (not s["commercial"]) or s["construction"] or s["resale_no_value_added"] or s["contingency_support"]
    if not covered:
        return False, "Commercial items are only covered in the cases in paragraph (c)(2)."
    if s["value"] > THRESHOLDS["sat"]:
        return True, "Ocean shipment over the simplified acquisition threshold: flow the full clause."
    return True, "Ocean shipment at or below the simplified acquisition threshold: flow paragraphs (a) through (f) and (j)."


def r_reserved(s):
    return None, "This clause number is now marked [Reserved] in the FAR. Check the clause text in your contract."


def r_not_required(s):
    return False, "The clause has no subcontract flowdown paragraph."


# ---------------------------------------------------------------- table
def _c(number, title, date, status, condition, paragraph, rule, commercial=None, threshold=None, note="", portion=""):
    fam = "DFARS" if number.startswith("252.") else "FAR"
    url = (DFARS + number) if fam == "DFARS" else (FAR + number)
    if commercial is None:
        commercial = number in FAR_COMMERCIAL_LIST if fam == "FAR" else False
    return {
        "number": number, "title": title, "date": date, "family": fam, "status": status,
        "condition": condition, "threshold": threshold, "paragraph": paragraph, "source_url": url,
        "commercial": commercial, "note": note, "portion": portion, "_rule": rule,
    }


CLAUSES: list[dict] = [
    _c("52.203-13", "Contractor Code of Business Ethics and Conduct", "Nov 2021", "conditional",
       "Subcontracts over the FAR 3.1004(a) threshold ($7.5 million) with a performance period of more than 120 days.",
       "(d)(1) The Contractor shall include the substance of this clause, including this paragraph (d), in subcontracts that exceed the threshold specified in FAR 3.1004(a) on the date of subcontract award and a performance period of more than 120 days.",
       r_203_13, threshold=THRESHOLDS["far_3_1004"],
       note="Disclosures of False Claims Act or criminal violations go to the agency OIG, with a copy to the Contracting Officer (paragraph (d)(2))."),
    _c("52.203-19", "Prohibition on Requiring Certain Internal Confidentiality Agreements or Statements", "Jan 2017", "mandatory",
       "All subcontracts.",
       "(f) The Contractor shall include the substance of this clause, including this paragraph (f), in subcontracts under such contracts.",
       _always),
    _c("52.204-21", "Basic Safeguarding of Covered Contractor Information Systems", "Nov 2021", "conditional",
       "Subcontracts (including commercial, other than COTS) where the subcontractor may have Federal contract information on its information system.",
       "(c) The Contractor shall include the substance of this clause, including this paragraph (c), in subcontracts under this contract (including subcontracts for the acquisition of commercial products or commercial services, other than commercially available off-the-shelf items), in which the subcontractor may have Federal contract information residing in or transiting through its information system.",
       r_204_21),
    _c("52.204-23", "Prohibition on Contracting for Hardware, Software, and Services Developed or Provided by Kaspersky Lab Covered Entities", "Dec 2023", "mandatory",
       "All subcontracts, including commercial.",
       "(d) The Contractor shall insert the substance of this clause, including this paragraph (d), in all subcontracts including subcontracts for the acquisition of commercial products or commercial services.",
       _always_incl_commercial),
    _c("52.204-25", "Prohibition on Contracting for Certain Telecommunications and Video Surveillance Services or Equipment", "Nov 2021", "mandatory",
       "All subcontracts and other contractual instruments, including commercial. Exclude paragraph (b)(2).",
       "(e) The Contractor shall insert the substance of this clause, including this paragraph (e) and excluding paragraph (b)(2), in all subcontracts and other contractual instruments, including subcontracts for the acquisition of commercial products or commercial services.",
       _always_incl_commercial, portion="excluding paragraph (b)(2)"),
    _c("52.204-27", "Prohibition on a ByteDance Covered Application", "Jun 2023", "mandatory",
       "All subcontracts, including commercial.",
       "(c) The Contractor shall insert the substance of this clause, including this paragraph (c), in all subcontracts, including subcontracts for the acquisition of commercial products or commercial services.",
       _always_incl_commercial),
    _c("52.209-6", "Protecting the Government's Interest When Subcontracting With Contractors Debarred, Suspended, Proposed for Debarment, or Voluntarily Excluded", "Jan 2025", "conditional",
       "Unless the prime contract is commercial: subcontracts over the FAR 9.405-2(b) threshold ($45,000) that are not for COTS items.",
       "(e) Unless this is a contract for the acquisition of commercial products or commercial services, the Contractor shall include the requirements of this clause, including this paragraph (e) (appropriately modified for the identification of the parties), in each subcontract that (1) Exceeds the threshold specified in FAR 9.405-2(b) on the date of subcontract award; and (2) Is not a subcontract for commercially available off-the-shelf items.",
       r_209_6, threshold=THRESHOLDS["far_9_405_2"]),
    _c("52.219-8", "Utilization of Small Business Concerns", "Jan 2025", "conditional",
       "Subcontracts that offer further subcontracting opportunities.",
       "The clause itself has no subcontracts paragraph. FAR 52.244-6(c)(1)(x) and 52.212-5(e)(1)(viii) require it \"in all subcontracts that offer further subcontracting opportunities\", and 52.219-9(d)(9) requires the same assurance in a subcontracting plan.",
       r_219_8, note="If the subcontract (except to a small business) exceeds the FAR 19.702(a) threshold, the subcontractor must include 52.219-8 in its own lower-tier subcontracts that offer subcontracting opportunities."),
    _c("52.219-9", "Small Business Subcontracting Plan", "Jan 2025", "conditional",
       "Other-than-small subcontractors receiving subcontracts over the FAR 19.702(a) threshold ($900,000; $2 million for construction) with further subcontracting possibilities must adopt their own plan.",
       "(d)(9) Assurances that the Offeror will include the clause of this contract entitled \"Utilization of Small Business Concerns\" in all subcontracts that offer further subcontracting opportunities, and that the Offeror will require all subcontractors (except small business concerns...) that receive subcontracts in excess of the applicable threshold specified in FAR 19.702(a) on the date of subcontract award, with further subcontracting possibilities to adopt a subcontracting plan that complies with the requirements of this clause.",
       r_219_9, threshold=THRESHOLDS["far_19_702"],
       note="Paragraph (a): this clause does not apply to small business concerns, so a small business prime normally will not have it."),
    _c("52.219-14", "Limitations on Subcontracting", "Oct 2022", "not_required",
       "No flowdown. The clause limits how much you, the prime, pay to subcontractors that are not similarly situated.",
       "The clause has no subcontracts paragraph. Paragraph (e) limits the prime: services, not more than 50 percent of the amount paid by the Government to subcontractors that are not similarly situated entities; supplies, not more than 50 percent excluding the cost of materials.",
       r_not_required, note="Track the percentage in the pricing workbook's limitations on subcontracting check."),
    _c("52.222-21", "Prohibition of Segregated Facilities", "Apr 2015", "conditional",
       "Every subcontract and purchase order subject to the Equal Opportunity clause (over $10,000, with work in the United States, per FAR 22.807).",
       "(c) The Contractor shall include this clause in every subcontract and purchase order that is subject to the Equal Opportunity clause of this contract.",
       r_eo, threshold=THRESHOLDS["far_22_807"]),
    _c("52.222-26", "Equal Opportunity", "Sept 2016", "conditional",
       "Every subcontract or purchase order not exempted by the Secretary of Labor (FAR 22.807 exempts $10,000 or less and work outside the United States).",
       "(c)(11) The Contractor shall include the terms and conditions of this clause in every subcontract or purchase order that is not exempted by the rules, regulations, or orders of the Secretary of Labor issued under Executive Order 11246, as amended, so that these terms and conditions will be binding upon each subcontractor or vendor.",
       r_eo, threshold=THRESHOLDS["far_22_807"],
       note="Include it only if your prime contract contains it."),
    _c("52.222-35", "Equal Opportunity for Veterans", "Jun 2020", "conditional",
       "Subcontracts valued at or above the FAR 22.1303 threshold ($200,000).",
       "(c) Subcontracts. The Contractor shall insert the terms of this clause in subcontracts valued at or above the threshold specified in FAR 22.1303(a) on the date of subcontract award, unless exempted by rules, regulations, or orders of the Secretary of Labor.",
       r_222_35, threshold=THRESHOLDS["far_22_1303"]),
    _c("52.222-36", "Equal Opportunity for Workers with Disabilities", "Jun 2020", "conditional",
       "Subcontracts or purchase orders over the FAR 22.1408(a) threshold ($20,000).",
       "(b) Subcontracts. The Contractor shall include the terms of this clause in every subcontract or purchase order in excess of the threshold specified in FAR 22.1408(a) on the date of subcontract award, unless exempted by rules, regulations, or orders of the Secretary.",
       r_222_36, threshold=THRESHOLDS["far_22_1408"]),
    _c("52.222-37", "Employment Reports on Veterans", "Jun 2020", "conditional",
       "Subcontracts valued at or above the FAR 22.1303 threshold ($200,000).",
       "(g) The Contractor shall insert the terms of this clause in subcontracts valued at or above the threshold specified in FAR 22.1303(a) on the date of subcontract award, unless exempted by rules, regulations, or orders of the Secretary of Labor.",
       r_222_35, threshold=THRESHOLDS["far_22_1303"]),
    _c("52.222-40", "Notification of Employee Rights Under the National Labor Relations Act", "Dec 2010", "conditional",
       "Subcontracts over $10,000 performed wholly or partly in the United States.",
       "(f)(1) The Contractor shall include the substance of this clause, including this paragraph (f), in every subcontract that exceeds $10,000 and will be performed wholly or partially in the United States, unless exempted by the rules, regulations, or orders of the Secretary of Labor.",
       r_222_40, threshold=10_000.0),
    _c("52.222-41", "Service Contract Labor Standards", "Aug 2018", "conditional",
       "Subcontracts subject to the Service Contract Labor Standards statute.",
       "(l) Subcontracts. The Contractor agrees to insert this clause in all subcontracts subject to the Service Contract Labor Standards statute.",
       r_222_41),
    _c("52.222-50", "Combating Trafficking in Persons", "Oct 2025", "mandatory",
       "All subcontracts and all contracts with agents. Paragraph (h) only for portions over $700,000 for supplies (other than COTS) acquired outside the United States or services performed outside the United States.",
       "(i)(1) The Contractor shall include the substance of this clause, including this paragraph (i), in all subcontracts and in all contracts with agents. The requirements in paragraph (h) of this clause apply only to any portion of the subcontract that (i) Is for supplies, other than commercially available off-the-shelf items, acquired outside the United States, or services to be performed outside the United States; and (ii) Has an estimated value that exceeds $700,000.",
       r_222_50),
    _c("52.222-54", "Employment Eligibility Verification", "Jan 2025", "conditional",
       "Subcontracts for services or construction over $3,500 that include work performed in the United States.",
       "(e) The Contractor shall include the requirements of this clause, including this paragraph (e) (appropriately modified for identification of the parties), in each subcontract that (1) Is for services (except for commercial services that are part of the purchase of a COTS item ... performed by the COTS provider, and are normally provided for that COTS item) or construction; (2) Has a value of more than $3,500; and (3) Includes work performed in the United States.",
       r_222_54, threshold=3_500.0),
    _c("52.223-18", "[Reserved] (formerly Encouraging Contractor Policies to Ban Text Messaging While Driving)", "", "check",
       "acquisition.gov now shows 52.223-18 as [Reserved].",
       "Check the clause text in your contract. The current FAR page for 52.223-18 shows [Reserved].",
       r_reserved),
    _c("52.224-3", "Privacy Training", "Jan 2017", "conditional",
       "Subcontracts where subcontractor employees will access a system of records, handle PII, or design, develop, maintain or operate a system of records.",
       "(f) The substance of this clause, including this paragraph (f), shall be included in all subcontracts under this contract, when subcontractor employees will (1) Have access to a system of records; (2) Create, collect, use, process, store, maintain, disseminate, disclose, dispose, or otherwise handle personally identifiable information; or (3) Design, develop, maintain, or operate a system of records.",
       r_224_3),
    _c("52.225-1", "Buy American-Supplies", "Oct 2022", "not_required",
       "No flowdown paragraph. You must still deliver domestic end products, so check your suppliers' content.",
       "The clause has no subcontracts paragraph. Paragraph (d): the Contractor shall deliver only domestic end products except to the extent it specified foreign end products in its Buy American Certificate.",
       r_not_required),
    _c("52.225-13", "Restrictions on Certain Foreign Purchases", "Feb 2021", "mandatory",
       "All subcontracts.",
       "(c) The Contractor shall insert this clause, including this paragraph (c), in all subcontracts.",
       _always, note="Not on the 52.244-6(c)(1) or 52.212-5(e)(1) lists, so it is not required in subcontracts for commercial products or services."),
    _c("52.232-40", "Providing Accelerated Payments to Small Business Subcontractors", "Mar 2023", "conditional",
       "All subcontracts with small businesses, including commercial.",
       "(c) Include the substance of this clause, including this paragraph (c), in all subcontracts with small business concerns, including subcontracts with small business concerns for the acquisition of commercial products or commercial services.",
       r_232_40),
    _c("52.244-6", "Subcontracts for Commercial Products and Commercial Services", "Oct 2025", "mandatory",
       "All subcontracts.",
       "(d) The Contractor shall include the terms of this clause, including this paragraph (d), in subcontracts awarded under this contract.",
       _always_incl_commercial, commercial=True,
       note="Paragraph (c)(1) lists the FAR clauses that must go into commercial subcontracts."),
    _c("52.246-2", "Inspection of Supplies-Fixed-Price", "Aug 1996", "check",
       "No subcontracts paragraph. Paragraph (d) requires you to have subcontractors furnish facilities and assistance for Government inspection.",
       "(d) If the Government performs inspection or test on the premises of the Contractor or a subcontractor, the Contractor shall furnish, and shall require subcontractors to furnish, at no increase in contract price, all reasonable facilities and assistance for the safe and convenient performance of these duties.",
       r_246_2),
    _c("52.247-64", "Preference for Privately Owned U.S.-Flag Commercial Vessels", "Nov 2021", "conditional",
       "All subcontracts and purchase orders, except commercial ones not covered by the exceptions in paragraph (e)(4).",
       "(d) The Contractor shall insert the substance of this clause, including this paragraph (d), in all subcontracts or purchase orders under this contract, except those described in paragraph (e)(4). (e)(4) excludes subcontracts for commercial products or services unless the contract is for ocean transportation or construction, or the supplies are resold without added value or shipped in direct support of contingency operations, exercises, or UN/NATO humanitarian or peacekeeping deployments.",
       r_247_64),
    # ---------------------------------------------------------------- DFARS
    _c("252.203-7002", "Requirement to Inform Employees of Whistleblower Rights", "Dec 2022", "mandatory",
       "All subcontracts.",
       "(b) The Contractor shall include the substance of this clause, including this paragraph (b), in all subcontracts.",
       _always),
    _c("252.204-7012", "Safeguarding Covered Defense Information and Cyber Incident Reporting", "May 2024", "conditional",
       "Subcontracts for operationally critical support, or where performance will involve covered defense information, including commercial. Flow without alteration.",
       "(m)(1) Include this clause, including this paragraph (m), in subcontracts, or similar contractual instruments, for operationally critical support, or for which subcontract performance will involve covered defense information, including subcontracts for commercial products or commercial services, without alteration, except to identify the parties.",
       r_7012, commercial=True,
       note="Also require the vendor to tell you when it asks the CO to vary from a NIST SP 800-171 requirement and to give you the DoD incident report number (paragraph (m)(2))."),
    _c("252.204-7020", "NIST SP 800-171 DoD Assessment Requirements", "Nov 2023", "conditional",
       "All subcontracts and other contractual instruments, including commercial, excluding COTS.",
       "(g)(1) The Contractor shall insert the substance of this clause, including this paragraph (g), in all subcontracts and other contractual instruments, including subcontracts for the acquisition of commercial products or commercial services (excluding commercially available off-the-shelf).",
       r_7020, commercial=True),
    _c("252.204-7021", "Contractor Compliance With the Cybersecurity Maturity Model Certification Level Requirements", "Nov 2025", "conditional",
       "Subcontracts (including commercial, excluding COTS) that will require processing, storing or transmitting FCI or CUI. Exclude paragraph (e)(1).",
       "(f)(1) Insert the substance of this clause, including this paragraph (f) and excluding paragraph (e)(1), in subcontracts and other contractual instruments, including those for the acquisition of commercial products and commercial services, excluding commercially available off-the-shelf items, if the subcontract or other contractual instrument will contain a requirement to process, store, or transmit FCI or CUI.",
       r_7021, commercial=True, portion="excluding paragraph (e)(1)"),
    _c("252.211-7003", "Item Unique Identification and Valuation", "Jan 2023", "conditional",
       "Subcontracts for items that need IUID under paragraph (c)(1), including commercial.",
       "(g) If the Contractor acquires by subcontract any item(s) for which item unique identification is required in accordance with paragraph (c)(1) of this clause, the Contractor shall include this clause, including this paragraph (g), in the applicable subcontract(s), including subcontracts for commercial products or commercial services.",
       r_7003, commercial=True),
    _c("252.222-7006", "Restrictions on the Use of Mandatory Arbitration Agreements", "Jan 2023", "conditional",
       "Covered subcontractors: subcontracts over $1 million, except subcontracts for commercial products or services.",
       "No separate subcontracts paragraph. (b)(2): the Contractor certifies that it requires each covered subcontractor to agree not to enter into or enforce the arbitration agreements described in (b)(1). (a) defines a covered subcontractor as any entity with a subcontract valued in excess of $1 million, except a subcontract for commercial products or commercial services, including COTS items.",
       r_7006, threshold=1_000_000.0),
    _c("252.223-7008", "Prohibition of Hexavalent Chromium", "Jan 2023", "conditional",
       "Subcontracts (including commercial) for supplies, maintenance and repair services, or construction materials.",
       "(d) The Contractor shall include the substance of this clause, including this paragraph (d), in all subcontracts, including subcontracts for commercial products or commercial services, that are for supplies, maintenance and repair services, or construction materials.",
       r_7008, commercial=True),
    _c("252.225-7009", "Restriction on Acquisition of Certain Articles Containing Specialty Metals", "Jan 2023", "conditional",
       "Subcontracts (including commercial products) for items containing specialty metals. Flow paragraphs (a) through (c) and (e)(2).",
       "(e)(2) The Contractor shall insert paragraphs (a) through (c) and this paragraph (e)(2) of this clause in subcontracts, including subcontracts for commercial products, that are for items containing specialty metals to ensure compliance of the end products that the Contractor will deliver to the Government.",
       r_7009, commercial=True, portion="paragraphs (a) through (c) and (e)(2) only"),
    _c("252.225-7012", "Preference for Certain Domestic Commodities", "Apr 2022", "not_required",
       "No flowdown paragraph. The domestic-commodity rules still apply to what you deliver, so check your suppliers.",
       "The clause has no subcontracts paragraph.",
       r_not_required),
    _c("252.225-7048", "Export-Controlled Items", "Jun 2013", "mandatory",
       "All subcontracts.",
       "(e) The Contractor shall include the substance of this clause, including this paragraph (e), in all subcontracts.",
       _always),
    _c("252.226-7001", "Utilization of Indian Organizations, Indian-Owned Economic Enterprises, and Native Hawaiian Small Business Concerns", "Jan 2023", "conditional",
       "Subcontracts over $500,000.",
       "(g) The Contractor shall insert the substance of this clause, including this paragraph (g), in all subcontracts exceeding $500,000.",
       r_7001, threshold=500_000.0),
    _c("252.244-7000", "Subcontracts for Commercial Products or Commercial Services", "Nov 2023", "mandatory",
       "All subcontracts, including commercial.",
       "(c) The Contractor shall include the terms of this clause, including this paragraph (c), in subcontracts awarded under this contract, including subcontracts for the acquisition of commercial products or commercial services.",
       _always_incl_commercial, commercial=True),
    _c("252.246-7007", "Contractor Counterfeit Electronic Part Detection and Avoidance System", "Jan 2023", "conditional",
       "Subcontracts (including commercial products) for electronic parts or assemblies containing electronic parts. Flow paragraphs (a) through (e) only.",
       "(e) The Contractor shall include the substance of this clause, excluding the introductory text and including only paragraphs (a) through (e), in subcontracts, including subcontracts for commercial products, for electronic parts or assemblies containing electronic parts.",
       r_7007, commercial=True, portion="paragraphs (a) through (e) only, without the introductory text"),
    _c("252.246-7008", "Sources of Electronic Parts", "Jan 2023", "conditional",
       "Subcontracts (including commercial products) for electronic parts or assemblies containing them, unless the subcontractor is the original manufacturer.",
       "(e) The Contractor shall include the substance of this clause, including this paragraph (e), in subcontracts, including subcontracts for commercial products, that are for electronic parts or assemblies containing electronic parts, unless the subcontractor is the original manufacturer.",
       r_7008b, commercial=True),
    _c("252.247-7023", "Transportation of Supplies by Sea", "Oct 2024", "conditional",
       "Subcontracts (including commercial products) for supplies described in paragraph (c)(2) that will be shipped by sea. Full clause over the simplified acquisition threshold; paragraphs (a) through (f) and (j) at or below it.",
       "(j) In the award of subcontracts for the types of supplies described in paragraph (c)(2) of this clause, including subcontracts for commercial products, the Contractor shall flow down the requirements of this clause as follows: (1) insert the substance of this clause, including this paragraph (j), in subcontracts that exceed the simplified acquisition threshold; (2) insert the substance of paragraphs (a) through (f) of this clause, and this paragraph (j), in subcontracts at or below the simplified acquisition threshold.",
       r_7023, commercial=True, threshold=THRESHOLDS["sat"]),
]

BY_NUMBER = {c["number"]: c for c in CLAUSES}


def public(c: dict) -> dict:
    """A clause entry without the rule function."""
    return {k: v for k, v in c.items() if not k.startswith("_")}


def evaluate(number: str, sub: dict | None) -> dict:
    """Decide whether one clause flows down to the described subcontract.

    Returns the public clause fields plus flow_down: "yes" | "no" | "check" and reason.
    Unknown clause numbers come back with flow_down "check".
    """
    s = _norm(sub)
    c = BY_NUMBER.get(number)
    if not c:
        return {"number": number, "title": "", "family": "DFARS" if number.startswith("252.") else "FAR",
                "status": "unknown", "flow_down": "check", "source_url": "",
                "reason": "Not in the curated table. Check the clause text for a subcontracts paragraph.",
                "condition": "", "paragraph": "", "note": "", "portion": "", "date": "", "threshold": None, "commercial": False}
    out = public(c)
    if s["commercial"] and not c["commercial"]:
        out.update(flow_down="no", reason=(
            "Commercial subcontract: this clause is not one that must flow to commercial subcontracts "
            "(FAR 52.244-6(c)(1), 52.212-5(e)(1), DFARS 252.244-7000(a))."))
        return out
    ok, reason = c["_rule"](s)
    out.update(flow_down="check" if ok is None else ("yes" if ok else "no"), reason=reason)
    return out


def check(numbers: list[str], sub: dict | None) -> list[dict]:
    """Evaluate a list of clause numbers (deduplicated, table order first, then unknowns)."""
    seen: list[str] = []
    for n in numbers:
        n = (n or "").strip()
        if n and n not in seen:
            seen.append(n)
    order = {c["number"]: i for i, c in enumerate(CLAUSES)}
    seen.sort(key=lambda n: (order.get(n, 10_000), n))
    return [evaluate(n, sub) for n in seen]
