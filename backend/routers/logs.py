# backend/routers/logs.py
import os
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from backend.logger import read_log_entries, list_log_dates

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _get_base_dir() -> str:
    return os.getenv("DOWNLOAD_DIR", "downloads")


@router.get("/dates")
def get_log_dates():
    return list_log_dates(base_dir=_get_base_dir())


@router.get("")
def get_logs(date: str = Query(..., description="YYYY-MM-DD")):
    return read_log_entries(date, base_dir=_get_base_dir())


@router.delete("")
def delete_log(date: str = Query(..., description="YYYY-MM-DD")):
    """删除指定日期的日志文件"""
    log_file = Path(_get_base_dir()) / "logs" / f"{date}.jsonl"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"{date} 日志不存在")
    log_file.unlink()
    return {"ok": True, "deleted": date}


@router.delete("/all")
def clear_all_logs():
    """清空所有日志文件"""
    log_dir = Path(_get_base_dir()) / "logs"
    if not log_dir.exists():
        return {"ok": True, "deleted": 0}
    files = list(log_dir.glob("*.jsonl"))
    for f in files:
        f.unlink()
    return {"ok": True, "deleted": len(files)}
