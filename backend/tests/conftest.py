import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["SAM_API_KEY"] = "test-key"
os.environ["ANTHROPIC_API_KEY"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _drop_website_invoices():
    """Website orders make invoices in Invoices and finance; remove them after each test so finance tests see only their own."""
    yield
    try:
        from app.db import SessionLocal
        from app.models_finance import Invoice
    except Exception:  # noqa: BLE001
        return
    with SessionLocal() as db:
        for inv in db.query(Invoice).filter(Invoice.notes.like("Website order%")).all():
            db.delete(inv)
        db.commit()
