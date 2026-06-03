# backend/task_runner.py
import logging
import os
from datetime import datetime, timezone
from sqlmodel import Session, select
from backend.database import get_engine
from backend.models import (
    SearchConfig, TaskRecord, DownloadRecord, SeenRecord,
    AppSetting, CookieAccount, NotifyChannel, LLMConfig,
)
from backend.crawler.client import DouyinClient
from backend.crawler.search import DouyinSearcher
from backend.crawler.downloader import Downloader
from backend.notify.feishu import FeishuNotifier
from backend.logger import write_log_entry
from backend.llm import check_relevance

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_setting(key: str, default: str = "", engine=None) -> str:
    if engine is None:
        engine = get_engine()
    with Session(engine) as session:
        stmt = select(AppSetting).where(AppSetting.key == key)
        setting = session.exec(stmt).first()
        return setting.value if setting else default


def _get_default_cookie(engine) -> str:
    with Session(engine) as session:
        acc = session.exec(
            select(CookieAccount).where(CookieAccount.is_default == True)
        ).first()
        if acc:
            return acc.cookie
        acc = session.exec(select(CookieAccount)).first()
        return acc.cookie if acc else ""


def _get_webhook(config_channel_id: int | None, config_feishu_webhook: str, engine) -> str:
    if config_feishu_webhook:
        return config_feishu_webhook
    with Session(engine) as session:
        if config_channel_id:
            ch = session.get(NotifyChannel, config_channel_id)
            if ch:
                return ch.webhook_url
        ch = session.exec(
            select(NotifyChannel).where(NotifyChannel.is_default == True)
        ).first()
        if ch:
            return ch.webhook_url
        ch = session.exec(select(NotifyChannel)).first()
        return ch.webhook_url if ch else ""


def _get_channel_config(config_channel_id: int | None, config_feishu_webhook: str, engine) -> dict | None:
    """返回渠道配置字典，优先用绑定渠道，其次用默认渠道"""
    with Session(engine) as session:
        if config_channel_id:
            ch = session.get(NotifyChannel, config_channel_id)
            if ch:
                return {"app_id": ch.app_id, "app_secret": ch.app_secret, "chat_id": ch.chat_id, "name": ch.name}
        ch = session.exec(
            select(NotifyChannel).where(NotifyChannel.is_default == True)
        ).first()
        if ch:
            return {"app_id": ch.app_id, "app_secret": ch.app_secret, "chat_id": ch.chat_id, "name": ch.name}
        ch = session.exec(select(NotifyChannel)).first()
        if ch:
            return {"app_id": ch.app_id, "app_secret": ch.app_secret, "chat_id": ch.chat_id, "name": ch.name}
        return None


def _get_default_llm(engine) -> dict | None:
    with Session(engine) as session:
        cfg = session.exec(
            select(LLMConfig).where(LLMConfig.is_default == True)
        ).first()
        if not cfg:
            cfg = session.exec(select(LLMConfig)).first()
        if cfg:
            return {
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
                "model": cfg.model,
                "prompt_template": cfg.prompt_template,
            }
        return None


async def run_task(config_id: int, engine=None) -> int:
    if engine is None:
        engine = get_engine()

    task_id: int | None = None
    with Session(engine) as session:
        config = session.get(SearchConfig, config_id)
        if not config:
            raise ValueError(f"Config {config_id} not found")
        task = TaskRecord(config_id=config_id, status="running", started_at=_utcnow())
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id
        config_name = config.name
        config_query = config.query
        config_search_type = config.search_type
        config_limit = config.limit
        config_sort_type = config.sort_type
        config_publish_time = config.publish_time
        config_content_type = config.content_type
        config_filter_duration = config.filter_duration
        config_feishu_webhook = config.feishu_webhook
        config_channel_id = config.channel_id
        config_llm_filter_enabled = config.llm_filter_enabled

    try:
        cookie = _get_default_cookie(engine) or os.getenv("DOUYIN_COOKIE", "")
        download_dir = get_setting("download_dir", os.getenv("DOWNLOAD_DIR", "downloads"), engine) or os.getenv("DOWNLOAD_DIR", "downloads")
        channel_cfg = _get_channel_config(config_channel_id, config_feishu_webhook, engine)

        client = DouyinClient(cookie=cookie)
        searcher = DouyinSearcher(client)
        downloader = Downloader(client=client, base_dir=download_dir)

        if config_search_type == "hashtag":
            items = await searcher.search_hashtag(config_query, limit=config_limit)
        else:
            items = await searcher.search_keyword(
                keyword=config_query,
                limit=config_limit,
                sort_type=config_sort_type,
                publish_time=config_publish_time,
                content_type=config_content_type,
                filter_duration=config_filter_duration,
            )

        # 去重：查询该配置曾经见过的 aweme_id
        with Session(engine) as session:
            existing_ids = set(
                row.aweme_id for row in session.exec(
                    select(SeenRecord).where(SeenRecord.config_id == config_id)
                ).all()
            )
        new_items = [it for it in items if it["aweme_id"] not in existing_ids]

        # 立即将本次搜索到的新内容写入 SeenRecord，无论后续下载是否成功
        if new_items:
            with Session(engine) as session:
                for item in new_items:
                    session.add(SeenRecord(
                        aweme_id=item["aweme_id"],
                        config_id=config_id,
                    ))
                session.commit()

        # LLM 相关性过滤
        if config_llm_filter_enabled:
            llm_cfg = _get_default_llm(engine)
            if llm_cfg:
                filtered = []
                for item in new_items:
                    relevant = await check_relevance(
                        keyword=config_query,
                        desc=item.get("desc", ""),
                        author=item.get("author", ""),
                        cover_url=item.get("cover_url", ""),
                        **llm_cfg,
                    )
                    if relevant:
                        filtered.append(item)
                    else:
                        logger.info("LLM 过滤: aweme_id=%s 不相关，跳过", item.get("aweme_id"))
                new_items = filtered
            else:
                logger.warning("llm_filter_enabled=True 但未配置 LLM，跳过过滤")

        downloaded_items = []
        for item in new_items:
            error_msg = None
            try:
                paths = await downloader.download(item)
                item["file_paths"] = paths
                downloaded_items.append(item)
                with Session(engine) as session:
                    for path in paths:
                        session.add(DownloadRecord(
                            task_id=task_id,
                            aweme_id=item["aweme_id"],
                            media_type=item["media_type"],
                            file_path=path,
                        ))
                    session.commit()
            except Exception as exc:
                logger.warning("下载失败 aweme_id=%s: %s", item.get("aweme_id"), exc)
                error_msg = str(exc)

            try:
                write_log_entry({
                    "ts": _utcnow().isoformat(),
                    "task_id": task_id,
                    "config_name": config_name,
                    "aweme_id": item.get("aweme_id", ""),
                    "media_type": item.get("media_type", ""),
                    "author": item.get("author", ""),
                    "desc": item.get("desc", "")[:200],
                    "video_url": item.get("video_url"),
                    "image_urls": item.get("image_urls", []),
                    "downloaded": error_msg is None,
                    "file_paths": item.get("file_paths", []),
                    "sent": False,
                    "error": error_msg,
                }, base_dir=download_dir)
            except Exception as log_exc:
                logger.warning("日志写入失败 aweme_id=%s: %s", item.get("aweme_id"), log_exc)

        sent = 0
        if channel_cfg and channel_cfg.get("app_id") and channel_cfg.get("chat_id") and downloaded_items:
            notifier = FeishuNotifier(
                app_id=channel_cfg["app_id"],
                app_secret=channel_cfg["app_secret"],
                chat_id=channel_cfg["chat_id"],
            )
            sent = await notifier.send_media_items(downloaded_items, config_name=config_name)
            with Session(engine) as session:
                for item in downloaded_items:
                    for r in session.exec(
                        select(DownloadRecord).where(DownloadRecord.aweme_id == item["aweme_id"])
                    ).all():
                        r.sent = True
                session.commit()

        with Session(engine) as session:
            task = session.get(TaskRecord, task_id)
            task.status = "done"
            task.total = len(items)
            task.downloaded = len(downloaded_items)
            task.sent = sent
            task.finished_at = _utcnow()
            session.add(task)
            session.commit()

    except Exception as e:
        if task_id is not None:
            with Session(engine) as session:
                task = session.get(TaskRecord, task_id)
                if task:
                    task.status = "failed"
                    task.error = str(e)
                    task.finished_at = _utcnow()
                    session.add(task)
                    session.commit()
        raise

    return task_id
