# tests/test_routers_tasks_logs.py
"""
任务记录路由：删除单条、清空全部、trigger 404
采集日志路由：删除指定日期、清空所有日志
SeenRecord 模型：去重隔离
"""
import json
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.database import get_engine, init_db
from backend.main import create_app
from backend.models import TaskRecord, SearchConfig, SeenRecord


# ── fixtures ──────────────────────────────────────────────

@pytest.fixture
def client():
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_tasks():
    """预置 1 个 config 和 3 条任务记录"""
    engine = get_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        cfg = SearchConfig(name="test", query="kw", search_type="search", limit=5)
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        for i in range(3):
            s.add(TaskRecord(config_id=cfg.id, status="done"))
        s.commit()
    app = create_app(engine=engine)
    with TestClient(app) as c:
        yield c, engine


@pytest.fixture
def client_with_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-06-01.jsonl").write_text(
        '{"ts":"2026-06-01T09:00:00+00:00","aweme_id":"1","config_name":"c","media_type":"video",'
        '"author":"a","desc":"d","downloaded":true,"sent":false,"error":null,"task_id":1,'
        '"video_url":null,"image_urls":[],"file_paths":[]}\n',
        encoding="utf-8"
    )
    (log_dir / "2026-06-02.jsonl").write_text(
        '{"ts":"2026-06-02T09:00:00+00:00","aweme_id":"2","config_name":"c","media_type":"video",'
        '"author":"a","desc":"d","downloaded":true,"sent":false,"error":null,"task_id":2,'
        '"video_url":null,"image_urls":[],"file_paths":[]}\n',
        encoding="utf-8"
    )
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    with TestClient(app) as c:
        yield c, tmp_path


# ── 任务记录：删除 & 清空 ──────────────────────────────────

def test_delete_task_success(client_with_tasks):
    client, engine = client_with_tasks
    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 3
    task_id = tasks[0]["id"]

    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    remaining = client.get("/api/tasks").json()
    assert len(remaining) == 2
    assert all(t["id"] != task_id for t in remaining)


def test_delete_task_not_found(client):
    resp = client.delete("/api/tasks/9999")
    assert resp.status_code == 404


def test_clear_all_tasks(client_with_tasks):
    client, engine = client_with_tasks
    assert len(client.get("/api/tasks").json()) == 3

    resp = client.delete("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["deleted"] == 3

    assert client.get("/api/tasks").json() == []


def test_clear_tasks_when_empty(client):
    resp = client.delete("/api/tasks")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


def test_trigger_task_not_found(client):
    resp = client.post("/api/tasks/trigger/9999")
    assert resp.status_code == 404


# ── 采集日志：删除 & 清空 ──────────────────────────────────

def test_delete_log_by_date(client_with_logs):
    client, tmp_path = client_with_logs

    dates = client.get("/api/logs/dates").json()
    assert "2026-06-01" in dates

    resp = client.delete("/api/logs?date=2026-06-01")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "2026-06-01"

    dates_after = client.get("/api/logs/dates").json()
    assert "2026-06-01" not in dates_after
    assert "2026-06-02" in dates_after


def test_delete_log_not_found(client_with_logs):
    client, _ = client_with_logs
    resp = client.delete("/api/logs?date=2000-01-01")
    assert resp.status_code == 404


def test_clear_all_logs(client_with_logs):
    client, tmp_path = client_with_logs

    assert len(client.get("/api/logs/dates").json()) == 2

    resp = client.delete("/api/logs/all")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    assert client.get("/api/logs/dates").json() == []


def test_clear_all_logs_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path))
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    with TestClient(app) as client:
        resp = client.delete("/api/logs/all")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


# ── SeenRecord 模型测试 ────────────────────────────────────

def test_seen_record_created_correctly():
    engine = get_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(SeenRecord(aweme_id="abc123", config_id=1))
        s.add(SeenRecord(aweme_id="def456", config_id=1))
        s.add(SeenRecord(aweme_id="abc123", config_id=2))  # 不同 config，不算重复
        s.commit()

        all_seen = s.exec(select(SeenRecord)).all()
        assert len(all_seen) == 3


def test_seen_record_query_by_config():
    engine = get_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(SeenRecord(aweme_id="id1", config_id=1))
        s.add(SeenRecord(aweme_id="id2", config_id=1))
        s.add(SeenRecord(aweme_id="id3", config_id=2))
        s.commit()

    with Session(engine) as s:
        c1_ids = {r.aweme_id for r in s.exec(
            select(SeenRecord).where(SeenRecord.config_id == 1)
        ).all()}
        c2_ids = {r.aweme_id for r in s.exec(
            select(SeenRecord).where(SeenRecord.config_id == 2)
        ).all()}

    assert c1_ids == {"id1", "id2"}
    assert c2_ids == {"id3"}
