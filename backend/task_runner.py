# backend/task_runner.py
import json
import logging
import os
import httpx
from datetime import datetime, timezone, timedelta
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


_CST = timezone(timedelta(hours=8))


def _utcnow() -> datetime:
    return datetime.now(_CST)


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
        def _ch_to_dict(ch) -> dict:
            return {
                "channel_type": ch.channel_type,
                "name": ch.name,
                "app_id": ch.app_id,
                "app_secret": ch.app_secret,
                "chat_id": ch.chat_id,
            }
        if config_channel_id:
            ch = session.get(NotifyChannel, config_channel_id)
            if ch:
                return _ch_to_dict(ch)
        ch = session.exec(
            select(NotifyChannel).where(NotifyChannel.is_default == True)
        ).first()
        if ch:
            return _ch_to_dict(ch)
        ch = session.exec(select(NotifyChannel)).first()
        if ch:
            return _ch_to_dict(ch)
        return None


def _channel_cfg_is_valid(cfg: dict) -> bool:
    return bool(cfg.get("app_id") and cfg.get("chat_id"))


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
        config_llm_prompt_template = config.llm_prompt_template

    try:
        new_items: list = []
        downloaded_items: list = []
        cookie = _get_default_cookie(engine) or os.getenv("DOUYIN_COOKIE", "")
        download_dir = get_setting("download_dir", os.getenv("DOWNLOAD_DIR", "downloads"), engine) or os.getenv("DOWNLOAD_DIR", "downloads")
        channel_cfg = _get_channel_config(config_channel_id, config_feishu_webhook, engine)

        client = DouyinClient(cookie=cookie)
        searcher = DouyinSearcher(client)
        downloader = Downloader(client=client, base_dir=download_dir)

        # 预先加载历史去重集合
        with Session(engine) as session:
            existing_ids = set(
                row.aweme_id for row in session.exec(
                    select(SeenRecord).where(SeenRecord.config_id == config_id)
                ).all()
            )

        nil_reason: str | None = None
        user_notes: list[str] = []

        if config_search_type == "user":
            # query 存储多用户 JSON：[{"sec_uid": "...", "limit": 20, "nickname": "..."}, ...]
            # 兼容直接填 sec_uid 字符串的情况
            try:
                user_entries = json.loads(config_query)
                if isinstance(user_entries, str):
                    user_entries = [{"sec_uid": user_entries, "limit": config_limit}]
            except (json.JSONDecodeError, TypeError):
                user_entries = [{"sec_uid": config_query, "limit": config_limit}]

            nil_reasons = []
            user_notes = []  # 记录每个用户的采集摘要（含错误）
            for entry in user_entries:
                sec_uid = entry.get("sec_uid", "").strip()
                per_limit = int(entry.get("limit", config_limit))
                tab = entry.get("tab", "post")
                id_type = entry.get("id_type", "sec_uid")  # "sec_uid" 或 "douyin_id"
                display_name = entry.get("nickname") or sec_uid[:12]
                if not sec_uid:
                    continue
                # 支持粘贴完整主页链接，自动提取 sec_uid
                if sec_uid.startswith("http"):
                    from urllib.parse import urlparse
                    parsed_path = urlparse(sec_uid).path.rstrip("/").split("/")
                    # 取最后一段，过滤掉空字符串和 'user' 字面量
                    candidate = parsed_path[-1] if parsed_path else ""
                    if not candidate or candidate == "user":
                        msg = f"{display_name}：主页链接无法解析出 sec_uid（URL 格式不正确）"
                        nil_reasons.append(msg)
                        user_notes.append(f"✗ {msg}")
                        continue
                    sec_uid = candidate
                # 抖音号模式：先通过搜索解析出 sec_uid（与 URL 模式互斥）
                elif id_type == "douyin_id":
                    resolved = await searcher.resolve_sec_uid(sec_uid)
                    if not resolved:
                        msg = f"{display_name}：抖音号未找到对应用户"
                        nil_reasons.append(msg)
                        user_notes.append(f"✗ {msg}")
                        continue
                    sec_uid = resolved
                user_exclude = existing_ids | {it["aweme_id"] for it in new_items}
                items, reason = await searcher.search_user_profile(
                    sec_uid=sec_uid,
                    limit=per_limit,
                    tab=tab,
                    exclude_ids=user_exclude,
                )
                new_items.extend(items)
                if reason:
                    msg = f"{display_name}：{reason}"
                    nil_reasons.append(msg)
                    user_notes.append(f"✗ {msg}")
                elif items:
                    user_notes.append(f"✓ {display_name}：获取 {len(items)} 条")
                else:
                    user_notes.append(f"- {display_name}：无新内容")
            if nil_reasons and not new_items:
                nil_reason = "；".join(nil_reasons)
        else:
            # 将历史 id 传入，搜索器内部持续翻页直到凑够 limit 条新内容
            new_items, nil_reason = await searcher.search_keyword(
                keyword=config_query,
                limit=config_limit,
                sort_type=config_sort_type,
                publish_time=config_publish_time,
                content_type=config_content_type,
                filter_duration=config_filter_duration,
                exclude_ids=existing_ids,
            )

        # LLM 相关性过滤
        new_items_before_llm: list = []
        if config_llm_filter_enabled:
            new_items_before_llm = new_items
            llm_cfg = _get_default_llm(engine)
            if llm_cfg:
                filtered = []
                for item in new_items:
                    media_type = item.get("media_type", "")
                    image_urls = item.get("image_urls", [])
                    cover_url = item.get("cover_url", "")

                    if media_type == "image" and image_urls:
                        # 图文：每张图单独判断，有一张通过就推送，只推通过的图
                        media_details = []
                        passed_indices = []
                        for idx, img_url in enumerate(image_urls):
                            relevant, llm_curl = await check_relevance(
                                keyword=config_query,
                                desc=item.get("desc", ""),
                                author=item.get("author", ""),
                                cover_url=img_url,
                                prompt_template=config_llm_prompt_template,
                                **llm_cfg,
                            )
                            media_details.append({
                                "url": img_url,
                                "llm_filtered": not relevant,
                                "llm_curl": llm_curl,
                            })
                            if relevant:
                                passed_indices.append(idx)
                        item["media_details"] = media_details
                        if passed_indices:
                            # 只保留通过的图片
                            item["llm_passed_image_indices"] = passed_indices
                            filtered.append(item)
                        else:
                            logger.info("LLM 过滤: aweme_id=%s 所有图片不相关，跳过", item.get("aweme_id"))
                            item["llm_filtered"] = True
                    else:
                        # 视频：用封面图判断一次
                        relevant, llm_curl = await check_relevance(
                            keyword=config_query,
                            desc=item.get("desc", ""),
                            author=item.get("author", ""),
                            cover_url=cover_url,
                            prompt_template=config_llm_prompt_template,
                            **llm_cfg,
                        )
                        item["media_details"] = [{
                            "url": cover_url or item.get("video_url", ""),
                            "llm_filtered": not relevant,
                            "llm_curl": llm_curl,
                        }]
                        item["llm_curl"] = llm_curl
                        if relevant:
                            filtered.append(item)
                        else:
                            logger.info("LLM 过滤: aweme_id=%s 不相关，跳过", item.get("aweme_id"))
                            item["llm_filtered"] = True
                new_items = filtered
            else:
                logger.warning("llm_filter_enabled=True 但未配置 LLM，跳过过滤")

        # 写入被 LLM 过滤掉的内容日志（llm_filtered=True）
        for item in [it for it in (new_items_before_llm if config_llm_filter_enabled else []) if it.get("llm_filtered")]:
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
                    "cover_url": item.get("cover_url"),
                    "image_urls": item.get("image_urls", []),
                    "downloaded": False,
                    "file_paths": [],
                    "sent": False,
                    "llm_filtered": True,
                    "llm_curl": item.get("llm_curl", ""),
                    "media_details": item.get("media_details", []),
                    "error": None,
                }, base_dir=download_dir)
            except Exception as log_exc:
                logger.warning("LLM 过滤日志写入失败 aweme_id=%s: %s", item.get("aweme_id"), log_exc)

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
                    "cover_url": item.get("cover_url"),
                    "image_urls": item.get("image_urls", []),
                    "downloaded": error_msg is None,
                    "file_paths": item.get("file_paths", []),
                    "sent": False,
                    "llm_filtered": False,
                    "llm_curl": item.get("llm_curl", ""),
                    "media_details": item.get("media_details", []),
                    "error": error_msg,
                }, base_dir=download_dir)
            except Exception as log_exc:
                logger.warning("日志写入失败 aweme_id=%s: %s", item.get("aweme_id"), log_exc)

        sent = 0
        if channel_cfg and downloaded_items:
            if channel_cfg.get("channel_type", "feishu_bot") == "feishu_bot" and channel_cfg.get("app_id") and channel_cfg.get("chat_id"):
                notifier = FeishuNotifier(
                    app_id=channel_cfg["app_id"],
                    app_secret=channel_cfg["app_secret"],
                    chat_id=channel_cfg["chat_id"],
                )
                sent = await notifier.send_media_items(downloaded_items, config_name=config_name)
            if sent > 0:
                with Session(engine) as session:
                    for item in downloaded_items:
                        for r in session.exec(
                            select(DownloadRecord).where(DownloadRecord.aweme_id == item["aweme_id"])
                        ).all():
                            r.sent = True
                    session.commit()
            # 推送成功后才写入 SeenRecord，避免推送失败导致内容永久丢失
            if sent > 0:
                with Session(engine) as session:
                    for item in downloaded_items:
                        session.add(SeenRecord(
                            aweme_id=str(item["aweme_id"]),
                            config_id=config_id,
                        ))
                    session.commit()
        elif downloaded_items:
            # 无推送渠道时，下载成功即视为已处理，写入 SeenRecord
            with Session(engine) as session:
                for item in downloaded_items:
                    session.add(SeenRecord(
                        aweme_id=str(item["aweme_id"]),
                        config_id=config_id,
                    ))
                session.commit()

        with Session(engine) as session:
            task = session.get(TaskRecord, task_id)
            task.status = "done"
            llm_filtered_count = len(new_items_before_llm) - len(new_items) if config_llm_filter_enabled else 0
            items_before_filter = new_items_before_llm if config_llm_filter_enabled else new_items
            task.total = len(items_before_filter)
            task.new_count = len(new_items)
            task.downloaded = len(downloaded_items)
            task.sent = sent
            task.finished_at = _utcnow()
            if nil_reason:
                task.note = f"搜索无结果：{nil_reason}"
            elif config_search_type == "user" and user_notes:
                # user 模式：汇总每个用户的采集结果，含错误详情
                task.note = "；".join(user_notes)
            elif llm_filtered_count > 0 and len(new_items) == 0:
                task.note = f"全部被 LLM 过滤（{llm_filtered_count} 条）"
            elif llm_filtered_count > 0 and len(new_items) > 0:
                task.note = f"LLM 过滤 {llm_filtered_count} 条，剩余 {len(new_items)} 条"
            elif len(items_before_filter) == 0:
                task.note = "无新内容（全部为历史重复）"
            elif len(new_items) > 0 and len(downloaded_items) == 0:
                task.note = f"新内容 {len(new_items)} 条，下载全部失败"
            elif channel_cfg and not _channel_cfg_is_valid(channel_cfg):
                task.note = "未配置通知渠道必要参数，跳过推送"
            session.add(task)
            session.commit()

    except Exception as e:
        if task_id is not None:
            with Session(engine) as session:
                task = session.get(TaskRecord, task_id)
                if task:
                    task.status = "failed"
                    llm_filtered_count = len(new_items_before_llm) - len(new_items) if config_llm_filter_enabled else 0
                    items_before_filter = new_items_before_llm if config_llm_filter_enabled else new_items
                    task.total = len(items_before_filter)
                    task.new_count = len(new_items)
                    task.downloaded = len(downloaded_items)
                    if isinstance(e, httpx.ConnectError):
                        task.error = f"网络连接失败（{type(e).__name__}）：{str(e) or '无法建立 TLS 连接，请检查网络或代理'}"
                    elif isinstance(e, (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout)):
                        task.error = f"请求超时（{type(e).__name__}）：{str(e) or '服务端无响应'}"
                    else:
                        task.error = str(e) or repr(e)
                    task.finished_at = _utcnow()
                    session.add(task)
                    session.commit()
        raise

    return task_id
