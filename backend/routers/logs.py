# backend/routers/logs.py
import os
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from backend.database import get_engine
from backend.models import AppSetting, TaskRecord, SearchConfig
from backend.logger import read_log_entries, list_log_dates, read_log_entries_by_task

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _get_base_dir() -> str:
    """优先读数据库 download_dir 设置，其次 env，最后默认值。"""
    try:
        with Session(get_engine()) as session:
            s = session.exec(select(AppSetting).where(AppSetting.key == "download_dir")).first()
            if s and s.value:
                return s.value
    except Exception:
        pass
    return os.getenv("DOWNLOAD_DIR", "downloads")


@router.get("/task/{task_id}")
def get_logs_by_task(task_id: int):
    return read_log_entries_by_task(task_id, base_dir=_get_base_dir())


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


class ResendRequest(BaseModel):
    task_id: int
    aweme_ids: list[str]


@router.post("/resend")
async def resend_items(body: ResendRequest):
    """重新推送指定条目（不走 LLM 过滤）"""
    engine = get_engine()
    base_dir = _get_base_dir()

    # 找 task 对应的配置，用于获取渠道
    with Session(engine) as session:
        task = session.get(TaskRecord, body.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        config = session.get(SearchConfig, task.config_id)
        config_name = config.name if config else ""
        channel_id = config.channel_id if config else None
        feishu_webhook = config.feishu_webhook if config else ""

    from backend.task_runner import _get_channel_config
    channel_cfg = _get_channel_config(channel_id, feishu_webhook, engine)
    if not channel_cfg or not channel_cfg.get("app_id") or not channel_cfg.get("chat_id"):
        raise HTTPException(status_code=400, detail="未配置推送渠道")

    # 从日志里找到对应条目
    all_entries = read_log_entries_by_task(body.task_id, base_dir=base_dir)
    id_set = set(body.aweme_ids)
    items = [e for e in all_entries if e.get("aweme_id") in id_set]
    if not items:
        raise HTTPException(status_code=404, detail="未找到对应采集记录")

    from backend.notify.feishu import FeishuNotifier
    notifier = FeishuNotifier(
        app_id=channel_cfg["app_id"],
        app_secret=channel_cfg["app_secret"],
        chat_id=channel_cfg["chat_id"],
    )
    try:
        sent = await notifier.send_media_items(items, config_name=config_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "推送失败，请检查渠道配置")
    return {"ok": True, "sent": sent, "total": len(items)}
