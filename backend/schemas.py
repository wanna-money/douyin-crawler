from pydantic import BaseModel
from typing import Optional

_DEFAULT_PROMPT = (
    '判断以下抖音视频内容是否与搜索关键词相关。\n'
    '只回答“是”或“否”，不要解释。\n\n'
    '搜索关键词：{keyword}\n'
    '视频描述：{desc}\n'
    '作者：{author}\n\n'
    '是否相关：'
)


class SearchConfigCreate(BaseModel):
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
    channel_id: Optional[int] = None
    llm_filter_enabled: bool = False


class SearchConfigUpdate(BaseModel):
    name: Optional[str] = None
    query: Optional[str] = None
    search_type: Optional[str] = None
    sort_type: Optional[int] = None
    publish_time: Optional[int] = None
    content_type: Optional[int] = None
    filter_duration: Optional[str] = None
    limit: Optional[int] = None
    enabled: Optional[bool] = None
    cron: Optional[str] = None
    feishu_webhook: Optional[str] = None
    channel_id: Optional[int] = None
    llm_filter_enabled: Optional[bool] = None


class CookieAccountCreate(BaseModel):
    name: str
    cookie: str
    note: str = ""
    is_default: bool = False


class CookieAccountUpdate(BaseModel):
    name: Optional[str] = None
    cookie: Optional[str] = None
    note: Optional[str] = None
    is_default: Optional[bool] = None


class NotifyChannelCreate(BaseModel):
    name: str
    channel_type: str = "feishu_bot"
    app_id: str = ""
    app_secret: str = ""
    chat_id: str = ""
    is_default: bool = False


class NotifyChannelUpdate(BaseModel):
    name: Optional[str] = None
    channel_type: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    chat_id: Optional[str] = None
    is_default: Optional[bool] = None


class LLMConfigCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    model: str = "gpt-4o-mini"
    prompt_template: str = _DEFAULT_PROMPT
    is_default: bool = False


class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    prompt_template: Optional[str] = None
    is_default: Optional[bool] = None


class TaskTriggerResponse(BaseModel):
    task_id: int
    message: str


class SettingUpdate(BaseModel):
    value: str
