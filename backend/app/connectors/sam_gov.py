"""SAM.gov Get Opportunities Public API (v2).

Docs: https://open.gsa.gov/api/get-opportunities-public-api/

Notes that shape this connector:
- postedFrom/postedTo are required (MM/dd/yyyy) and can span at most one year.
- limit max is 1000 per page; paginate with offset.
- Daily request quotas are low for non-federal keys, so we query once per NAICS code
  and fetch notice descriptions lazily (each description is another request).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import httpx

from ..config import SAM_API_KEY, SAM_SEARCH_URL

# Notice types worth bidding on or tracking. Award notices (a) are excluded.
# o = Solicitation, k = Combined Synopsis/Solicitation, p = Presolicitation, r = Sources Sought, s = Special Notice
DEFAULT_PTYPES = ["o", "k", "p", "r"]


class SamApiError(RuntimeError):
    pass


def _fmt(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def search(
    *,
    days_back: int = 14,
    naics: str | None = None,
    set_aside: str | None = None,
    ptypes: Iterable[str] = DEFAULT_PTYPES,
    state: str | None = None,
    keyword_title: str | None = None,
    solicitation_number: str | None = None,
    max_pages: int = 3,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[list[dict], int]:
    """Return (raw notices, requests_used)."""
    key = api_key or SAM_API_KEY
    if not key:
        raise SamApiError("SAM_API_KEY is not set. Create a public API key on your SAM.gov Account Details page.")

    days_back = max(1, min(days_back, 364))
    today = date.today()
    params: list[tuple[str, str]] = [
        ("api_key", key),
        ("postedFrom", _fmt(today - timedelta(days=days_back))),
        ("postedTo", _fmt(today)),
        ("limit", "1000"),
    ]
    for p in ptypes:
        params.append(("ptype", p))
    if naics:
        params.append(("ncode", naics))
    if set_aside:
        params.append(("typeOfSetAside", set_aside))
    if state:
        params.append(("state", state))
    if keyword_title:
        params.append(("title", keyword_title))
    if solicitation_number:
        params.append(("solnum", solicitation_number))

    own_client = client is None
    client = client or httpx.Client(timeout=60)
    results: list[dict] = []
    seen: set[str] = set()
    requests_used = 0
    offset = 0
    try:
        for _ in range(max_pages):
            # The docs call offset a "page index", but in practice it behaves as a record offset.
            # We advance by records and de-duplicate on noticeId so either behavior is safe.
            resp = client.get(SAM_SEARCH_URL, params=params + [("offset", str(offset))])
            requests_used += 1
            if resp.status_code == 404:
                break  # SAM returns 404 for "no data found"
            if resp.status_code == 429:
                raise SamApiError("SAM.gov daily request limit reached. Try again tomorrow or narrow your sync.")
            if resp.status_code >= 400:
                raise SamApiError(f"SAM.gov returned {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            batch = body.get("opportunitiesData") or []
            new = [n for n in batch if n.get("noticeId") not in seen]
            seen.update(n.get("noticeId") for n in new)
            results.extend(new)
            total = int(body.get("totalRecords") or 0)
            if not new or len(results) >= total:
                break
            offset += len(batch)
    finally:
        if own_client:
            client.close()
    return results, requests_used


def fetch_description(description_url: str, api_key: str | None = None, client: httpx.Client | None = None) -> str:
    """Notice descriptions are a separate call that needs the API key appended."""
    key = api_key or SAM_API_KEY
    if not description_url or description_url == "null" or not key:
        return ""
    own_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        resp = client.get(description_url, params={"api_key": key})
        if resp.status_code >= 400:
            return ""
        try:
            data = resp.json()
            return data.get("description", "") if isinstance(data, dict) else str(data)
        except ValueError:
            return resp.text
    finally:
        if own_client:
            client.close()


def _s(v) -> str:
    if v is None or v == "null":
        return ""
    return str(v).strip()


def _place(pop: dict | None) -> tuple[str, str]:
    if not pop:
        return "", ""
    city = (pop.get("city") or {}).get("name", "") if isinstance(pop.get("city"), dict) else _s(pop.get("city"))
    st = pop.get("state") or {}
    state_code = st.get("code", "") if isinstance(st, dict) else _s(st)
    parts = [p for p in (city, state_code, _s(pop.get("zip"))) if p]
    return ", ".join(parts), state_code[:2] if state_code else ""


def _dedupe_path(path: str) -> str:
    """'VA.VA.NCO 10' -> 'VA / NCO 10' (SAM repeats the department as the sub-tier)."""
    parts: list[str] = []
    for p in (x.strip() for x in path.split(".")):
        if p and (not parts or parts[-1] != p):
            parts.append(p)
    return " / ".join(parts)


def normalize(n: dict) -> dict:
    """Map a raw SAM notice to Opportunity column values."""
    place, pop_state = _place(n.get("placeOfPerformance"))
    agency = _s(n.get("fullParentPathName")) or " / ".join(
        x for x in (_s(n.get("department")), _s(n.get("subTier")), _s(n.get("office"))) if x
    )
    notice_id = _s(n.get("noticeId"))
    award = n.get("award") or {}
    amount = None
    try:
        amount = float(award.get("amount")) if award.get("amount") else None
    except (TypeError, ValueError):
        amount = None
    contacts = [
        {
            "name": _s(c.get("fullName") or c.get("fullname")),
            "title": _s(c.get("title")),
            "email": _s(c.get("email")),
            "phone": _s(c.get("phone")),
            "type": _s(c.get("type")),
        }
        for c in (n.get("pointOfContact") or [])
        if isinstance(c, dict)
    ]
    return {
        "source": "sam",
        "external_id": notice_id,
        "solicitation_number": _s(n.get("solicitationNumber")),
        "title": _s(n.get("title")),
        "agency": _dedupe_path(agency),
        "notice_type": _s(n.get("type")),
        "set_aside_code": _s(n.get("typeOfSetAside") or n.get("setAsideCode")).upper(),
        "set_aside_desc": _s(n.get("typeOfSetAsideDescription") or n.get("setAside")),
        "naics": _s(n.get("naicsCode")),
        "psc": _s(n.get("classificationCode")),
        "posted_date": _s(n.get("postedDate"))[:10],
        "response_deadline": _s(n.get("responseDeadLine") or n.get("reponseDeadLine")),
        "place_of_performance": place,
        "pop_state": pop_state,
        "url": f"https://sam.gov/opp/{notice_id}/view" if notice_id else "",
        "description_url": _s(n.get("description")),
        "contacts": contacts,
        "attachments": [u for u in (n.get("resourceLinks") or []) if u],
        "estimated_value": amount,
        "active": _s(n.get("active")).lower() != "no",
        "raw": n,
    }
