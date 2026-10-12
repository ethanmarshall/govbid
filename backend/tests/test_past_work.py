import base64

from fastapi.testclient import TestClient

import pytest

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_past_work_drafts_hidden_until_published(client):
    up = client.post("/api/portal/site-media", files={"file": ("cart.png", PNG, "image/png")})
    assert up.status_code == 200, up.text
    name = up.json()["name"]
    assert client.post("/api/portal/site-media", files={"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")}).status_code == 400
    projects = [
        {"title": "Rolling equipment cart", "kind": "in_house", "year": "2026", "summary": "T-slot cart", "details": ["1530 posts", ""],
         "image": name, "published": True},
        {"title": "Draft job", "kind": "customer", "summary": "not checked yet", "published": False},
        {"title": "Bad image", "kind": "nonsense", "image": "../../etc/passwd", "published": True},
    ]
    r = client.put("/api/portal/settings", json={"site": {"projects": projects}})
    assert r.status_code == 200, r.text
    saved = r.json()["site"]["projects"]
    assert len(saved) == 3 and saved[1]["published"] is False and saved[2]["kind"] == "in_house" and saved[2]["image"] == ""
    assert saved[0]["details"] == ["1530 posts"]
    pub = client.get("/api/public/info").json()["site"]["projects"]
    assert [p["title"] for p in pub] == ["Rolling equipment cart", "Bad image"]
    assert pub[0]["kind_label"] == "In-house build" and "published" not in pub[0]
    img = TestClient(app).get(f"/api/public/site-media/{name}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == PNG
    bad = TestClient(app).get("/api/public/site-media/..%2F..%2Fsecret.png")
    assert "image" not in bad.headers.get("content-type", "")
    assert TestClient(app).get("/api/public/site-media/abc.png").status_code == 404
    client.put("/api/portal/settings", json={"site": {"projects": []}})
