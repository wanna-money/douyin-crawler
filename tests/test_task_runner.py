import pytest
from unittest.mock import AsyncMock, patch
from sqlmodel import Session
from backend.database import get_engine, init_db
from backend.models import SearchConfig, TaskRecord
from backend.task_runner import run_task


@pytest.fixture
def db_engine():
    engine = get_engine(":memory:")
    init_db(engine)
    return engine


@pytest.mark.asyncio
async def test_run_task_creates_task_record(db_engine):
    with Session(db_engine) as session:
        config = SearchConfig(
            name="test",
            query="美食",
            search_type="search",
            cron="0 9 * * *",
            feishu_webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test",
            limit=5,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        config_id = config.id

    with patch("backend.task_runner.DouyinClient") as MockClient, \
         patch("backend.task_runner.DouyinSearcher") as MockSearcher, \
         patch("backend.task_runner.Downloader") as MockDownloader, \
         patch("backend.task_runner.FeishuNotifier") as MockNotifier, \
         patch("backend.task_runner.get_setting", return_value="cookie=test"):

        mock_searcher_inst = AsyncMock()
        mock_searcher_inst.search_keyword.return_value = [
            {"aweme_id": "1", "media_type": "video", "desc": "test", "author": "a",
             "video_url": "http://x.com/v.mp4", "image_urls": []}
        ]
        MockSearcher.return_value = mock_searcher_inst

        mock_dl_inst = AsyncMock()
        mock_dl_inst.download.return_value = ["/tmp/1.mp4"]
        MockDownloader.return_value = mock_dl_inst

        mock_notifier_inst = AsyncMock()
        mock_notifier_inst.send_media_items.return_value = 1
        MockNotifier.return_value = mock_notifier_inst

        task_id = await run_task(config_id=config_id, engine=db_engine)

    with Session(db_engine) as session:
        task = session.get(TaskRecord, task_id)
        assert task is not None
        assert task.status == "done"
        assert task.downloaded >= 0
