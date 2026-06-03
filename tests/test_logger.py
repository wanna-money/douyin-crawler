# tests/test_logger.py
import json
import pytest
from pathlib import Path
from backend.logger import write_log_entry, read_log_entries, list_log_dates


def test_write_and_read_log(tmp_path):
    entry = {
        "ts": "2026-06-03T09:00:00+00:00",
        "task_id": 1,
        "config_name": "美食",
        "aweme_id": "123",
        "media_type": "video",
        "author": "测试",
        "desc": "test desc",
        "video_url": "https://example.com/v.mp4",
        "image_urls": [],
        "downloaded": True,
        "file_paths": ["/tmp/123.mp4"],
        "sent": True,
        "error": None,
    }
    write_log_entry(entry, base_dir=str(tmp_path))
    results = read_log_entries("2026-06-03", base_dir=str(tmp_path))
    assert len(results) == 1
    assert results[0]["aweme_id"] == "123"
    assert results[0]["downloaded"] is True


def test_write_multiple_entries(tmp_path):
    for i in range(3):
        write_log_entry({
            "ts": f"2026-06-03T09:0{i}:00+00:00",
            "task_id": i,
            "config_name": "test",
            "aweme_id": str(i),
            "media_type": "video",
            "author": "a",
            "desc": "",
            "video_url": None,
            "image_urls": [],
            "downloaded": False,
            "file_paths": [],
            "sent": False,
            "error": "timeout",
        }, base_dir=str(tmp_path))
    results = read_log_entries("2026-06-03", base_dir=str(tmp_path))
    assert len(results) == 3


def test_read_nonexistent_date(tmp_path):
    results = read_log_entries("2000-01-01", base_dir=str(tmp_path))
    assert results == []


def test_list_log_dates(tmp_path):
    for date in ["2026-06-01", "2026-06-02", "2026-06-03"]:
        write_log_entry({
            "ts": f"{date}T09:00:00+00:00",
            "task_id": 1, "config_name": "t", "aweme_id": "1",
            "media_type": "video", "author": "a", "desc": "",
            "video_url": None, "image_urls": [], "downloaded": True,
            "file_paths": [], "sent": False, "error": None,
        }, base_dir=str(tmp_path))
    dates = list_log_dates(base_dir=str(tmp_path))
    assert "2026-06-03" in dates
    assert "2026-06-01" in dates
    assert len(dates) == 3


def test_write_entry_with_unknown_ts(tmp_path):
    entry = {
        "ts": "",
        "task_id": 1, "config_name": "t", "aweme_id": "x",
        "media_type": "video", "author": "a", "desc": "",
        "video_url": None, "image_urls": [], "downloaded": False,
        "file_paths": [], "sent": False, "error": "fail",
    }
    write_log_entry(entry, base_dir=str(tmp_path))
    results = read_log_entries("unknown", base_dir=str(tmp_path))
    assert len(results) == 1


def test_skip_malformed_lines(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "2026-06-03.jsonl"
    log_file.write_text('{"valid": true}\nNOT_JSON\n{"also": "valid"}\n')
    results = read_log_entries("2026-06-03", base_dir=str(tmp_path))
    assert len(results) == 2
