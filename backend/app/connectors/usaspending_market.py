"""USAspending.gov queries for the recompete tracker and buyer analytics. No API key required.

Verified 2026-10-09 against the API contracts in github.com/fedspendingtransparency/usaspending-api
(usaspending_api/api_contracts/contracts/v2/...) and live calls to https://api.usaspending.gov:

- POST /api/v2/search/spending_by_award/  body {filters, fields, limit (max 100), page, sort, order}.
  Response {results: [...], page_metadata: {page, hasNext}}. Contract fields used: "Award ID", "Recipient Name",
  "Recipient UEI", "Award Amount", "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency",
  "Contract Award Type", "NAICS" ({code, description}), "PSC" ({code, description}), "Description",
  "Last Modified Date", "generated_internal_id". "End Date" is the period of performance current end date
  (matches period_of_performance.end_date on the award detail). There is no filter on end date, so the
  recompete search sorts by "End Date" descending and pages down to the window.
- time_period filter without date_type: start_date is compared to action_date (latest transaction) and
  end_date to date_signed. Searches cannot start earlier than 2007-10-01.
- POST /api/v2/search/spending_by_category/{category}/ with categories awarding_subagency and recipient
  (results: name, code, amount; recipient rows also carry uei and recipient_id). There is no awarding office
  category, so offices come from award detail calls on a sample of the largest awards.
- POST /api/v2/search/spending_over_time/ body {group: "fiscal_year", filters}; results [{time_period:
  {fiscal_year}, aggregated_amount, Contract_Obligations, ...}]. Amounts are obligations from transactions.
- POST /api/v2/search/spending_by_award_count/ body {filters}; results {contracts, idvs, ...}.
- GET /api/v2/awards/{generated_internal_id}/: awarding_agency.office_agency_name, period_of_performance
  {start_date, end_date, potential_end_date}, latest_transaction_contract_data {type_set_aside,
  type_set_aside_description, extent_competed, extent_competed_description, number_of_offers_received,
  solicitation_identifier, solicitation_procedures_description}, parent_award {piid, ...}, base_and_all_options,
  total_obligation, place_of_performance {city_name, state_code}.
- Filters: award_type_codes ["A","B","C","D"] (contracts), naics_codes and psc_codes as arrays of codes
  (a 2 digit FSC like "53" matches every PSC under it), set_aside_type_codes, award_amounts [{lower_bound}],
  agencies [{type: "awarding", tier: "toptier" | "subtier", name, toptier_name}].
- Set-aside codes and labels: usaspending-website src/js/dataMapping/search/contractFields.js.
"""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Protocol

import httpx

API_BASE = "https://api.usaspending.gov/api/v2"
AWARD_PAGE = "https://www.usaspending.gov/award/"
CONTRACT_TYPES = ["A", "B", "C", "D"]
EARLIEST_SEARCH_DATE = date(2007, 10, 1)

SET_ASIDE_LABELS = {
    "8AN": "8(a) Sole Source",
    "HS3": "8(a) with HUBZone Preference",
    "8A": "8(a) Competed",
    "BI": "Buy Indian",
    "HS2Civ": "Combination HUBZone and 8(a)",
    "EDWOSB": "Economically-Disadvantaged Women-Owned Small Business",
    "EDWOSBSS": "Economically Disadvantaged Women Owned Small Business Sole Source",
    "ESB": "Emerging Small Business Set Aside",
    "HMP": "HBCU or MI Set Aside - Partial",
    "HMT": "HBCU or MI Set Aside - Total",
    "HZC": "HUBZone Set Aside",
    "HZS": "HUBZone Sole Source",
    "ISEE": "Indian Economic Enterprise",
    "ISBEE": "Indian Small Business Economic Enterprise",
    "NONE": "No Set Aside Used",
    "RSBCiv": "Reserved for Small Business $2,501 to $100K",
    "8ACCiv": "SDB Set Aside 8(a)",
    "SDVOSBS": "SDVOSB Sole Source",
    "SDVOSBC": "Service-Disabled Veteran-Owned Small Business Set Aside",
    "SBP": "Small Business Set Aside - Partial",
    "SBA": "Small Business Set Aside - Total",
    "VSBCiv": "Very Small Business Set Aside",
    "VSA": "Veteran Set Aside",
    "VSS": "Veteran Sole Source",
    "WOSB": "Women-Owned Small Business",
    "WOSBSS": "Women Owned Small Business Sole Source",
}
# Every small-business-only set-aside code above (excludes NONE, Buy Indian, Indian Economic Enterprise and HBCU/MI).
SMALL_BUSINESS_SET_ASIDES = ["SBA", "SBP", "8A", "8AN", "HS3", "HS2Civ", "8ACCiv", "HZC", "HZS", "SDVOSBC", "SDVOSBS",
                             "WOSB", "WOSBSS", "EDWOSB", "EDWOSBSS", "VSA", "VSS", "ESB", "RSBCiv", "VSBCiv", "ISBEE"]
SDVOSB_SET_ASIDES = ["SDVOSBC", "SDVOSBS"]
SET_ASIDE_GROUPS = {
    "sdvosb": SDVOSB_SET_ASIDES,
    "veteran": ["VSA", "VSS", "SDVOSBC", "SDVOSBS"],
    "small_business": SMALL_BUSINESS_SET_ASIDES,
    "none": ["NONE"],
}

AWARD_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "Award Amount", "Start Date", "End Date",
    "Awarding Agency", "Awarding Sub Agency", "Contract Award Type", "NAICS", "PSC", "Description",
    "Last Modified Date", "generated_internal_id",
]

Request = tuple[str, str, dict | None]  # (method, path under API_BASE, json body)


class Fetcher(Protocol):
    def many(self, reqs: list[Request]) -> list[dict]: ...


class HttpFetcher:
    """Runs requests against USAspending with a few in parallel. Paths are relative to API_BASE."""

    def __init__(self, client: httpx.Client | None = None, workers: int = 4):
        self.client = client or httpx.Client(timeout=90)
        self.workers = workers

    def call(self, req: Request) -> dict:
        method, path, body = req
        url = API_BASE + path
        resp = self.client.post(url, json=body) if method == "POST" else self.client.get(url)
        if resp.status_code >= 400:
            raise RuntimeError(f"USAspending returned {resp.status_code} for {path}: {resp.text[:300]}")
        return resp.json()

    def many(self, reqs: list[Request]) -> list[dict]:
        if len(reqs) <= 1:
            return [self.call(r) for r in reqs]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(self.call, reqs))

    def close(self) -> None:
        self.client.close()


# ------------------------------------------------------------------ dates
def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def recompete_window(today: date, months_from: int = 6, months_to: int = 18) -> tuple[date, date]:
    """Period of performance end dates to look for: months_from to months_to months after today."""
    if months_to < months_from:
        months_from, months_to = months_to, months_from
    return add_months(today, months_from), add_months(today, months_to)


def fiscal_year(d: date) -> int:
    """Federal fiscal year: FY2027 runs 2026-10-01 to 2027-09-30."""
    return d.year + 1 if d.month >= 10 else d.year


def fy_bounds(fy: int) -> tuple[date, date]:
    return date(fy - 1, 10, 1), date(fy, 9, 30)


def last_complete_fys(today: date, n: int) -> list[int]:
    """The n most recent fiscal years that have ended, oldest first."""
    last = fiscal_year(today) - 1
    return list(range(last - max(1, n) + 1, last + 1))


# ------------------------------------------------------------------ filters
def fsc_prefixes(nsn_watchlist: list[str]) -> list[str]:
    """FSC codes from NSN watchlist entries ("5340", "5340-01-123-4567", "534001...")."""
    out = []
    for item in nsn_watchlist or []:
        digits = "".join(ch for ch in str(item) if ch.isdigit())
        if len(digits) >= 4 and digits[:4] not in out:
            out.append(digits[:4])
    return out


def base_filters(*, naics: list[str] | None = None, psc: list[str] | None = None, start: date, end: date,
                 agency: str = "", sub_agency: str = "", set_asides: list[str] | None = None,
                 min_value: float | None = None) -> dict:
    f: dict = {
        "award_type_codes": CONTRACT_TYPES,
        "time_period": [{"start_date": max(start, EARLIEST_SEARCH_DATE).isoformat(), "end_date": end.isoformat()}],
    }
    if naics:
        f["naics_codes"] = list(naics)
    if psc:
        f["psc_codes"] = list(psc)
    if set_asides:
        f["set_aside_type_codes"] = list(set_asides)
    if min_value:
        f["award_amounts"] = [{"lower_bound": float(min_value)}]
    # Agency objects in one list are ORed, so a sub-agency is sent alone, scoped by toptier_name.
    if sub_agency:
        sub = {"type": "awarding", "tier": "subtier", "name": sub_agency}
        if agency:
            sub["toptier_name"] = agency
        f["agencies"] = [sub]
    elif agency:
        f["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]
    return f


def _code(v) -> str:
    return (v.get("code") or "") if isinstance(v, dict) else (v or "")


def normalize_award(r: dict) -> dict:
    gid = r.get("generated_internal_id") or ""
    return {
        "generated_internal_id": gid,
        "award_id": r.get("Award ID") or "",
        "recipient": r.get("Recipient Name") or "",
        "recipient_uei": r.get("Recipient UEI") or "",
        "amount": float(r.get("Award Amount") or 0),
        "start_date": (r.get("Start Date") or "")[:10],
        "end_date": (r.get("End Date") or "")[:10],
        "agency": r.get("Awarding Agency") or "",
        "sub_agency": r.get("Awarding Sub Agency") or "",
        "award_type": r.get("Contract Award Type") or "",
        "naics": _code(r.get("NAICS")),
        "psc": _code(r.get("PSC")),
        "description": r.get("Description") or "",
        "last_modified": (r.get("Last Modified Date") or "")[:10],
        "url": AWARD_PAGE + gid if gid else "",
    }


# ------------------------------------------------------------------ recompetes
def recompete_bodies_page(filters: dict, page: int) -> dict:
    return {"filters": filters, "fields": AWARD_FIELDS, "limit": 100, "page": page, "sort": "End Date", "order": "desc"}


def search_recompetes(fetch: Fetcher, *, naics: list[str], psc: list[str], window: tuple[date, date], today: date,
                      agency: str = "", min_value: float | None = None, set_asides: list[str] | None = None,
                      lookback_years: int = 5, max_pages: int = 10) -> dict:
    """Contracts whose current end date falls inside window.

    NAICS and PSC lists are searched separately and merged (USAspending ANDs them inside one filter).
    Only awards with a transaction in the last lookback_years are considered.
    """
    w_start, w_end = window
    start = today - timedelta(days=365 * lookback_years)
    dims = []
    if naics:
        dims.append({"naics": naics})
    if psc:
        dims.append({"psc": psc})
    found: dict[str, dict] = {}
    truncated = False
    pages_used = 0
    lowest_scanned = ""
    for dim in dims:
        filters = base_filters(naics=dim.get("naics"), psc=dim.get("psc"), start=start, end=today, agency=agency,
                               set_asides=set_asides, min_value=min_value)
        for page in range(1, max_pages + 1):
            data = fetch.many([("POST", "/search/spending_by_award/", recompete_bodies_page(filters, page))])[0]
            pages_used += 1
            rows = [normalize_award(r) for r in data.get("results") or []]
            for a in rows:
                if a["end_date"] and w_start.isoformat() <= a["end_date"] <= w_end.isoformat() and a["generated_internal_id"]:
                    a["matched_on"] = "naics" if "naics" in dim else "psc"
                    found.setdefault(a["generated_internal_id"], a)
            ends = [a["end_date"] for a in rows if a["end_date"]]
            if ends and (not lowest_scanned or min(ends) < lowest_scanned):
                lowest_scanned = min(ends)
            if not (data.get("page_metadata") or {}).get("hasNext") or (ends and min(ends) < w_start.isoformat()):
                break
        else:
            truncated = True
    results = sorted(found.values(), key=lambda a: (a["end_date"], -a["amount"]))
    return {"results": results, "truncated": truncated, "pages": pages_used, "scanned_to": lowest_scanned}


def normalize_detail(d: dict) -> dict:
    aa = d.get("awarding_agency") or {}
    pop = d.get("period_of_performance") or {}
    tx = d.get("latest_transaction_contract_data") or {}
    parent = d.get("parent_award") or {}
    place = d.get("place_of_performance") or {}
    gid = d.get("generated_unique_award_id") or ""
    sa_code = tx.get("type_set_aside") or ""
    return {
        "generated_internal_id": gid,
        "piid": d.get("piid") or "",
        "type": d.get("type_description") or "",
        "description": d.get("description") or "",
        "agency": (aa.get("toptier_agency") or {}).get("name") or "",
        "sub_agency": (aa.get("subtier_agency") or {}).get("name") or "",
        "office": aa.get("office_agency_name") or "",
        "start_date": (pop.get("start_date") or "")[:10],
        "end_date": (pop.get("end_date") or "")[:10],
        "potential_end_date": (pop.get("potential_end_date") or "")[:10],
        "total_obligation": d.get("total_obligation"),
        "base_and_all_options": d.get("base_and_all_options"),
        "set_aside_code": sa_code,
        "set_aside": tx.get("type_set_aside_description") or SET_ASIDE_LABELS.get(sa_code, sa_code),
        "extent_competed_code": tx.get("extent_competed") or "",
        "extent_competed": tx.get("extent_competed_description") or "",
        "offers": tx.get("number_of_offers_received") or "",
        "solicitation_id": tx.get("solicitation_identifier") or "",
        "solicitation_procedures": tx.get("solicitation_procedures_description") or "",
        "parent_piid": parent.get("piid") or "",
        "place": ", ".join(x for x in [place.get("city_name"), place.get("state_code")] if x),
        "url": AWARD_PAGE + gid if gid else "",
    }


def award_detail(fetch: Fetcher, generated_internal_id: str) -> dict:
    return normalize_detail(fetch.many([("GET", f"/awards/{generated_internal_id}/", None)])[0])


# ------------------------------------------------------------------ buyer analytics
def _sot(filters: dict) -> Request:
    return ("POST", "/search/spending_over_time/", {"group": "fiscal_year", "filters": filters})


def _count(filters: dict) -> Request:
    return ("POST", "/search/spending_by_award_count/", {"filters": filters})


def _by_fy(data: dict) -> dict[int, float]:
    out = {}
    for r in data.get("results") or []:
        fy = (r.get("time_period") or {}).get("fiscal_year")
        if fy:
            out[int(fy)] = float(r.get("Contract_Obligations", r.get("aggregated_amount")) or 0)
    return out


def _contracts(data: dict) -> int:
    return int((data.get("results") or {}).get("contracts") or 0)


def buyer_analytics(fetch: Fetcher, *, naics: list[str], psc: list[str], fys: list[int], top: int = 10,
                    subagency_counts: int = 8) -> dict:
    start, _ = fy_bounds(fys[0])
    _, end = fy_bounds(fys[-1])
    common = {"naics": naics, "psc": psc}
    f_all = base_filters(**common, start=start, end=end)
    f_sb = base_filters(**common, start=start, end=end, set_asides=SMALL_BUSINESS_SET_ASIDES)
    f_sd = base_filters(**common, start=start, end=end, set_asides=SDVOSB_SET_ASIDES)

    reqs: list[Request] = [_sot(f_all), _sot(f_sb), _sot(f_sd),
                           ("POST", "/search/spending_by_category/awarding_subagency/", {"filters": f_all, "limit": top, "page": 1}),
                           ("POST", "/search/spending_by_category/recipient/", {"filters": f_all, "limit": top, "page": 1})]
    for fy in fys:
        s, e = fy_bounds(fy)
        reqs += [_count(base_filters(**common, start=s, end=e)),
                 _count(base_filters(**common, start=s, end=e, set_asides=SMALL_BUSINESS_SET_ASIDES)),
                 _count(base_filters(**common, start=s, end=e, set_asides=SDVOSB_SET_ASIDES))]
    res = fetch.many(reqs)
    tot, sb, sd = _by_fy(res[0]), _by_fy(res[1]), _by_fy(res[2])
    subs_raw, recips_raw = res[3].get("results") or [], res[4].get("results") or []

    years = []
    for i, fy in enumerate(fys):
        c_all, c_sb, c_sd = (_contracts(res[5 + 3 * i + k]) for k in range(3))
        dollars = tot.get(fy, 0.0)
        years.append({
            "fiscal_year": fy, "obligations": dollars, "awards": c_all,
            "sb_obligations": sb.get(fy, 0.0), "sdvosb_obligations": sd.get(fy, 0.0),
            "sb_awards": c_sb, "sdvosb_awards": c_sd,
            "avg_award": dollars / c_all if c_all else None,
        })

    subs = [{"name": r.get("name") or "", "code": r.get("code") or "", "agency": r.get("agency_name") or "",
             "amount": float(r.get("amount") or 0)} for r in subs_raw]
    count_reqs = [_count(base_filters(**common, start=start, end=end, agency=s["agency"], sub_agency=s["name"]))
                  for s in subs[:subagency_counts] if s["name"]]
    for s, data in zip([s for s in subs[:subagency_counts] if s["name"]], fetch.many(count_reqs)):
        s["awards"] = _contracts(data)
        s["avg_award"] = s["amount"] / s["awards"] if s["awards"] else None

    recips = [{"name": r.get("name") or "", "uei": r.get("uei") or "", "recipient_id": r.get("recipient_id") or "",
               "amount": float(r.get("amount") or 0)} for r in recips_raw]
    total = sum(y["obligations"] for y in years)
    awards = sum(y["awards"] for y in years)
    sb_total = sum(y["sb_obligations"] for y in years)
    sd_total = sum(y["sdvosb_obligations"] for y in years)
    sb_awards = sum(y["sb_awards"] for y in years)
    sd_awards = sum(y["sdvosb_awards"] for y in years)
    return {
        "fiscal_years": fys, "range": {"start": start.isoformat(), "end": end.isoformat()},
        "years": years, "sub_agencies": subs, "recipients": recips,
        "totals": {
            "obligations": total, "awards": awards, "avg_award": total / awards if awards else None,
            "sb_share_dollars": sb_total / total if total else None, "sdvosb_share_dollars": sd_total / total if total else None,
            "sb_share_awards": sb_awards / awards if awards else None, "sdvosb_share_awards": sd_awards / awards if awards else None,
        },
    }


def office_sample(fetch: Fetcher, *, naics: list[str], psc: list[str], fys: list[int], sample: int = 20) -> dict:
    """Awarding offices behind the largest awards in the range (USAspending has no office aggregate)."""
    start, _ = fy_bounds(fys[0])
    _, end = fy_bounds(fys[-1])
    f = base_filters(naics=naics, psc=psc, start=start, end=end)
    body = {"filters": f, "fields": AWARD_FIELDS, "limit": min(100, max(1, sample)), "page": 1,
            "sort": "Award Amount", "order": "desc"}
    awards = [normalize_award(r) for r in (fetch.many([("POST", "/search/spending_by_award/", body)])[0].get("results") or [])]
    awards = [a for a in awards if a["generated_internal_id"]][:sample]
    details = fetch.many([("GET", f"/awards/{a['generated_internal_id']}/", None) for a in awards])
    agg: dict[tuple, dict] = {}
    for a, d in zip(awards, details):
        nd = normalize_detail(d)
        key = (nd["office"] or "(office not reported)", nd["sub_agency"] or a["sub_agency"])
        row = agg.setdefault(key, {"office": key[0], "sub_agency": key[1], "agency": nd["agency"] or a["agency"],
                                   "amount": 0.0, "awards": 0, "set_asides": {}})
        row["amount"] += a["amount"]
        row["awards"] += 1
        if nd["set_aside_code"]:
            row["set_asides"][nd["set_aside_code"]] = row["set_asides"].get(nd["set_aside_code"], 0) + 1
    offices = sorted(agg.values(), key=lambda r: r["amount"], reverse=True)
    return {"sample_size": len(awards), "offices": offices}
