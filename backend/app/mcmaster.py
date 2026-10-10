"""McMaster-Carr Product Information API (https://www.mcmaster.com/help/api).

Access is by approval: email eCommerce@mcmaster.com. Approved customers get a client certificate (.pfx) and its
password, and use their mcmaster.com login. Set on the server:

  MCMASTER_USERNAME        your mcmaster.com login
  MCMASTER_PASSWORD        its password
  MCMASTER_CERT_PATH       the .pfx file (default /etc/secrets/mcmaster.pfx: a Render "secret file")
  MCMASTER_CERT_BASE64     or the .pfx itself, base64 encoded, if you would rather use an environment variable
  MCMASTER_CERT_PASSWORD   the certificate's password

Flow: POST /v1/login -> AuthToken (24 h). A product must be subscribed (PUT /v1/products) before its information
(GET /v1/products/{pn}) or price (GET /v1/products/{pn}/price) can be read. Accounts have a cap on subscriptions.
Nothing else from the site is scraped: only this API, under McMaster's terms.
"""
from __future__ import annotations

import base64
import os
import re
import tempfile
import threading
import time
from pathlib import Path

BASE = "https://api.mcmaster.com/v1"
PN_RX = re.compile(r"(?<![A-Z0-9])(\d{3,5}[A-Z]\d{1,4})(?![A-Z0-9])")  # 91290A115, 5972K91, 6391K123 (underscores separate)


class McMasterError(Exception):
    pass


def part_numbers_in(text: str) -> list[str]:
    """McMaster part numbers in a name (their CAD downloads are named by part number)."""
    return PN_RX.findall((text or "").upper())


def configured() -> bool:
    return bool(os.getenv("MCMASTER_USERNAME") and os.getenv("MCMASTER_PASSWORD") and _cert_source())


def _cert_source() -> bytes | None:
    b64 = os.getenv("MCMASTER_CERT_BASE64")
    if b64:
        try:
            return base64.b64decode(b64)
        except ValueError:
            return None
    p = Path(os.getenv("MCMASTER_CERT_PATH", "/etc/secrets/mcmaster.pfx"))
    return p.read_bytes() if p.exists() else None


def status() -> dict:
    missing = [k for k in ("MCMASTER_USERNAME", "MCMASTER_PASSWORD") if not os.getenv(k)]
    if not _cert_source():
        missing.append("MCMASTER_CERT_PATH or MCMASTER_CERT_BASE64 (the .pfx certificate)")
    return {"configured": not missing, "missing": missing}


class Client:
    """One logged-in session. Thread-safe enough for this app: one token, refreshed when it expires."""

    def __init__(self, transport=None):
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()
        self._files: tuple[str, str] | None = None
        self._transport = transport  # tests pass an httpx.MockTransport

    def _cert_files(self) -> tuple[str, str] | None:
        if self._transport is not None:
            return None
        if self._files:
            return self._files
        data = _cert_source()
        if not data:
            raise McMasterError("McMaster certificate not found. Set MCMASTER_CERT_PATH or MCMASTER_CERT_BASE64.")
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

        pw = os.getenv("MCMASTER_CERT_PASSWORD", "")
        try:
            key, cert, extra = pkcs12.load_key_and_certificates(data, pw.encode() if pw else None)
        except ValueError as exc:
            raise McMasterError(f"Could not open the McMaster certificate (check MCMASTER_CERT_PASSWORD): {exc}") from None
        d = Path(tempfile.mkdtemp(prefix="mcm-"))
        os.chmod(d, 0o700)
        cf, kf = d / "cert.pem", d / "key.pem"
        cf.write_bytes(cert.public_bytes(Encoding.PEM) + b"".join(c.public_bytes(Encoding.PEM) for c in (extra or [])))
        kf.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
        os.chmod(kf, 0o600)
        self._files = (str(cf), str(kf))
        return self._files

    def _http(self):
        import httpx

        if self._transport is not None:
            return httpx.Client(transport=self._transport, base_url=BASE, timeout=20)
        return httpx.Client(cert=self._cert_files(), base_url=BASE, timeout=20)

    def _login(self, http) -> str:
        with self._lock:
            if self._token and time.time() < self._expires - 300:
                return self._token
            r = http.post("/login", json={"UserName": os.getenv("MCMASTER_USERNAME", ""), "Password": os.getenv("MCMASTER_PASSWORD", "")})
            if r.status_code == 401:
                raise McMasterError("McMaster refused the login: the account is not approved for the API, or the username or password is wrong.")
            if r.status_code >= 400:
                raise McMasterError(f"McMaster login failed ({r.status_code}): {r.text[:200]}")
            body = r.json()
            self._token = body.get("AuthToken")
            self._expires = time.time() + 23 * 3600
            if not self._token:
                raise McMasterError("McMaster login returned no token.")
            return self._token

    def _get(self, http, path: str, retry: bool = True):
        tok = self._login(http)
        r = http.get(path, headers={"Authorization": f"Bearer {tok}"})
        if r.status_code == 401 and retry:  # token expired early
            self._token = None
            return self._get(http, path, retry=False)
        return r

    def product(self, pn: str) -> dict:
        """Subscribe (if needed), then read the product and its price. Returns
        {part_number, description, status, price_breaks: [{min_qty, amount, uom}], unit_price, pack_qty, url, raw}."""
        pn = pn.strip().upper()
        if not PN_RX.fullmatch(pn):
            raise McMasterError(f"{pn} does not look like a McMaster-Carr part number.")
        with self._http() as http:
            tok = self._login(http)
            info = self._get(http, f"/products/{pn}")
            if info.status_code == 403 and "NOT_SUBSCRIBED" in info.text.upper():
                s = http.put("/products", json={"URL": f"https://mcmaster.com/{pn}"}, headers={"Authorization": f"Bearer {tok}"})
                if s.status_code >= 400:
                    raise McMasterError(f"Could not subscribe to {pn} ({s.status_code}): {s.text[:200]}. "
                                        "McMaster limits how many products an account can subscribe to each day.")
                info = self._get(http, f"/products/{pn}")
            if info.status_code == 404:
                raise McMasterError(f"McMaster has no part {pn}.")
            if info.status_code >= 400:
                raise McMasterError(f"McMaster product lookup failed ({info.status_code}): {info.text[:200]}")
            prod = info.json()
            pr = self._get(http, f"/products/{pn}/price")
            if pr.status_code >= 400:
                raise McMasterError(f"McMaster price lookup failed ({pr.status_code}): {pr.text[:200]}")
            prices = pr.json() if isinstance(pr.json(), list) else (pr.json().get("Prices") or [])
        return parse(pn, prod, prices)


def _desc(prod: dict) -> str:
    for k in ("DetailDescription", "FamilyDescription", "ProductDescription", "Description"):
        if prod.get(k):
            return str(prod[k])[:300]
    specs = prod.get("Specifications") or []
    bits = []
    for sp in specs[:6]:
        if isinstance(sp, dict):
            name = sp.get("Attribute") or sp.get("Name")
            vals = sp.get("Values") or sp.get("Value")
            if name and vals:
                bits.append(f"{name}: {', '.join(vals) if isinstance(vals, list) else vals}")
    return "; ".join(bits)[:300]


def pack_size(uom: str) -> int:
    m = re.search(r"(?:pack|package|bag|box)s?\s+of\s+(\d+)", uom or "", re.I) or re.search(r"(\d+)\s*(?:per|/)\s*(?:pack|package|bag|box)", uom or "", re.I)
    return int(m.group(1)) if m else 1


def parse(pn: str, prod: dict, prices: list) -> dict:
    breaks = []
    for p in prices or []:
        try:
            breaks.append({"min_qty": int(p.get("MinimumQuantity") or 1), "amount": float(p.get("Amount")), "uom": str(p.get("UnitOfMeasure") or "Each")})
        except (TypeError, ValueError):
            continue
    breaks.sort(key=lambda b: b["min_qty"])
    first = breaks[0] if breaks else None
    pack = pack_size(first["uom"]) if first else 1
    return {"part_number": pn, "description": _desc(prod), "status": prod.get("ProductStatus") or "",
            "price_breaks": breaks, "pack_price": first["amount"] if first else None, "pack_qty": pack,
            "unit_price": round(first["amount"] / pack, 4) if first else None, "url": f"https://www.mcmaster.com/{pn}/", "raw": prod}


_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client
