# tests/test_routers_llm.py
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


def test_list_llm_empty(client):
    resp = client.get("/api/llm")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_llm_config(client):
    resp = client.post("/api/llm", json={
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "is_default": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "DeepSeek"
    assert data["is_default"] is True
    assert "prompt_template" in data


def test_update_llm_config(client):
    resp = client.post("/api/llm", json={
        "name": "old", "base_url": "https://x.com/v1", "model": "m1"
    })
    lid = resp.json()["id"]
    resp = client.put(f"/api/llm/{lid}", json={"model": "m2"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "m2"


def test_delete_llm_config(client):
    resp = client.post("/api/llm", json={
        "name": "tmp", "base_url": "https://x.com/v1", "model": "m"
    })
    lid = resp.json()["id"]
    client.delete(f"/api/llm/{lid}")
    assert all(c["id"] != lid for c in client.get("/api/llm").json())


def test_set_default_clears_others(client):
    client.post("/api/llm", json={"name": "A", "base_url": "https://a.com/v1", "model": "m", "is_default": True})
    resp = client.post("/api/llm", json={"name": "B", "base_url": "https://b.com/v1", "model": "m"})
    lid_b = resp.json()["id"]
    client.post(f"/api/llm/{lid_b}/set-default")
    configs = {c["name"]: c for c in client.get("/api/llm").json()}
    assert configs["A"]["is_default"] is False
    assert configs["B"]["is_default"] is True


def test_llm_not_found(client):
    assert client.put("/api/llm/9999", json={"model": "x"}).status_code == 404
    assert client.delete("/api/llm/9999").status_code == 404


def test_search_config_llm_filter_enabled(client):
    resp = client.post("/api/configs", json={
        "name": "test", "query": "美食", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 10, "enabled": True,
        "cron": "0 9 * * *", "feishu_webhook": "",
        "llm_filter_enabled": True,
    })
    assert resp.status_code == 200
    assert resp.json()["llm_filter_enabled"] is True


def test_search_config_llm_filter_default_false(client):
    resp = client.post("/api/configs", json={
        "name": "no_llm", "query": "美食", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 10, "enabled": True,
        "cron": "0 9 * * *", "feishu_webhook": "",
    })
    assert resp.status_code == 200
    assert resp.json()["llm_filter_enabled"] is False
