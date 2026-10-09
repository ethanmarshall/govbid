"""Standards library API: catalog plus saved, cited and imported documents."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import standards as S
from .config import UPLOAD_DIR
from .db import get_db

router = APIRouter(prefix="/api/standards", tags=["standards"])

MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_IMPORT_BYTES = 60 * 1024 * 1024
FILE_DIR = UPLOAD_DIR / "standards"


def _bool(v: str | None) -> bool | None:
    if v is None or v == "":
        return None
    return str(v).lower() in ("1", "true", "yes", "free")


@router.get("")
def list_standards(
    q: str = "",
    category: str = "",
    scope: str = "all",
    free: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if scope not in S.SCOPES:
        raise HTTPException(400, f"scope must be one of {', '.join(S.SCOPES)}")
    items = S.filter_entries(S.merged_entries(db), q=q, category=category, scope=scope, free=_bool(free))
    total = len(items)
    start = (page - 1) * limit
    out = {"items": items[start:start + limit], "total": total, "page": page, "limit": limit, "lookup": None}
    if S.looks_like_id(q):
        lk = S.lookup(db, q)
        exact = any(i["base_id"] == lk["entry"]["base_id"] for i in items)
        if not exact:
            out["lookup"] = lk
    return out


@router.get("/categories")
def categories(scope: str = "all", q: str = "", free: str | None = None, db: Session = Depends(get_db)):
    items = S.filter_entries(S.merged_entries(db), q=q, scope=scope if scope in S.SCOPES else "all", free=_bool(free))
    return {"categories": S.category_counts(items), "total": len(items)}


@router.get("/lookup")
def lookup(id: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return S.lookup(db, id)


class RevisionCheckIn(BaseModel):
    cited: list = []


@router.post("/revision-check")
def revision_check(body: RevisionCheckIn, db: Session = Depends(get_db)):
    return {"results": S.revision_check(db, body.cited)}


@router.post("/import")
async def import_list(file: UploadFile = File(...), save_to_library: bool = Form(False), db: Session = Depends(get_db)):
    """Load an exported list (CSV or Excel) with columns such as Document ID, Title, Status, Date."""
    from .connectors.tabular_import import _rows_from_file

    name = file.filename or "list.csv"
    suffix = Path(name).suffix.lower()
    if suffix not in (".csv", ".tsv", ".txt", ".xlsx", ".xlsm"):
        raise HTTPException(400, "Upload a CSV or Excel (.xlsx) file.")
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File is larger than 60 MB.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"import{suffix}"
        path.write_bytes(data)
        try:
            rows = _rows_from_file(path)
        except Exception as exc:  # unreadable spreadsheet
            raise HTTPException(400, f"Could not read the file: {exc}")
    result = S.import_rows(db, rows, save_to_library=save_to_library)
    return result


# ---- file routes come before the catch-all so IDs with slashes still route correctly
def _row_or_404(db: Session, base_id: str):
    row = S.get_row(db, S.canonical_id(base_id))
    if row is None:
        raise HTTPException(404, "Not in your library")
    return row


def _safe_name(base_id: str, filename: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", base_id).strip("_")
    fn = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "document.pdf").name).strip("_") or "document.pdf"
    return f"{stem}__{fn}"


@router.post("/{base_id:path}/file")
async def upload_file(base_id: str, file: UploadFile = File(...), revision: str = Form(""), db: Session = Depends(get_db)):
    name = file.filename or "document.pdf"
    if Path(name).suffix.lower() != ".pdf" and file.content_type != "application/pdf":
        raise HTTPException(400, "Attach a PDF copy of the document.")
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "File is larger than 60 MB.")
    base = S.canonical_id(S.parse_doc_id(base_id)[0] or base_id)
    row = S.get_or_create_row(db, base)
    FILE_DIR.mkdir(parents=True, exist_ok=True)
    if row.file_name:
        old = FILE_DIR / row.file_name
        if old.exists():
            old.unlink()
    stored = _safe_name(base, name if name.lower().endswith(".pdf") else name + ".pdf")
    (FILE_DIR / stored).write_bytes(data)
    row.file_name = stored
    row.in_library = True
    if revision.strip():
        row.revision_on_file = revision.strip()[:40]
    db.commit()
    return S.entry_view(row)


@router.get("/{base_id:path}/file")
def download_file(base_id: str, db: Session = Depends(get_db)):
    row = _row_or_404(db, base_id)
    path = FILE_DIR / (row.file_name or "")
    if not row.file_name or not path.exists():
        raise HTTPException(404, "No file attached")
    display = row.file_name.split("__", 1)[-1]
    return FileResponse(path, filename=display, media_type="application/pdf")


@router.delete("/{base_id:path}/file")
def delete_file(base_id: str, db: Session = Depends(get_db)):
    row = _row_or_404(db, base_id)
    if row.file_name:
        path = FILE_DIR / row.file_name
        if path.exists():
            path.unlink()
    row.file_name = ""
    db.commit()
    return S.entry_view(row)


class StandardUpdate(BaseModel):
    in_library: bool | None = None
    revision_on_file: str | None = None
    notes: str | None = None
    title: str | None = None
    category: str | None = None


@router.get("/{base_id:path}")
def get_standard(base_id: str, db: Session = Depends(get_db)):
    return S.lookup(db, base_id)["entry"]


@router.put("/{base_id:path}")
def update_standard(base_id: str, body: StandardUpdate, db: Session = Depends(get_db)):
    base = S.canonical_id(S.parse_doc_id(base_id)[0] or base_id)
    if not base:
        raise HTTPException(400, "Document ID required")
    row = S.get_or_create_row(db, base)
    if body.in_library is not None:
        row.in_library = body.in_library
    if body.revision_on_file is not None:
        rev = body.revision_on_file.strip()
        # Accept a full ID typed into the revision box ("MIL-STD-130N") as well as just "N".
        if len(rev) > 3 and S.parse_doc_id(rev)[0] == base:
            rev = S.parse_doc_id(rev)[1]
        row.revision_on_file = rev[:40]
    if body.notes is not None:
        row.notes = body.notes
    if body.title is not None and body.title.strip():
        row.title = body.title.strip()[:500]
    if body.category is not None:
        row.category = body.category.strip()[:120]
    db.commit()
    return S.entry_view(row)
