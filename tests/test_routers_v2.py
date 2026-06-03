# tests/test_routers_v2.py
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


# ===== Cookie 测试 =====

def test_list_cookies_empty(client):
    resp = client.get("/api/cookies")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_cookie(client):
    resp = client.post("/api/cookies", json={"name": "主号", "cookie": "sid=abc", "is_default": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "主号"
    assert data["is_default"] is True
    assert data["id"] is not None


def test_create_and_list_cookie(client):
    client.post("/api/cookies", json={"name": "主号", "cookie": "sid=abc", "is_default": True})
    resp = client.get("/api/cookies")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_cookie(client):
    resp = client.post("/api/cookies", json={"name": "旧名", "cookie": "old=1"})
    cid = resp.json()["id"]
    resp = client.put(f"/api/cookies/{cid}", json={"name": "新名"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名"


def test_delete_cookie(client):
    resp = client.post("/api/cookies", json={"name": "tmp", "cookie": "x=1"})
    cid = resp.json()["id"]
    client.delete(f"/api/cookies/{cid}")
    assert all(c["id"] != cid for c in client.get("/api/cookies").json())


def test_set_default_cookie_clears_others(client):
    client.post("/api/cookies", json={"name": "号A", "cookie": "a=1", "is_default": True})
    resp = client.post("/api/cookies", json={"name": "号B", "cookie": "b=2", "is_default": False})
    id_b = resp.json()["id"]
    client.post(f"/api/cookies/{id_b}/set-default")
    cookies = {c["name"]: c for c in client.get("/api/cookies").json()}
    assert cookies["号A"]["is_default"] is False
    assert cookies["号B"]["is_default"] is True


def test_cookie_not_found(client):
    resp = client.put("/api/cookies/9999", json={"name": "x"})
    assert resp.status_code == 404
    resp = client.delete("/api/cookies/9999")
    assert resp.status_code == 404


# ===== Channel 测试 =====

def test_list_channels_empty(client):
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_channel(client):
    resp = client.post("/api/channels", json={
        "name": "美食团队", "app_id": "cli_abc", "app_secret": "sec", "chat_id": "oc_123", "is_default": True
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "美食团队"
    assert data["channel_type"] == "feishu_bot"
    assert data["is_default"] is True
    assert data["app_id"] == "cli_abc"
    assert data["chat_id"] == "oc_123"


def test_create_and_list_channel(client):
    client.post("/api/channels", json={"name": "ch", "app_id": "cli_x", "app_secret": "s", "chat_id": "oc_x"})
    resp = client.get("/api/channels")
    assert len(resp.json()) == 1


def test_update_channel(client):
    resp = client.post("/api/channels", json={"name": "旧", "app_id": "cli_1", "app_secret": "s", "chat_id": "oc_1"})
    cid = resp.json()["id"]
    resp = client.put(f"/api/channels/{cid}", json={"name": "新"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新"


def test_delete_channel(client):
    resp = client.post("/api/channels", json={"name": "tmp", "app_id": "cli_t", "app_secret": "s", "chat_id": "oc_t"})
    cid = resp.json()["id"]
    client.delete(f"/api/channels/{cid}")
    assert all(c["id"] != cid for c in client.get("/api/channels").json())


def test_set_default_channel_clears_others(client):
    client.post("/api/channels", json={"name": "ch1", "app_id": "cli_a", "app_secret": "s", "chat_id": "oc_a", "is_default": True})
    resp = client.post("/api/channels", json={"name": "ch2", "app_id": "cli_b", "app_secret": "s", "chat_id": "oc_b"})
    cid2 = resp.json()["id"]
    client.post(f"/api/channels/{cid2}/set-default")
    chs = {c["name"]: c for c in client.get("/api/channels").json()}
    assert chs["ch1"]["is_default"] is False
    assert chs["ch2"]["is_default"] is True


def test_channel_not_found(client):
    resp = client.put("/api/channels/9999", json={"name": "x"})
    assert resp.status_code == 404
    resp = client.delete("/api/channels/9999")
    assert resp.status_code == 404


# ===== SearchConfig 绑定 channel_id =====

def test_config_with_channel_id(client):
    resp = client.post("/api/channels", json={"name": "ch1", "app_id": "cli_a", "app_secret": "s", "chat_id": "oc_a"})
    ch_id = resp.json()["id"]
    resp = client.post("/api/configs", json={
        "name": "test", "query": "kw", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 10, "enabled": True,
        "cron": "0 9 * * *", "feishu_webhook": "", "channel_id": ch_id
    })
    assert resp.status_code == 200
    assert resp.json()["channel_id"] == ch_id


def test_config_without_channel_id(client):
    resp = client.post("/api/configs", json={
        "name": "no_ch", "query": "kw", "search_type": "search",
        "sort_type": 0, "publish_time": 0, "content_type": 0,
        "filter_duration": "", "limit": 10, "enabled": True,
        "cron": "0 9 * * *", "feishu_webhook": ""
    })
    assert resp.status_code == 200
    assert resp.json()["channel_id"] is None
