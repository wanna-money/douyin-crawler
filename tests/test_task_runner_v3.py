# tests/test_task_runner_v3.py
"""
核心流程测试：覆盖 task_runner.run_task 的完整执行路径
- SeenRecord 去重
- LLM 过滤开关
- 下载失败继续执行
- 飞书发送
- 任务异常时标记 failed
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlmodel import Session, select
from backend.database import get_engine, init_db
from backend.models import (
    SearchConfig, TaskRecord, SeenRecord, DownloadRecord,
    CookieAccount, NotifyChannel, LLMConfig,
)
from backend.task_runner import run_task, _get_default_llm


# ── fixtures ──────────────────────────────────────────────

@pytest.fixture
def engine():
    e = get_engine(":memory:")
    init_db(e)
    return e


@pytest.fixture
def config(engine):
    with Session(engine) as s:
        cfg = SearchConfig(name="测试配置", query="美食", search_type="search", limit=5)
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        return cfg.id


@pytest.fixture
def cookie(engine):
    with Session(engine) as s:
        s.add(CookieAccount(name="主号", cookie="sid=test", is_default=True))
        s.commit()


def _mock_items(ids=("a1", "a2")):
    return [
        {
            "aweme_id": aid,
            "media_type": "video",
            "desc": f"desc_{aid}",
            "author": "作者",
            "video_url": f"https://example.com/{aid}.mp4",
            "cover_url": f"https://example.com/{aid}_cover.jpg",
            "image_urls": [],
        }
        for aid in ids
    ]


def _patch_runner(search_items=None, download_paths=None, send_count=1):
    """返回 patch 上下文的公共 mock 集合"""
    search_items = search_items or _mock_items()
    download_paths = download_paths or ["/tmp/a1.mp4"]

    mock_searcher = AsyncMock()
    mock_searcher.search_keyword.return_value = search_items
    mock_searcher.search_hashtag.return_value = search_items

    mock_downloader = AsyncMock()
    mock_downloader.download.return_value = download_paths

    mock_notifier = AsyncMock()
    mock_notifier.send_media_items.return_value = send_count

    return mock_searcher, mock_downloader, mock_notifier


# ── 基础流程 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_success(engine, config, cookie, tmp_path):
    """正常完成任务：搜索→去重→下载→日志→状态 done"""
    searcher, downloader, notifier = _patch_runner()

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config, engine=engine)

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.status == "done"
        assert task.total == 2
        assert task.downloaded == 2


@pytest.mark.asyncio
async def test_run_task_dedup_via_seen_record(engine, config, cookie, tmp_path):
    """SeenRecord 去重：第一次执行后，第二次相同内容不再下载"""
    searcher, downloader, notifier = _patch_runner(search_items=_mock_items(["dup1", "dup2"]))

    patches = dict(
        DouyinSearcher=searcher,
        Downloader=downloader,
        FeishuNotifier=notifier,
    )

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        # 第一次执行
        await run_task(config_id=config, engine=engine)
        first_download_count = downloader.download.call_count

        # 第二次执行：相同 aweme_id，SeenRecord 已有，不应再下载
        await run_task(config_id=config, engine=engine)
        second_download_count = downloader.download.call_count

    # 第二次不新增下载
    assert second_download_count == first_download_count

    # SeenRecord 表中有且仅有 2 条（不重复写）
    with Session(engine) as s:
        seen = s.exec(select(SeenRecord).where(SeenRecord.config_id == config)).all()
        assert len(seen) == 2


@pytest.mark.asyncio
async def test_run_task_dedup_is_per_config(engine, tmp_path):
    """不同 config_id 的 SeenRecord 互不干扰"""
    with Session(engine) as s:
        c1 = SearchConfig(name="配置1", query="美食", search_type="search", limit=5)
        c2 = SearchConfig(name="配置2", query="旅游", search_type="search", limit=5)
        s.add(c1); s.add(c2)
        s.commit()
        s.refresh(c1); s.refresh(c2)
        c1_id, c2_id = c1.id, c2.id

    searcher = AsyncMock()
    searcher.search_keyword.return_value = _mock_items(["shared_id"])
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/x.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=c1_id, engine=engine)
        initial_calls = downloader.download.call_count

        # 相同 aweme_id 但不同 config，不应被 c1 的 SeenRecord 去重
        await run_task(config_id=c2_id, engine=engine)

    assert downloader.download.call_count == initial_calls + 1


@pytest.mark.asyncio
async def test_run_task_seen_record_written_even_if_download_fails(engine, config, cookie, tmp_path):
    """下载失败时 SeenRecord 也应写入，防止下次重复尝试失败的内容"""
    searcher = AsyncMock()
    searcher.search_keyword.return_value = _mock_items(["fail_id"])
    downloader = AsyncMock()
    downloader.download.side_effect = Exception("下载超时")
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config, engine=engine)

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.status == "done"   # 下载失败不影响任务状态
        assert task.downloaded == 0

        seen = s.exec(select(SeenRecord).where(SeenRecord.config_id == config)).all()
        assert any(r.aweme_id == "fail_id" for r in seen)  # 仍写入 SeenRecord


@pytest.mark.asyncio
async def test_run_task_partial_download_failure(engine, config, cookie, tmp_path):
    """部分下载失败时，成功的继续处理，失败的跳过"""
    items = _mock_items(["ok1", "fail1", "ok2"])
    searcher = AsyncMock()
    searcher.search_keyword.return_value = items

    call_count = [0]
    async def download_side_effect(item):
        call_count[0] += 1
        if item["aweme_id"] == "fail1":
            raise Exception("网络错误")
        return [f"/tmp/{item['aweme_id']}.mp4"]

    downloader = AsyncMock()
    downloader.download.side_effect = download_side_effect
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config, engine=engine)

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.status == "done"
        assert task.total == 3
        assert task.downloaded == 2  # ok1 + ok2


# ── LLM 过滤 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_llm_filter_skips_irrelevant(engine, tmp_path):
    """LLM 过滤开启时，不相关内容被跳过"""
    with Session(engine) as s:
        cfg = SearchConfig(name="LLM测试", query="美食", search_type="search",
                           limit=5, llm_filter_enabled=True)
        llm = LLMConfig(name="test", base_url="https://api.x.com/v1",
                        api_key="k", model="m", is_default=True)
        s.add(cfg); s.add(llm)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    items = _mock_items(["rel", "irrel"])
    searcher = AsyncMock()
    searcher.search_keyword.return_value = items
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/rel.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    # LLM: "rel" 相关，"irrel" 不相关
    async def fake_check(keyword, desc, author, base_url, api_key, model,
                         prompt_template, cover_url="", timeout=20):
        return desc != "desc_irrel"

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.check_relevance", side_effect=fake_check), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config_id, engine=engine)

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.downloaded == 1  # 只下载了相关的 "rel"


@pytest.mark.asyncio
async def test_run_task_llm_filter_disabled_skips_check(engine, config, cookie, tmp_path):
    """LLM 过滤关闭时不调用 check_relevance"""
    searcher = AsyncMock()
    searcher.search_keyword.return_value = _mock_items()
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/x.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    mock_check = AsyncMock(return_value=True)

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.check_relevance", mock_check), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=config, engine=engine)

    mock_check.assert_not_called()


@pytest.mark.asyncio
async def test_run_task_llm_no_config_skips_filter(engine, tmp_path):
    """LLM 过滤开启但未配置模型时，跳过过滤（放行所有）"""
    with Session(engine) as s:
        cfg = SearchConfig(name="无LLM", query="美食", search_type="search",
                           limit=5, llm_filter_enabled=True)  # 开启但无 LLMConfig
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    items = _mock_items(["x1", "x2"])
    searcher = AsyncMock()
    searcher.search_keyword.return_value = items
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/x.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config_id, engine=engine)

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.downloaded == 2  # 无 LLM 配置，全部放行


# ── 飞书发送 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_sends_to_feishu_when_channel_configured(engine, tmp_path):
    """有通知渠道配置时，下载后发送飞书"""
    with Session(engine) as s:
        ch = NotifyChannel(name="测试群", app_id="cli_test",
                           app_secret="secret", chat_id="oc_test", is_default=True)
        cfg = SearchConfig(name="发送测试", query="美食", search_type="search", limit=5)
        s.add(ch); s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_keyword.return_value = _mock_items(["send1"])
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/send1.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 1

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config_id, engine=engine)

    notifier.send_media_items.assert_called_once()
    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.sent == 1


@pytest.mark.asyncio
async def test_run_task_skips_feishu_when_no_channel(engine, config, cookie, tmp_path):
    """没有通知渠道时不调用飞书发送"""
    searcher = AsyncMock()
    searcher.search_keyword.return_value = _mock_items()
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/x.mp4"]
    mock_notifier_cls = MagicMock()

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", mock_notifier_cls), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=config, engine=engine)

    mock_notifier_cls.assert_not_called()


# ── 错误处理 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_marks_failed_on_search_error(engine, config, cookie, tmp_path):
    """搜索异常时任务状态标记为 failed"""
    searcher = AsyncMock()
    searcher.search_keyword.side_effect = Exception("抖音接口超时")
    downloader = AsyncMock()

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        with pytest.raises(Exception, match="抖音接口超时"):
            task_id = await run_task(config_id=config, engine=engine)

    with Session(engine) as s:
        tasks = s.exec(select(TaskRecord).where(TaskRecord.config_id == config)).all()
        assert any(t.status == "failed" for t in tasks)
        assert any("抖音接口超时" in (t.error or "") for t in tasks)


@pytest.mark.asyncio
async def test_run_task_raises_for_missing_config(engine):
    """config_id 不存在时直接抛出 ValueError"""
    with pytest.raises(ValueError, match="not found"):
        await run_task(config_id=9999, engine=engine)


# ── hashtag 搜索路径 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_hashtag_search_type(engine, tmp_path):
    """search_type=hashtag 时调用 search_hashtag"""
    with Session(engine) as s:
        cfg = SearchConfig(name="话题测试", query="ch_123456",
                           search_type="hashtag", limit=5)
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_hashtag.return_value = _mock_items(["ht1"])
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/ht1.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=config_id, engine=engine)

    searcher.search_hashtag.assert_called_once_with("ch_123456", limit=5)
    searcher.search_keyword.assert_not_called()


# ── _get_default_llm ──────────────────────────────────────

def test_get_default_llm_returns_default(engine):
    with Session(engine) as s:
        s.add(LLMConfig(name="A", base_url="https://a.com/v1", model="m1", is_default=False))
        s.add(LLMConfig(name="B", base_url="https://b.com/v1", model="m2", is_default=True))
        s.commit()
    result = _get_default_llm(engine)
    assert result["model"] == "m2"


def test_get_default_llm_fallback_to_first(engine):
    with Session(engine) as s:
        s.add(LLMConfig(name="only", base_url="https://c.com/v1", model="m3", is_default=False))
        s.commit()
    result = _get_default_llm(engine)
    assert result["model"] == "m3"


def test_get_default_llm_returns_none_when_empty(engine):
    assert _get_default_llm(engine) is None
