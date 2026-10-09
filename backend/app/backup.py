"""Backups: one zip with a consistent copy of the database and every uploaded file.

GET /api/admin/backup downloads it from the site; `python -m app.cli backup` writes one to disk.
SQLite's online backup API copies the database safely while the app is running.
"""
from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import DATABASE_URL, UPLOAD_DIR

router = APIRouter(prefix="/api/admin")


def _db_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL.replace("sqlite:///", "", 1))


def make_backup(out_dir: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir or tempfile.mkdtemp())
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"govbid-backup-{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        db = _db_path()
        if db and db.exists():
            snap = out_dir / f".snapshot-{stamp}.db"
            src, dst = sqlite3.connect(db), sqlite3.connect(snap)
            with dst:
                src.backup(dst)
            src.close(); dst.close()
            z.write(snap, "govbid.db")
            snap.unlink()
        if UPLOAD_DIR.exists():
            for f in UPLOAD_DIR.rglob("*"):
                if f.is_file():
                    z.write(f, Path("uploads") / f.relative_to(UPLOAD_DIR))
    return zpath


@router.get("/backup")
def download_backup():
    path = make_backup()
    return FileResponse(path, filename=path.name, media_type="application/zip",
                        background=BackgroundTask(lambda: path.unlink(missing_ok=True)))
