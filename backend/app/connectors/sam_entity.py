"""SAM.gov Entity Management API (teaming partner and vendor search).

Docs: https://open.gsa.gov/api/entity-api/

Facts this connector relies on (checked against the docs page):
- Endpoint: https://api.sam.gov/entity-information/v3/entities?api_key=... (v4 also exists).
- Filters: naicsCode (any NAICS on the registration), primaryNaics, naicsLimitedSB (NAICS where the
  entity is small), physicalAddressProvinceOrStateCode (2 letters), legalBusinessName (partial match),
  businessTypeCode, sbaBusinessTypeCode, registrationStatus=A (active).
- Pagination: page (0 based) and size, and size cannot exceed 10. page * size cannot exceed 10,000.
- includeSections: entityRegistration, coreData, assertions, pointsOfContact.
- Response: entityData[] with entityRegistration (ueiSAM, cageCode, legalBusinessName),
  coreData.entityInformation.entityURL, coreData.physicalAddress (city, stateOrProvinceCode),
  coreData.businessTypes.businessTypeList[] / sbaBusinessTypeList[], assertions.goodsAndServices
  (primaryNaics, naicsList[].naicsCode / sbaSmallBusiness), pointsOfContact.governmentBusinessPOC.
  links.nextLink is present when there is another page.
- Public keys: 10 requests/day for a non-federal personal key without a SAM.gov role, 1,000/day with a role.
  POC names and addresses are public; POC email and phone need FOUO access, so they are usually blank.

Business type codes (SAM business type table):
  QF Service-Disabled Veteran Owned Business, A5 Veteran Owned Business, 8W Woman Owned Small Business,
  8E Economically Disadvantaged WOSB, A2 Woman Owned Business, XX SBA Certified HUBZone, A6 SBA Certified
  8(a) Program Participant, JT SBA Certified 8(a) Joint Venture.
"""
from __future__ import annotations

import httpx

from .. import config

ENTITY_URL = "https://api.sam.gov/entity-information/v3/entities"
PAGE_SIZE = 10  # API maximum
SECTIONS = "entityRegistration,coreData,assertions,pointsOfContact"

# business_type option -> (query parameter, code)
BUSINESS_TYPE_FILTERS: dict[str, tuple[str, str]] = {
    "sdvosb": ("businessTypeCode", "QF"),
    "vosb": ("businessTypeCode", "A5"),
    "wosb": ("businessTypeCode", "8W"),
    "hubzone": ("sbaBusinessTypeCode", "XX"),
    "8a": ("sbaBusinessTypeCode", "A6"),
}
BUSINESS_TYPES = ["", "sdvosb", "vosb", "wosb", "hubzone", "8a", "small"]


class EntityApiError(RuntimeError):
    pass


def build_params(
    *, naics: str = "", state: str = "", business_type: str = "", q: str = "", page: int = 0, api_key: str = ""
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [
        ("api_key", api_key),
        ("registrationStatus", "A"),
        ("includeSections", SECTIONS),
        ("page", str(max(0, int(page)))),
        ("size", str(PAGE_SIZE)),
    ]
    naics = (naics or "").strip()
    bt = (business_type or "").strip().lower()
    if bt == "small":
        if not naics:
            raise EntityApiError("The 'any small business' filter needs a NAICS code (SAM decides size per NAICS).")
        params.append(("naicsLimitedSB", naics))
    elif naics:
        params.append(("naicsCode", naics))
    if bt in BUSINESS_TYPE_FILTERS:
        params.append(BUSINESS_TYPE_FILTERS[bt])
    elif bt not in ("", "any", "small"):
        raise EntityApiError(f"Unknown business type '{business_type}'. Use one of: {', '.join(b for b in BUSINESS_TYPES if b)}.")
    if state:
        params.append(("physicalAddressProvinceOrStateCode", state.strip().upper()[:2]))
    if q:
        params.append(("legalBusinessName", q.strip()))
    return params


def search(
    *,
    naics: str = "",
    state: str = "",
    business_type: str = "",
    q: str = "",
    page: int = 0,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Search active SAM registrations. Returns {total, page, size, has_more, results: [normalized]}."""
    key = api_key if api_key is not None else config.SAM_API_KEY
    if not key:
        raise EntityApiError(
            "SAM_API_KEY is not set. Create a public API key on your SAM.gov Account Details page and add it to backend/.env."
        )
    if not any([naics, state, business_type, q]):
        raise EntityApiError("Give at least one filter (NAICS, state, business type or name).")
    params = build_params(naics=naics, state=state, business_type=business_type, q=q, page=page, api_key=key)

    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        resp = client.get(ENTITY_URL, params=params)
    except httpx.HTTPError as e:
        raise EntityApiError(f"Could not reach SAM.gov: {e}") from e
    finally:
        if own:
            client.close()
    if resp.status_code == 429:
        raise EntityApiError("SAM.gov daily request limit reached for this API key. Try again tomorrow.")
    if resp.status_code in (401, 403):
        raise EntityApiError("SAM.gov rejected the API key. Check that it is current on your SAM.gov Account Details page.")
    if resp.status_code >= 400:
        try:
            j = resp.json()
            msg = j.get("detail") or j.get("message") or j.get("error", {}).get("message") or resp.text[:300]
        except Exception:
            msg = resp.text[:300]
        raise EntityApiError(f"SAM.gov returned {resp.status_code}: {msg}")
    data = resp.json()
    rows = data.get("entityData") or []
    total = data.get("totalRecords")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    has_more = bool((data.get("links") or {}).get("nextLink")) or (
        total is not None and (int(page) + 1) * PAGE_SIZE < total
    )
    return {
        "total": total,
        "page": int(page),
        "size": PAGE_SIZE,
        "has_more": has_more,
        "results": [normalize(r) for r in rows],
    }


def _codes(items: list | None, key: str) -> set[str]:
    return {str(i.get(key)).upper() for i in (items or []) if isinstance(i, dict) and i.get(key)}


def normalize(raw: dict) -> dict:
    reg = raw.get("entityRegistration") or {}
    core = raw.get("coreData") or {}
    addr = core.get("physicalAddress") or {}
    info = core.get("entityInformation") or {}
    bts = core.get("businessTypes") or {}
    gs = (raw.get("assertions") or {}).get("goodsAndServices") or {}
    pocs = raw.get("pointsOfContact") or {}

    codes = _codes(bts.get("businessTypeList"), "businessTypeCode")
    sba = _codes(bts.get("sbaBusinessTypeList"), "sbaBusinessTypeCode")
    naics_list = [n for n in (gs.get("naicsList") or []) if isinstance(n, dict)]
    naics_codes = [str(n.get("naicsCode")) for n in naics_list if n.get("naicsCode")]
    primary = str(gs.get("primaryNaics") or "")
    if primary and primary not in naics_codes:
        naics_codes.insert(0, primary)
    small: bool | None = None
    for n in naics_list:
        if str(n.get("naicsCode")) == primary and n.get("sbaSmallBusiness") in ("Y", "N"):
            small = n.get("sbaSmallBusiness") == "Y"

    poc = {}
    for k in ("governmentBusinessPOC", "electronicBusinessPOC"):
        p = pocs.get(k) or {}
        name = " ".join(x for x in [p.get("firstName"), p.get("lastName")] if x)
        if name:
            poc = {
                "name": name,
                "title": p.get("title") or "",
                "email": p.get("email") or p.get("emailAddress") or "",
                "phone": p.get("usPhone") or p.get("phoneNumber") or "",
                "role": "Government business POC" if k == "governmentBusinessPOC" else "Electronic business POC",
            }
            break

    return {
        "uei": reg.get("ueiSAM") or "",
        "cage": reg.get("cageCode") or "",
        "name": reg.get("legalBusinessName") or "",
        "dba": reg.get("dbaName") or "",
        "city": addr.get("city") or "",
        "state": addr.get("stateOrProvinceCode") or "",
        "naics_codes": naics_codes,
        "primary_naics": primary,
        "business_types": {
            "SB": small,
            "SDVOSB": "QF" in codes,
            "VOSB": "A5" in codes or "QF" in codes,
            "WOSB": bool({"8W", "8E"} & codes) or bool({"8W", "8E"} & sba),
            "HUBZone": "XX" in sba or "XX" in codes,
            "8A": bool({"A6", "JT"} & sba) or bool({"A6", "JT"} & codes),
        },
        "is_manufacturer": "MF" in codes or (core.get("generalInformation") or {}).get("organizationStructureCode") == "MF",
        "website": info.get("entityURL") or "",
        "registration_expires": reg.get("registrationExpirationDate") or "",
        "poc": poc,
    }
