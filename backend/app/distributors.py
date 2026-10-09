"""Live distributor pricing for purchased parts (Digi-Key and Mouser).

Contract used by the harness, panel and other quoters:
    price_bom(lines, quantities=None) -> {
        configured: {digikey: bool, mouser: bool},
        results: [{mpn, best: {distributor, unit_price, qty_break, stock, lead_weeks, url, description, ...} | None,
                   offers: [...], error?, by_quantity: [...]}],
    }
Each line is {mpn, manufacturer?, qty}. qty is per build. `quantities` are build quantities: `best` is priced at
qty x the smallest build quantity (the conservative unit price) and `by_quantity` gives the best offer at each one.
With no keys configured nothing is called and every `best` is None, so callers keep their manual prices.

Best offer rule: lowest extended price at the needed quantity among offers with enough stock; if no offer has enough
stock, the lowest extended price among offers with any stock (with a note), else the lowest price overall (with a note).
Ordering more to reach a cheaper price break is considered (for example 10 at a 10-piece break can cost less than 9).

Results are cached for 24 hours per distributor and MPN in the distributor_cache table.

Environment variables:
    DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET   Digi-Key API app (Product Information V4), production
    MOUSER_API_KEY                             Mouser Search API key

API details verified (October 2026):
  Digi-Key, OAuth 2-legged flow: POST https://api.digikey.com/v1/oauth2/token, form fields client_id, client_secret,
    grant_type=client_credentials; response access_token, expires_in (seconds), token_type; tokens last 10 minutes.
    Calls send "Authorization: Bearer <token>" and "X-DIGIKEY-Client-Id".
    https://developer.digikey.com/tutorials-and-resources/oauth-20-2-legged-flow
  Digi-Key Product Information V4 (OpenAPI file https://developer.digikey.com/node/3959/oas-download):
    base https://api.digikey.com/products/v4, POST /search/keyword with body {Keywords, Limit, Offset, ...};
    optional headers X-DIGIKEY-Locale-Site, X-DIGIKEY-Locale-Language, X-DIGIKEY-Locale-Currency.
    KeywordResponse {Products, ProductsCount, ExactMatches}. Product fields used: ManufacturerProductNumber,
    Manufacturer.Name, Description.ProductDescription, QuantityAvailable, ProductUrl, UnitPrice,
    ManufacturerLeadWeeks (string), ProductVariations[]. PriceBreak {BreakQuantity, UnitPrice, TotalPrice}.
    Per-variation fields (DigiKeyProductNumber, PackageType.Name, StandardPricing, MinimumOrderQuantity,
    QuantityAvailableforPackageType) are read defensively: the ProductVariation schema was not fully confirmed.
  Mouser Search API (https://api.mouser.com/api/docs/v1): POST https://api.mouser.com/api/v1/search/partnumber?apiKey=KEY
    body {"SearchByPartRequest": {"mouserPartNumber": "A|B|...", "partSearchOptions": "Exact"}}; up to 10 part numbers
    separated by "|". Response {Errors, SearchResults: {NumberOfResult, Parts: [{ManufacturerPartNumber, Manufacturer,
    Description, Availability, AvailabilityInStock, LeadTime, ProductDetailUrl, PriceBreaks: [{Quantity, Price,
    Currency}], Min, Mult}]}}. Price is a string with a currency symbol (for example "$0.10").
"""
from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import httpx

DIGIKEY_TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
DIGIKEY_KEYWORD_URL = "https://api.digikey.com/products/v4/search/keyword"
MOUSER_PART_URL = "https://api.mouser.com/api/v1/search/partnumber"
CACHE_HOURS = 24
DIGIKEY_WORKERS = 3
MOUSER_BATCH = 10
TIMEOUT = 20.0

_token_lock = threading.Lock()
_token: dict = {"value": "", "expires": 0.0, "client_id": ""}


class DistributorError(RuntimeError):
    pass


def configured() -> dict:
    return {"digikey": bool(os.getenv("DIGIKEY_CLIENT_ID") and os.getenv("DIGIKEY_CLIENT_SECRET")),
            "mouser": bool(os.getenv("MOUSER_API_KEY"))}


def _make_client() -> httpx.Client:
    """One place to build the HTTP client so tests can swap in httpx.MockTransport."""
    return httpx.Client(timeout=TIMEOUT)


def _num(v) -> float | None:
    """Parse a number from a float or a string like "$1,234.50" or "1.234,50 €"."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:  # "1,234" is thousands; "0,45" is a decimal comma
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _int(v) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


# ---------------------------------------------------------------- Digi-Key
def _digikey_token(client: httpx.Client) -> str:
    cid, secret = os.getenv("DIGIKEY_CLIENT_ID", ""), os.getenv("DIGIKEY_CLIENT_SECRET", "")
    with _token_lock:
        if _token["value"] and _token["client_id"] == cid and time.time() < _token["expires"]:
            return _token["value"]
        r = client.post(DIGIKEY_TOKEN_URL, data={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            raise DistributorError(f"Digi-Key sign-in failed ({r.status_code}). Check DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET.")
        j = r.json()
        _token.update(value=j.get("access_token", ""), client_id=cid,
                      expires=time.time() + max(int(j.get("expires_in") or 600) - 60, 30))  # refresh a minute early
        return _token["value"]


def _clear_token() -> None:
    with _token_lock:
        _token.update(value="", expires=0.0, client_id="")


def _digikey_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-DIGIKEY-Client-Id": os.getenv("DIGIKEY_CLIENT_ID", ""),
            "X-DIGIKEY-Locale-Site": "US", "X-DIGIKEY-Locale-Language": "en", "X-DIGIKEY-Locale-Currency": "USD",
            "Content-Type": "application/json", "Accept": "application/json"}


def _lead_weeks(v) -> float | None:
    n = _num(v)
    return n if n is not None and n > 0 else None


def normalize_digikey(p: dict) -> list[dict]:
    """Offers (one per package variation with prices) from one Digi-Key v4 Product."""
    mfr = (p.get("Manufacturer") or {}).get("Name") or ""
    desc = (p.get("Description") or {}).get("ProductDescription") or (p.get("Description") or {}).get("DetailedDescription") or ""
    base = {"distributor": "digikey", "mpn": p.get("ManufacturerProductNumber") or "", "manufacturer": mfr,
            "description": desc, "url": p.get("ProductUrl") or "", "lead_weeks": _lead_weeks(p.get("ManufacturerLeadWeeks")),
            "currency": "USD"}
    offers = []
    for v in p.get("ProductVariations") or []:
        breaks = [{"qty": int(b["BreakQuantity"]), "unit_price": float(b["UnitPrice"])}
                  for b in v.get("StandardPricing") or [] if b.get("BreakQuantity") and b.get("UnitPrice") is not None]
        if not breaks:
            continue
        stock = v.get("QuantityAvailableforPackageType")
        if stock is None:
            stock = v.get("QuantityAvailable", p.get("QuantityAvailable"))
        offers.append({**base, "distributor_pn": v.get("DigiKeyProductNumber") or "",
                       "package": (v.get("PackageType") or {}).get("Name") or "",
                       "stock": _int(stock) or 0, "min_qty": _int(v.get("MinimumOrderQuantity")) or breaks[0]["qty"],
                       "price_breaks": sorted(breaks, key=lambda b: b["qty"])})
    if not offers and p.get("UnitPrice"):
        offers.append({**base, "distributor_pn": "", "package": "", "stock": _int(p.get("QuantityAvailable")) or 0,
                       "min_qty": 1, "price_breaks": [{"qty": 1, "unit_price": float(p["UnitPrice"])}]})
    return offers


def digikey_search(mpn: str, client: httpx.Client, limit: int = 10) -> list[dict]:
    token = _digikey_token(client)
    body = {"Keywords": mpn[:250], "Limit": limit, "Offset": 0}
    r = client.post(DIGIKEY_KEYWORD_URL, json=body, headers=_digikey_headers(token))
    if r.status_code == 401:  # token revoked or expired early: sign in again once
        _clear_token()
        r = client.post(DIGIKEY_KEYWORD_URL, json=body, headers=_digikey_headers(_digikey_token(client)))
    if r.status_code == 429:
        raise DistributorError("Digi-Key rate limit reached. Try again later.")
    if r.status_code != 200:
        raise DistributorError(f"Digi-Key search failed ({r.status_code}).")
    j = r.json()
    products = list(j.get("ExactMatches") or [])
    want = mpn.strip().upper()
    if not products:
        products = [p for p in j.get("Products") or [] if (p.get("ManufacturerProductNumber") or "").upper() == want]
    if not products:
        products = (j.get("Products") or [])[:3]  # no exact match: show close ones, flagged by mpn mismatch
    out = []
    for p in products:
        out.extend(normalize_digikey(p))
    return out


# ---------------------------------------------------------------- Mouser
def _lead_from_text(s) -> float | None:
    """Mouser LeadTime is text such as "84 Days"; return weeks."""
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(day|week)", str(s), re.I)
    if not m:
        return None
    n = float(m.group(1))
    return round(n / 7, 1) if m.group(2).lower().startswith("day") else n


def normalize_mouser(p: dict) -> dict | None:
    breaks = []
    currency = ""
    for b in p.get("PriceBreaks") or []:
        q, price = _int(b.get("Quantity")), _num(b.get("Price"))
        if q and price is not None:
            breaks.append({"qty": q, "unit_price": price})
            currency = currency or b.get("Currency") or ""
    if not breaks:
        return None
    stock = _int(p.get("AvailabilityInStock"))
    if stock is None:
        m = re.match(r"\s*([\d,]+)\s+In Stock", p.get("Availability") or "", re.I)
        stock = _int(m.group(1)) if m else 0
    return {"distributor": "mouser", "mpn": p.get("ManufacturerPartNumber") or "", "manufacturer": p.get("Manufacturer") or "",
            "description": p.get("Description") or "", "url": p.get("ProductDetailUrl") or "",
            "distributor_pn": p.get("MouserPartNumber") or "", "package": "", "stock": stock or 0,
            "min_qty": _int(p.get("Min")) or breaks[0]["qty"], "lead_weeks": _lead_from_text(p.get("LeadTime")),
            "currency": currency or "USD", "price_breaks": sorted(breaks, key=lambda b: b["qty"])}


def mouser_search(mpns: list[str], client: httpx.Client) -> dict[str, list[dict]]:
    """Look up to 10 MPNs per call (pipe separated). Returns {MPN upper: offers}."""
    key = os.getenv("MOUSER_API_KEY", "")
    out: dict[str, list[dict]] = {m.strip().upper(): [] for m in mpns}
    for i in range(0, len(mpns), MOUSER_BATCH):
        chunk = [m for m in mpns[i:i + MOUSER_BATCH] if 3 <= len(m.strip()) <= 40]
        if not chunk:
            continue
        body = {"SearchByPartRequest": {"mouserPartNumber": "|".join(c.strip() for c in chunk), "partSearchOptions": "Exact"}}
        r = client.post(MOUSER_PART_URL, params={"apiKey": key}, json=body,
                        headers={"Content-Type": "application/json", "Accept": "application/json"})
        if r.status_code == 429:
            raise DistributorError("Mouser rate limit reached. Try again later.")
        if r.status_code != 200:
            raise DistributorError(f"Mouser search failed ({r.status_code}).")
        j = r.json()
        errs = j.get("Errors") or []
        if errs and not (j.get("SearchResults") or {}).get("Parts"):
            raise DistributorError("Mouser: " + "; ".join(e.get("Message") or e.get("Code") or "error" for e in errs))
        for p in (j.get("SearchResults") or {}).get("Parts") or []:
            offer = normalize_mouser(p)
            if not offer:
                continue
            k = offer["mpn"].upper()
            if k in out:
                out[k].append(offer)
            elif len(chunk) == 1:
                out[chunk[0].strip().upper()].append(offer)
        if i + MOUSER_BATCH < len(mpns):
            time.sleep(0.5)  # stay well under the per-minute limit
    return out


# ---------------------------------------------------------------- price break selection
def cost_at(offer: dict, need: int) -> dict | None:
    """Cheapest way to buy `need` from this offer: the applicable break, or ordering up to a cheaper higher break."""
    breaks = offer.get("price_breaks") or []
    if not breaks or need <= 0:
        return None
    mult_min = max(int(offer.get("min_qty") or 1), 1)
    options = []
    applicable = [b for b in breaks if b["qty"] <= need]
    if applicable and need >= mult_min:
        b = applicable[-1]
        options.append((round(b["unit_price"] * need, 4), need, b))
    for b in breaks:
        if b["qty"] >= need:
            order = max(b["qty"], mult_min)
            options.append((round(b["unit_price"] * order, 4), order, b))
    if not options:
        b = breaks[-1]
        order = max(need, mult_min)
        options.append((round(b["unit_price"] * order, 4), order, b))
    ext, order, b = min(options, key=lambda o: (o[0], o[1]))
    return {"unit_price": b["unit_price"], "qty_break": b["qty"], "order_qty": order, "extended_price": round(ext, 2)}


def choose_best(offers: list[dict], need: int) -> dict | None:
    priced = []
    for o in offers:
        c = cost_at(o, need)
        if c:
            priced.append({**{k: o.get(k) for k in ("distributor", "mpn", "manufacturer", "distributor_pn", "package",
                                                   "stock", "lead_weeks", "url", "description", "currency")}, **c,
                           "need_qty": need})
    if not priced:
        return None
    enough = [p for p in priced if (p["stock"] or 0) >= p["order_qty"]]
    if enough:
        best = min(enough, key=lambda p: p["extended_price"])
        return {**best, "stock_ok": True, "note": ""}
    some = [p for p in priced if (p["stock"] or 0) > 0]
    pool = some or priced
    best = min(pool, key=lambda p: p["extended_price"])
    lead = f" Lead time about {best['lead_weeks']:g} weeks." if best.get("lead_weeks") else ""
    note = (f"Only {best['stock']} in stock at {best['distributor']} for {best['order_qty']} needed." if some
            else f"Not in stock at {best['distributor']}.") + lead
    return {**best, "stock_ok": False, "note": note}


# ---------------------------------------------------------------- cache
def _cache_get(db, distributor: str, key: str) -> list[dict] | None:
    from .models_quote_tools import DistributorCache
    row = db.query(DistributorCache).filter_by(distributor=distributor, mpn_key=key).first()
    if row and row.fetched_at and row.fetched_at > datetime.utcnow() - timedelta(hours=CACHE_HOURS):
        return list(row.offers or [])
    return None


def _cache_put(db, distributor: str, key: str, offers: list[dict]) -> None:
    from .models_quote_tools import DistributorCache
    row = db.query(DistributorCache).filter_by(distributor=distributor, mpn_key=key).first() \
        or DistributorCache(distributor=distributor, mpn_key=key)
    row.offers, row.fetched_at = offers, datetime.utcnow()
    db.add(row)


def lookup(mpns: list[str], *, db=None, client: httpx.Client | None = None, use_cache: bool = True) -> tuple[dict, dict]:
    """Offers for each MPN from every configured distributor. Returns ({MPN upper: offers}, {MPN upper: error})."""
    from .db import SessionLocal

    conf = configured()
    keys = list(dict.fromkeys(m.strip().upper() for m in mpns if m and m.strip()))
    offers: dict[str, list[dict]] = {k: [] for k in keys}
    errors: dict[str, list[str]] = {k: [] for k in keys}
    if not keys or not any(conf.values()):
        return offers, {}
    own_db = db is None
    db = db or SessionLocal()
    own_client = client is None
    client = client or _make_client()
    try:
        for dist in ("digikey", "mouser"):
            if not conf[dist]:
                continue
            todo = []
            for k in keys:
                cached = _cache_get(db, dist, k) if use_cache else None
                if cached is not None:
                    offers[k].extend(cached)
                else:
                    todo.append(k)
            if not todo:
                continue
            fresh: dict[str, list[dict]] = {}
            if dist == "digikey":
                def one(k: str):
                    try:
                        return k, digikey_search(k, client), None
                    except (DistributorError, httpx.HTTPError, ValueError) as exc:
                        return k, None, f"Digi-Key: {exc}"
                with ThreadPoolExecutor(max_workers=DIGIKEY_WORKERS) as ex:
                    for k, res, err in ex.map(one, todo):
                        if err:
                            errors[k].append(err)
                        else:
                            fresh[k] = res
            else:
                try:
                    fresh = mouser_search(todo, client)
                except (DistributorError, httpx.HTTPError, ValueError) as exc:
                    for k in todo:
                        errors[k].append(f"Mouser: {exc}" if not str(exc).startswith("Mouser") else str(exc))
            for k, res in fresh.items():
                offers[k].extend(res)
                _cache_put(db, dist, k, res)
        db.commit()
    finally:
        if own_client:
            client.close()
        if own_db:
            db.close()
    return offers, {k: "; ".join(v) for k, v in errors.items() if v}


def price_bom(lines: list[dict], quantities: list[int] | None = None, *, db=None, client: httpx.Client | None = None) -> dict:
    """Live prices for a bill of materials. See the module docstring for the shape."""
    conf = configured()
    builds = sorted({int(q) for q in (quantities or []) if q and int(q) > 0}) or [1]
    clean = []
    for ln in lines or []:
        mpn = str((ln or {}).get("mpn") or "").strip()
        try:
            qty = max(int(float((ln or {}).get("qty") or 1)), 1)
        except (TypeError, ValueError):
            qty = 1
        clean.append({"mpn": mpn, "manufacturer": str((ln or {}).get("manufacturer") or ""), "qty": qty})
    offers, errors = lookup([c["mpn"] for c in clean], db=db, client=client) if any(conf.values()) else ({}, {})
    results = []
    for c in clean:
        k = c["mpn"].upper()
        row: dict = {"mpn": c["mpn"], "manufacturer": c["manufacturer"], "qty": c["qty"], "best": None, "offers": [], "by_quantity": []}
        if not c["mpn"]:
            row["error"] = "No manufacturer part number."
            results.append(row)
            continue
        found = list(offers.get(k) or [])
        if c["manufacturer"] and found:  # prefer the named manufacturer when the MPN is shared
            same = [o for o in found if c["manufacturer"].lower()[:6] in (o.get("manufacturer") or "").lower()]
            found = same or found
        row["offers"] = found
        if found:
            row["by_quantity"] = [{"quantity": b, "need": c["qty"] * b, "best": choose_best(found, c["qty"] * b)} for b in builds]
            row["best"] = row["by_quantity"][0]["best"]
            if row["best"] and row["best"]["mpn"].upper() != k:
                row["best"]["note"] = (row["best"]["note"] + " " if row["best"]["note"] else "") + \
                    f"No exact match for {c['mpn']}; closest is {row['best']['mpn']}. Check it before using this price."
        if errors.get(k):
            row["error"] = errors[k]
        elif any(conf.values()) and not found:
            row["error"] = "Not found at the configured distributors."
        results.append(row)
    return {"configured": conf, "results": results}


def search(q: str, *, db=None, client: httpx.Client | None = None) -> dict:
    """Offers for one MPN from every configured distributor."""
    conf = configured()
    if not q.strip() or not any(conf.values()):
        return {"configured": conf, "query": q, "offers": [], "error": "" if q.strip() else "Enter a part number."}
    offers, errors = lookup([q], db=db, client=client)
    k = q.strip().upper()
    return {"configured": conf, "query": q, "offers": offers.get(k, []), "error": errors.get(k, "")}
