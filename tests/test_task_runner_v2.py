# tests/test_task_runner_v2.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlmodel import Session
from backend.database import get_engine, init_db
from backend.models import SearchConfig, TaskRecord, CookieAccount, NotifyChannel
from backend.task_runner import run_task, _get_default_cookie, _get_webhook, _get_channel_config


@pytest.fixture
def db_engine():
    engine = get_engine(":memory:")
    init_db(engine)
    return engine


def test_get_default_cookie_returns_default(db_engine):
    with Session(db_engine) as s:
        s.add(CookieAccount(name="A", cookie="cookie_a", is_default=False))
        s.add(CookieAccount(name="B", cookie="cookie_b", is_default=True))
        s.commit()
    result = _get_default_cookie(db_engine)
    assert result == "cookie_b"


def test_get_default_cookie_fallback_to_first(db_engine):
    with Session(db_engine) as s:
        s.add(CookieAccount(name="A", cookie="cookie_a", is_default=False))
        s.commit()
    result = _get_default_cookie(db_engine)
    assert result == "cookie_a"


def test_get_default_cookie_empty(db_engine):
    result = _get_default_cookie(db_engine)
    assert result == ""


def test_get_webhook_uses_config_feishu_webhook(db_engine):
    result = _get_webhook(None, "https://direct.webhook", db_engine)
    assert result == "https://direct.webhook"


def test_get_webhook_uses_channel_by_id(db_engine):
    with Session(db_engine) as s:
        ch = NotifyChannel(name="ch", webhook_url="https://channel.hook")
        s.add(ch)
        s.commit()
        s.refresh(ch)
        ch_id = ch.id
    result = _get_webhook(ch_id, "", db_engine)
    assert result == "https://channel.hook"


def test_get_webhook_uses_default_channel(db_engine):
    with Session(db_engine) as s:
        s.add(NotifyChannel(name="default_ch", webhook_url="https://default.hook", is_default=True))
        s.commit()
    result = _get_webhook(None, "", db_engine)
    assert result == "https://default.hook"


def test_get_webhook_returns_empty_when_none(db_engine):
    result = _get_webhook(None, "", db_engine)
    assert result == ""


def test_get_channel_config_by_id(db_engine):
    with Session(db_engine) as s:
        ch = NotifyChannel(name="bot_ch", app_id="cli_abc", app_secret="sec", chat_id="oc_123")
        s.add(ch)
        s.commit()
        s.refresh(ch)
        ch_id = ch.id
    result = _get_channel_config(ch_id, "", db_engine)
    assert result is not None
    assert result["app_id"] == "cli_abc"
    assert result["chat_id"] == "oc_123"


def test_get_channel_config_default(db_engine):
    with Session(db_engine) as s:
        s.add(NotifyChannel(name="default_bot", app_id="cli_def", app_secret="sec2", chat_id="oc_456", is_default=True))
        s.commit()
    result = _get_channel_config(None, "", db_engine)
    assert result is not None
    assert result["app_id"] == "cli_def"


def test_get_channel_config_returns_none_when_empty(db_engine):
    result = _get_channel_config(None, "", db_engine)
    assert result is None


@pytest.mark.asyncio
async def test_run_task_uses_cookie_account(db_engine, tmp_path):
    with Session(db_engine) as s:
        s.add(CookieAccount(name="main", cookie="real_cookie", is_default=True))
        config = SearchConfig(name="test", query="kw", search_type="search", limit=2)
        s.add(config)
        s.commit()
        s.refresh(config)
        config_id = config.id

    with patch("backend.task_runner.DouyinClient") as MockClient, \
         patch("backend.task_runner.DouyinSearcher") as MockSearcher, \
         patch("backend.task_runner.Downloader") as MockDownloader, \
         patch("backend.task_runner.FeishuNotifier") as MockNotifier, \
         patch("backend.task_runner.write_log_entry") as MockLog, \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)):

        mock_searcher = AsyncMock()
        mock_searcher.search_keyword.return_value = [
            {"aweme_id": "1", "media_type": "video", "desc": "d", "author": "a",
             "video_url": "http://x.com/v.mp4", "image_urls": []}
        ]
        MockSearcher.return_value = mock_searcher

        mock_dl = AsyncMock()
        mock_dl.download.return_value = [str(tmp_path / "1.mp4")]
        MockDownloader.return_value = mock_dl

        MockNotifier.return_value = AsyncMock()
        MockNotifier.return_value.send_media_items.return_value = 0

        task_id = await run_task(config_id=config_id, engine=db_engine)

    # 验证 DouyinClient 用了正确的 cookie
    MockClient.assert_called_once_with(cookie="real_cookie")
    # 验证日志被写入
    assert MockLog.call_count == 1
    log_entry = MockLog.call_args[0][0]
    assert log_entry["aweme_id"] == "1"
    assert log_entry["downloaded"] is True

    with Session(db_engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.status == "done"
        assert task.downloaded == 1
