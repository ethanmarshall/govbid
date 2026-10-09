"""Decide whether the company can bid on an opportunity, based on its set-aside.

Statuses:
  eligible_now             You can bid today.
  eligible_once_certified  Reserved for a certification you have applied for but do not hold yet.
  not_eligible             Reserved for a program you are not in.
Every result also carries a list of warnings (SAM not active, NAICS mismatch, size standard unknown).

Certification statuses stored on the profile: "certified", "pending", or "none".
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Set-aside code (SAM.gov typeOfSetAside values) -> label and the certifications that satisfy it.
# A set-aside is satisfied when ANY listed certification is held.
SET_ASIDES: dict[str, dict] = {
    "": {"label": "Unrestricted / full and open", "certs": None},
    "NONE": {"label": "Unrestricted / full and open", "certs": None},
    "SBA": {"label": "Total Small Business Set-Aside (FAR 19.5)", "certs": ["SB"]},
    "SBP": {"label": "Partial Small Business Set-Aside (FAR 19.5)", "certs": ["SB"]},
    "8A": {"label": "8(a) Set-Aside (FAR 19.8)", "certs": ["8A"]},
    "8AN": {"label": "8(a) Sole Source (FAR 19.8)", "certs": ["8A"]},
    "HZC": {"label": "HUBZone Set-Aside (FAR 19.13)", "certs": ["HUBZONE"]},
    "HZS": {"label": "HUBZone Sole Source (FAR 19.13)", "certs": ["HUBZONE"]},
    "SDVOSBC": {"label": "SDVOSB Set-Aside (FAR 19.14)", "certs": ["SDVOSB"]},
    "SDVOSBS": {"label": "SDVOSB Sole Source (FAR 19.14)", "certs": ["SDVOSB"]},
    "WOSB": {"label": "WOSB Program Set-Aside (FAR 19.15)", "certs": ["WOSB", "EDWOSB"]},
    "WOSBSS": {"label": "WOSB Program Sole Source (FAR 19.15)", "certs": ["WOSB", "EDWOSB"]},
    "EDWOSB": {"label": "EDWOSB Program Set-Aside (FAR 19.15)", "certs": ["EDWOSB"]},
    "EDWOSBSS": {"label": "EDWOSB Program Sole Source (FAR 19.15)", "certs": ["EDWOSB"]},
    "LAS": {"label": "Local Area Set-Aside (FAR 26.2)", "certs": None, "warning": "Local area set-aside: confirm your business is located in the named disaster area."},
    "IEE": {"label": "Indian Economic Enterprise Set-Aside (DOI)", "certs": ["IEE"]},
    "ISBEE": {"label": "Indian Small Business Economic Enterprise Set-Aside (DOI)", "certs": ["IEE"]},
    "BICIV": {"label": "Buy Indian Set-Aside (IHS)", "certs": ["IEE"]},
    # VA Vets First. A certified SDVOSB also qualifies for VOSB set-asides at the VA.
    "VSA": {"label": "Veteran-Owned Small Business Set-Aside (VA)", "certs": ["VOSB", "SDVOSB"]},
    "VSS": {"label": "Veteran-Owned Small Business Sole Source (VA)", "certs": ["VOSB", "SDVOSB"]},
}

SMALL_BUSINESS_PROGRAMS = {"SB", "8A", "HUBZONE", "SDVOSB", "VOSB", "WOSB", "EDWOSB", "IEE"}

CERT_LABELS = {
    "SB": "Small business (self-represented in SAM)",
    "SDVOSB": "SDVOSB (SBA VetCert)",
    "VOSB": "VOSB (SBA VetCert)",
    "8A": "8(a) Business Development",
    "HUBZONE": "HUBZone",
    "WOSB": "WOSB",
    "EDWOSB": "EDWOSB",
    "IEE": "Indian Economic Enterprise",
}


@dataclass
class EligibilityResult:
    status: str
    set_aside_label: str
    reason: str
    warnings: list[str] = field(default_factory=list)
    naics_match: bool | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "set_aside_label": self.set_aside_label,
            "reason": self.reason,
            "warnings": self.warnings,
            "naics_match": self.naics_match,
        }


def normalize_set_aside(code: str | None) -> str:
    code = (code or "").strip().upper()
    return "BICIV" if code == "BICIV" else code


def evaluate(opp_set_aside: str | None, opp_naics: str | None, profile) -> EligibilityResult:
    """profile: CompanyProfile or any object with the same attributes (None means no profile yet)."""
    code = normalize_set_aside(opp_set_aside)
    rule = SET_ASIDES.get(code)
    warnings: list[str] = []

    certs: dict = dict(getattr(profile, "certifications", None) or {})
    naics_list: list = list(getattr(profile, "naics_codes", None) or [])
    small_map: dict = dict(getattr(profile, "small_under_naics", None) or {})
    sam_status = getattr(profile, "sam_status", "not_registered") if profile else "not_registered"

    if sam_status != "active":
        warnings.append("Your SAM.gov registration is not marked active. You must be active in SAM to receive an award.")

    naics = (opp_naics or "").strip()
    naics_match: bool | None = None
    if naics and naics_list:
        naics_match = naics in naics_list
        if not naics_match:
            warnings.append(f"NAICS {naics} is not in your profile's NAICS codes.")

    if rule is None:
        return EligibilityResult(
            status="eligible_now" if not code else "not_eligible",
            set_aside_label=f"Unknown set-aside code '{code}'",
            reason="Set-aside code not recognized. Read the solicitation to confirm eligibility.",
            warnings=warnings + ["Unrecognized set-aside code."],
            naics_match=naics_match,
        )

    if rule.get("warning"):
        warnings.append(rule["warning"])

    required = rule["certs"]
    if required is None:
        return EligibilityResult("eligible_now", rule["label"], "Open to all responsible offerors.", warnings, naics_match)

    # Every set-aside here is a small business program, so size under the opportunity NAICS matters.
    if naics:
        small = small_map.get(naics)
        if small is False:
            return EligibilityResult(
                "not_eligible",
                rule["label"],
                f"You marked your business as not small under NAICS {naics}.",
                warnings,
                naics_match,
            )
        if small is None:
            warnings.append(f"Confirm you are small under the SBA size standard for NAICS {naics}.")

    statuses = [_cert_status(certs, c) for c in required]
    if "certified" in statuses:
        held = required[statuses.index("certified")]
        return EligibilityResult("eligible_now", rule["label"], f"You hold {CERT_LABELS.get(held, held)}.", warnings, naics_match)
    if "pending" in statuses:
        pend = required[statuses.index("pending")]
        reason = f"Requires {CERT_LABELS.get(pend, pend)}. Your application is pending; you can bid once it is approved."
        if pend in ("SDVOSB", "VOSB"):
            reason += " A pending VetCert application filed after the 2023 grace period does not let you bid on these set-asides yet."
        return EligibilityResult("eligible_once_certified", rule["label"], reason, warnings, naics_match)

    need = " or ".join(CERT_LABELS.get(c, c) for c in required)
    return EligibilityResult("not_eligible", rule["label"], f"Requires {need}.", warnings, naics_match)


def _cert_status(certs: dict, cert: str) -> str:
    if cert == "SB":
        # Small business status is self-represented; holding any small-business program implies it.
        if certs.get("SB") in ("certified", "pending"):
            return certs["SB"]
        if any(certs.get(c) == "certified" for c in SMALL_BUSINESS_PROGRAMS - {"SB"}):
            return "certified"
        return certs.get("SB", "none")
    return certs.get(cert, "none")
