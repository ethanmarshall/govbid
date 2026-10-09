"""USAspending.gov award search, used for competitor and pricing intelligence.

Docs: https://github.com/fedspendingtransparency/usaspending-api (POST /api/v2/search/spending_by_award/)
No API key required.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import httpx

from ..config import USASPENDING_URL

CONTRACT_TYPES = ["A", "B", "C", "D"]
FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Award Amount",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Description",
    "NAICS",
    "PSC",
    "generated_internal_id",
]


def search_awards(
    *,
    naics: list[str] | None = None,
    psc: list[str] | None = None,
    keywords: list[str] | None = None,
    agency: str | None = None,
    set_aside_codes: list[str] | None = None,
    years_back: int = 3,
    limit: int = 100,
    pages: int = 2,
    client: httpx.Client | None = None,
) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=365 * max(1, years_back))
    filters: dict = {
        "award_type_codes": CONTRACT_TYPES,
        "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
    }
    if naics:
        filters["naics_codes"] = naics
    if psc:
        filters["psc_codes"] = psc
    if keywords:
        filters["keywords"] = keywords
    if set_aside_codes:
        filters["set_aside_type_codes"] = set_aside_codes
    if agency:
        filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]

    own_client = client is None
    client = client or httpx.Client(timeout=60)
    out: list[dict] = []
    try:
        for page in range(1, pages + 1):
            body = {
                "filters": filters,
                "fields": FIELDS,
                "limit": min(limit, 100),
                "page": page,
                "sort": "Award Amount",
                "order": "desc",
            }
            resp = client.post(USASPENDING_URL, json=body)
            if resp.status_code >= 400:
                raise RuntimeError(f"USAspending returned {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            out.extend(data.get("results") or [])
            if not (data.get("page_metadata") or {}).get("hasNext"):
                break
    finally:
        if own_client:
            client.close()
    return [_normalize(r) for r in out]


def _normalize(r: dict) -> dict:
    naics = r.get("NAICS")
    psc = r.get("PSC")
    gid = r.get("generated_internal_id") or ""
    return {
        "award_id": r.get("Award ID") or "",
        "recipient": r.get("Recipient Name") or "",
        "recipient_uei": r.get("Recipient UEI") or "",
        "amount": float(r.get("Award Amount") or 0),
        "start_date": r.get("Start Date") or "",
        "end_date": r.get("End Date") or "",
        "agency": r.get("Awarding Agency") or "",
        "sub_agency": r.get("Awarding Sub Agency") or "",
        "description": r.get("Description") or "",
        "naics": naics.get("code") if isinstance(naics, dict) else (naics or ""),
        "psc": psc.get("code") if isinstance(psc, dict) else (psc or ""),
        "url": f"https://www.usaspending.gov/award/{gid}" if gid else "",
    }


def top_competitors(awards: list[dict], n: int = 15) -> list[dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"recipient": "", "uei": "", "total": 0.0, "count": 0, "agencies": set()})
    for a in awards:
        key = a["recipient_uei"] or a["recipient"]
        row = agg[key]
        row["recipient"] = a["recipient"]
        row["uei"] = a["recipient_uei"]
        row["total"] += a["amount"]
        row["count"] += 1
        if a["agency"]:
            row["agencies"].add(a["agency"])
    ranked = sorted(agg.values(), key=lambda x: x["total"], reverse=True)[:n]
    for r in ranked:
        r["agencies"] = sorted(r["agencies"])
    return ranked
