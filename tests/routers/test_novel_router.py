import json
from fastapi.testclient import TestClient
from app.main import create_app


def test_create_novel_endpoint():
    client = TestClient(create_app())
    resp = client.post("/api/novels", json={"name": "my_novel"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "my_novel"


def test_list_novels_endpoint():
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "list_test"})
    resp = client.get("/api/novels")
    assert resp.status_code == 200
    names = [n["name"] for n in resp.json()]
    assert "list_test" in names


def test_upload_novel_endpoint():
    client = TestClient(create_app())
    data = json.dumps([{"start_line": 1, "title": "ch1", "text": "hello"}])
    resp = client.post(
        "/api/novels/upload",
        data={"name": "uploaded_novel"},
        files={"file": ("novel.json", data, "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json()["chapter_count"] == 1


def test_get_chapters_endpoint():
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "chapters_test"})
    resp = client.get("/api/novels/chapters_test/chapters")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
