from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone, timedelta

_DEFAULT_PROMPT = (
    '判断以下抖音视频内容是否与搜索关键词相关。\n'
    '只回答“是”或“否”，不要解释。\n\n'
    '搜索关键词：{keyword}\n'
    '视频描述：{desc}\n'
    '作者：{author}\n\n'
    '是否相关：'
)


_CST = timezone(timedelta(hours=8))


def _utcnow() -> datetime:
    return datetime.now(_CST)


class CookieAccount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cookie: str
    note: str = ""
    is_default: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class NotifyChannel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    channel_type: str = "feishu_bot"   # feishu_bot
    app_id: str = ""
    app_secret: str = ""
    chat_id: str = ""                  # 群的 open_chat_id，如 oc_xxxxxx
    webhook_url: str = ""              # 保留兼容旧数据，新建时不用填
    is_default: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class LLMConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    base_url: str
    api_key: str = ""
    model: str = "gpt-4o-mini"
    is_default: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class SearchConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    query: str
    search_type: str = "search"
    sort_type: int = 0
    publish_time: int = 0
    content_type: int = 0
    filter_duration: str = ""
    limit: int = 50
    enabled: bool = True
    cron: str = "0 9 * * *"
    feishu_webhook: str = ""
    channel_id: Optional[int] = Field(default=None, foreign_key="notifychannel.id")
    llm_filter_enabled: bool = False
    llm_prompt_template: str = Field(default=_DEFAULT_PROMPT)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TaskRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    config_id: int
    status: str = "pending"
    total: int = 0
    new_count: int = 0
    downloaded: int = 0
    sent: int = 0
    note: str = ""
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class DownloadRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int
    aweme_id: str
    media_type: str
    file_path: str
    sent: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class SeenRecord(SQLModel, table=True):
    """记录已经搜索到过的内容，用于跨任务去重，防止重复推送"""
    id: Optional[int] = Field(default=None, primary_key=True)
    aweme_id: str = Field(index=True)
    config_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class AppSetting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True)
    value: str = ""
