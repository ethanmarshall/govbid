"""Login for a hosted copy, calendar token, health check and backups."""
import zipfile

from fastapi.testclient import TestClient

from app import auth
from app.main import app


def test_open_when_no_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    with TestClient(app) as c:
        assert c.get("/api/auth/status").json() == {"login_required": False, "signed_in": True, "username": None, "calendar_token": ""}
        assert c.get("/api/dashboard").status_code == 200


def test_login_required_flow(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "ethan")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.setenv("CALENDAR_TOKEN", "caltok")
    auth._fails.clear()
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/dashboard").status_code == 401
        assert c.get("/api/profile").status_code == 401
        assert c.get("/").status_code in (200, 404)  # the page shell itself is not data
        st = c.get("/api/auth/status").json()
        assert st["login_required"] and not st["signed_in"] and st["calendar_token"] == ""
        assert c.post("/api/auth/login", json={"username": "ethan", "password": "nope"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "ethan", "password": "correct horse battery"}).status_code == 200
        assert c.get("/api/dashboard").status_code == 200
        assert c.get("/api/auth/status").json()["calendar_token"] == "caltok"
        c.post("/api/auth/logout")
        assert c.get("/api/dashboard").status_code == 401
    with TestClient(app) as c2:  # calendar feed: token works without a session, wrong token does not
        assert c2.get("/api/calendar.ics", params={"token": "caltok"}).status_code == 200
        assert c2.get("/api/calendar.ics", params={"token": "bad"}).status_code == 401
        assert c2.get("/api/calendar.ics").status_code == 401


def test_forged_or_other_secret_cookie_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("SESSION_SECRET", "one")
    token = auth._signer().sign("admin").decode()
    assert auth.valid_session(token)
    monkeypatch.setenv("SESSION_SECRET", "two")
    assert not auth.valid_session(token)
    assert not auth.valid_session("admin.garbage")


def test_lockout_after_repeated_failures(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    auth._fails.clear()
    with TestClient(app) as c:
        for _ in range(auth.MAX_FAILS):
            assert c.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "admin", "password": "pw"}).status_code == 429
    auth._fails.clear()


def test_backup_zip(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    from app.backup import make_backup
    with TestClient(app) as c:
        c.get("/api/profile")
        r = c.get("/api/admin/backup")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(make_backup(tmp_path))
    assert "govbid.db" in z.namelist()
