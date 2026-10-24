"""Digi-Key Product Information API v4: list prices for 80/20 profiles and hardware.

Digi-Key is an 80/20 supplier and lists 80/20 parts under 80/20's own part numbers (1515-72 is a 72 in bar of
1515; 3360 is the 15 Series anchor fastener), so no matching table is needed. Set on the server:

  DIGIKEY_CLIENT_ID       from your app at developer.digikey.com (Product Information enabled)
  DIGIKEY_CLIENT_SECRET   its secret

Login is OAuth client credentials (a token lasts 10 minutes). Prices are Digi-Key's list prices at quantity 1:
your distributor's discounted price may be lower, and cutting and machining are priced separately.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime

BASE = "https://api.digikey.com"
MAKER = re.compile(r"80\s*/\s*20", re.I)
GAP = 0.6  # seconds between calls: Digi-Key allows about 120 a minute


class DigiKeyError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("DIGIKEY_CLIENT_ID") and os.getenv("DIGIKEY_CLIENT_SECRET"))


def status() -> dict:
    missing = [k for k in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET") if not os.getenv(k)]
    return {"configured": not missing, "missing": missing}


class Client:
    def __init__(self, transport=None):
        self._token, self._expires = None, 0.0
        self._lock = threading.Lock()
        self._transport = transport  # tests pass an httpx.MockTransport
        self._last = 0.0

    def _http(self):
        import httpx

        return httpx.Client(base_url=BASE, timeout=20, transport=self._transport) if self._transport else httpx.Client(base_url=BASE, timeout=20)

    def _login(self, http) -> str:
        with self._lock:
            if self._token and time.time() < self._expires - 60:
                return self._token
            r = http.post("/v1/oauth2/token", data={"client_id": os.getenv("DIGIKEY_CLIENT_ID", ""), "client_secret": os.getenv("DIGIKEY_CLIENT_SECRET", ""),
                                                    "grant_type": "client_credentials"})
            if r.status_code >= 400:
                raise DigiKeyError(f"Digi-Key login failed ({r.status_code}): check DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET. {r.text[:160]}")
            body = r.json()
            self._token = body.get("access_token")
            self._expires = time.time() + float(body.get("expires_in") or 600)
            if not self._token:
                raise DigiKeyError("Digi-Key login returned no token.")
            return self._token

    def search(self, keywords: str, limit: int = 50) -> list[dict]:
        """Products whose manufacturer is 80/20 for a keyword search."""
        wait = GAP - (time.time() - self._last)
        if wait > 0 and not self._transport:
            time.sleep(wait)
        with self._http() as http:
            for attempt in range(2):
                tok = self._login(http)
                r = http.post("/products/v4/search/keyword", json={"Keywords": keywords, "Limit": limit, "Offset": 0},
                              headers={"X-DIGIKEY-Client-Id": os.getenv("DIGIKEY_CLIENT_ID", ""), "Authorization": f"Bearer {tok}",
                                       "X-DIGIKEY-Locale-Site": "US", "X-DIGIKEY-Locale-Currency": "USD", "X-DIGIKEY-Locale-Language": "en"})
                self._last = time.time()
                if r.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                if r.status_code == 429:
                    raise DigiKeyError("Digi-Key's request limit was reached. Try again later (the daily limit resets at midnight Central).")
                if r.status_code >= 400:
                    raise DigiKeyError(f"Digi-Key search failed ({r.status_code}): {r.text[:200]}")
                return [p for p in r.json().get("Products") or [] if MAKER.search(str((p.get("Manufacturer") or {}).get("Name") or ""))]
        return []


def unit_price(p: dict) -> float | None:
    """The quantity-1 price: the lowest first-break price across the product's packagings, else UnitPrice."""
    best = None
    for v in p.get("ProductVariations") or []:
        for b in v.get("StandardPricing") or []:
            if int(b.get("BreakQuantity") or 0) <= 1 and b.get("UnitPrice"):
                best = float(b["UnitPrice"]) if best is None else min(best, float(b["UnitPrice"]))
    if best is None and p.get("UnitPrice"):
        best = float(p["UnitPrice"])
    return best


def part_price(c: Client, pn: str) -> dict | None:
    """{pn, price, url, description} for an exact 80/20 part number, or None."""
    for p in c.search(pn):
        mpn = str(p.get("ManufacturerProductNumber") or "").strip()
        if mpn.upper() == pn.upper():
            price = unit_price(p)
            if price:
                return {"pn": pn, "price": round(price, 4), "url": p.get("ProductUrl") or "",
                        "description": ((p.get("Description") or {}).get("ProductDescription") or "")[:120]}
    return None


def profile_per_inch(c: Client, pid: str) -> dict | None:
    """Cheapest price per inch of a profile over the bar lengths Digi-Key lists ("1515-72" is 72 in)."""
    rx = re.compile(rf"^{re.escape(pid)}-(\d+(?:\.\d+)?)$", re.I)
    best = None
    for p in c.search(pid):
        m = rx.match(str(p.get("ManufacturerProductNumber") or "").strip())
        price = unit_price(p) if m else None
        if not m or not price or float(m.group(1)) < 12:
            continue
        per = price / float(m.group(1))
        if best is None or per < best["per_inch"]:
            best = {"pid": pid, "per_inch": round(per, 4), "bar": p["ManufacturerProductNumber"], "bar_price": price, "url": p.get("ProductUrl") or ""}
    return best


# ------------------------------------------------------------------ refresh the shop's extrusion prices
_job: dict = {"running": False}


def job() -> dict:
    return dict(_job)


def refresh(db, client: Client | None = None, profiles: list[str] | None = None) -> dict:
    """Look up every 80/20 profile and hardware part the extrusion catalog prices and save what Digi-Key has into
    the extrusion prices (Part quotes > shop rates). Parts Digi-Key doesn't carry keep their current price."""
    from . import catalog_8020, pricing, quotes

    if not configured() and client is None:
        raise DigiKeyError("Digi-Key is not set up: add DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET on the server.")
    c = client or Client()
    cfg = quotes.get_config(db)
    have = cfg["extrusion"]["prices"]
    pids = profiles if profiles is not None else [p for p in have["profiles"] if catalog_8020.profile(p)]
    prof, found_p, missing = {}, [], []
    for pid in pids:
        _job.update(step=f"profile {pid}")
        hit = profile_per_inch(c, pid)
        if hit:
            prof[pid] = hit["per_inch"]
            found_p.append(hit)
        else:
            missing.append(pid)
    pn_price: dict[str, float] = {}
    for pn in sorted({r[0] for rows in catalog_8020.HARDWARE.values() for r in rows}):
        _job.update(step=f"part {pn}")
        hit = part_price(c, pn)
        if hit:
            pn_price[pn] = hit["price"]
        else:
            missing.append(pn)
    hw = {}
    for (base, fam), rows in catalog_8020.HARDWARE.items():
        if rows and all(r[0] in pn_price for r in rows):  # the part and the screws and T-nuts it needs
            hw[f"{base}-{fam}"] = round(sum(pn_price[r[0]] * float(r[2]) for r in rows), 4)
    when = datetime.utcnow().strftime("%Y-%m-%d")
    note = (f"Profile and hardware prices from Digi-Key list prices on {when} (quantity 1, before any distributor discount). "
            "Cutting and machining are your rates below.")
    quotes.update_config(db, {"extrusion": {"prices": {"profiles": prof, "hardware": hw}, "note": note,
                                            "price_source": {"source": "Digi-Key", "date": when, "profiles": len(prof), "hardware": len(hw),
                                                             "parts": pn_price}}})
    db.commit()
    return {"date": when, "profiles": len(prof), "hardware_items": len(hw), "parts_found": len(pn_price), "missing": missing,
            "examples": found_p[:5]}


def refresh_in_background(session_factory) -> dict:
    if _job.get("running"):
        return job()

    def run():
        db = session_factory()
        try:
            _job.update(result=refresh(db), error=None)
        except Exception as exc:  # noqa: BLE001
            _job.update(error=str(exc))
        finally:
            db.close()
            _job.update(running=False, step="", finished=time.time())

    _job.clear()
    _job.update(running=True, started=time.time(), step="starting", error=None, result=None)
    threading.Thread(target=run, daemon=True).start()
    return job()
