# tests/test_routers_logs.py
import os
import json
import pytest
from fastapi.testclient import TestClient
from backend.database import get_engine, init_db
from backend.main import create_app


@pytest.fixture
def client_with_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path))
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    # 预写一些日志
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-06-03.jsonl").write_text(
        '{"ts":"2026-06-03T09:00:00+00:00","aweme_id":"111","config_name":"美食","media_type":"video","author":"A","desc":"d","downloaded":true,"sent":true,"error":null,"task_id":1,"video_url":null,"image_urls":[],"file_paths":[]}\n'
        '{"ts":"2026-06-03T10:00:00+00:00","aweme_id":"222","config_name":"旅行","media_type":"image","author":"B","desc":"d2","downloaded":false,"sent":false,"error":"timeout","task_id":1,"video_url":null,"image_urls":[],"file_paths":[]}\n',
        encoding="utf-8"
    )
    (log_dir / "2026-06-02.jsonl").write_text(
        '{"ts":"2026-06-02T08:00:00+00:00","aweme_id":"333","config_name":"美食","media_type":"video","author":"C","desc":"d3","downloaded":true,"sent":true,"error":null,"task_id":2,"video_url":null,"image_urls":[],"file_paths":[]}\n',
        encoding="utf-8"
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path))
    engine = get_engine(":memory:")
    init_db(engine)
    app = create_app(engine=engine)
    with TestClient(app) as c:
        yield c


def test_get_log_dates(client_with_logs):
    resp = client_with_logs.get("/api/logs/dates")
    assert resp.status_code == 200
    dates = resp.json()
    assert "2026-06-03" in dates
    assert "2026-06-02" in dates
    assert len(dates) == 2


def test_get_log_dates_empty(client_empty):
    resp = client_empty.get("/api/logs/dates")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_logs_by_date(client_with_logs):
    resp = client_with_logs.get("/api/logs?date=2026-06-03")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 2
    aweme_ids = {e["aweme_id"] for e in entries}
    assert "111" in aweme_ids
    assert "222" in aweme_ids


def test_get_logs_another_date(client_with_logs):
    resp = client_with_logs.get("/api/logs?date=2026-06-02")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["aweme_id"] == "333"


def test_get_logs_nonexistent_date(client_with_logs):
    resp = client_with_logs.get("/api/logs?date=2000-01-01")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_logs_requires_date_param(client_empty):
    resp = client_empty.get("/api/logs")
    assert resp.status_code == 422  # missing required query param
