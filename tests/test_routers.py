import pytest
from fastapi.testclient import TestClient
from backend.database import get_engine, init_db
from backend.main import create_app


@pytest.fixture
def client():
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    with TestClient(app) as c:
        yield c


def test_create_and_list_config(client):
    payload = {
        "name": "美食",
        "query": "美食探店",
        "search_type": "search",
        "sort_type": 2,
        "publish_time": 7,
        "content_type": 0,
        "filter_duration": "",
        "limit": 50,
        "enabled": True,
        "cron": "0 9 * * *",
        "feishu_webhook": "",
    }
    resp = client.post("/api/configs", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "美食"
    config_id = data["id"]

    resp = client.get("/api/configs")
    assert resp.status_code == 200
    assert any(c["id"] == config_id for c in resp.json())


def test_update_config(client):
    payload = {
        "name": "风景", "query": "风景", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 20, "enabled": True,
        "cron": "0 8 * * *", "feishu_webhook": "",
    }
    resp = client.post("/api/configs", json=payload)
    config_id = resp.json()["id"]

    resp = client.put(f"/api/configs/{config_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_delete_config(client):
    payload = {
        "name": "del", "query": "del", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 10, "enabled": True,
        "cron": "0 9 * * *", "feishu_webhook": "",
    }
    resp = client.post("/api/configs", json=payload)
    config_id = resp.json()["id"]
    resp = client.delete(f"/api/configs/{config_id}")
    assert resp.status_code == 200

    resp = client.get("/api/configs")
    assert all(c["id"] != config_id for c in resp.json())


def test_get_settings(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200


def test_update_setting(client):
    resp = client.put("/api/settings/douyin_cookie", json={"value": "test_cookie"})
    assert resp.status_code == 200
    resp = client.get("/api/settings")
    settings = {s["key"]: s["value"] for s in resp.json()}
    assert settings.get("douyin_cookie") == "test_cookie"
