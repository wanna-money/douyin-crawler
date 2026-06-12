# tests/test_task_runner_v3.py
"""
核心流程测试：覆盖 task_runner.run_task 的完整执行路径
- SeenRecord 去重
- LLM 过滤开关
- 下载失败继续执行
- 飞书发送
- 任务异常时标记 failed
"""
import json
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
    mock_searcher.search_keyword.return_value = (search_items, None)
    mock_searcher.search_user_profile.return_value = (search_items, None)

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
    """SeenRecord 去重：第一次执行后，第二次搜索器返回空（已被去重），不再下载"""
    searcher = AsyncMock()
    # 第一次返回 2 条，第二次 Playwright 因 exclude_ids 已过滤，返回空
    searcher.search_keyword.side_effect = [
        (_mock_items(["dup1", "dup2"]), None),
        ([], None),
    ]
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/x.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        # 第一次执行
        await run_task(config_id=config, engine=engine)
        first_download_count = downloader.download.call_count

        # 第二次执行：搜索器返回空，不应再下载
        await run_task(config_id=config, engine=engine)
        second_download_count = downloader.download.call_count

    assert second_download_count == first_download_count

    # SeenRecord 表中有 2 条
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
    searcher.search_keyword.return_value = (_mock_items(["shared_id"]), None)
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
async def test_run_task_seen_record_not_written_if_download_fails(engine, config, cookie, tmp_path):
    """下载失败时 SeenRecord 不写入（下次可以重试）"""
    searcher = AsyncMock()
    searcher.search_keyword.return_value = (_mock_items(["fail_id"]), None)
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
        assert len(seen) == 0  # 下载失败不写入 SeenRecord，下次可以重试


@pytest.mark.asyncio
async def test_run_task_partial_download_failure(engine, config, cookie, tmp_path):
    """部分下载失败时，成功的继续处理，失败的跳过"""
    items = _mock_items(["ok1", "fail1", "ok2"])
    searcher = AsyncMock()
    searcher.search_keyword.return_value = (items, None)

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
    searcher.search_keyword.return_value = (items, None)
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
    searcher.search_keyword.return_value = (_mock_items(), None)
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
    searcher.search_keyword.return_value = (items, None)
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
    searcher.search_keyword.return_value = (_mock_items(["send1"]), None)
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
    searcher.search_keyword.return_value = (_mock_items(), None)
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


# ── user 搜索路径 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_user_search_type(engine, tmp_path):
    """search_type=user 时调用 search_user_profile，而非 search_keyword"""
    with Session(engine) as s:
        users = [{"sec_uid": "uid_abc", "limit": 3, "nickname": "博主A"}]
        cfg = SearchConfig(
            name="用户测试",
            query=json.dumps(users),
            search_type="user",
            limit=10,
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_user_profile.return_value = (_mock_items(["u1", "u2"]), None)
    downloader = AsyncMock()
    downloader.download.return_value = ["/tmp/u1.mp4"]
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        task_id = await run_task(config_id=config_id, engine=engine)

    searcher.search_user_profile.assert_called_once_with(
        sec_uid="uid_abc", limit=3, tab="post", exclude_ids=set()
    )
    searcher.search_keyword.assert_not_called()

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.status == "done"
        assert task.total == 2


@pytest.mark.asyncio
async def test_run_task_user_multi_accounts(engine, tmp_path):
    """user 模式下多个账号分别搜索，结果合并"""
    with Session(engine) as s:
        users = [
            {"sec_uid": "uid_a", "limit": 2, "nickname": "A"},
            {"sec_uid": "uid_b", "limit": 3, "nickname": "B"},
        ]
        cfg = SearchConfig(
            name="多用户",
            query=json.dumps(users),
            search_type="user",
            limit=10,
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_user_profile.side_effect = [
        (_mock_items(["a1", "a2"]), None),
        (_mock_items(["b1", "b2", "b3"]), None),
    ]
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

    assert searcher.search_user_profile.call_count == 2
    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        assert task.total == 5  # a1+a2+b1+b2+b3


@pytest.mark.asyncio
async def test_run_task_user_dedup_across_accounts(engine, tmp_path):
    """user 模式下，第二个账号不重复推送第一个账号已抓取的内容"""
    with Session(engine) as s:
        users = [
            {"sec_uid": "uid_a", "limit": 5, "nickname": "A"},
            {"sec_uid": "uid_b", "limit": 5, "nickname": "B"},
        ]
        cfg = SearchConfig(
            name="去重测试",
            query=json.dumps(users),
            search_type="user",
            limit=10,
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    # uid_b 返回的 shared_id 已被 uid_a 返回过
    searcher = AsyncMock()
    searcher.search_user_profile.side_effect = [
        (_mock_items(["shared", "a_only"]), None),
        (_mock_items(["shared", "b_only"]), None),  # shared 会被排除
    ]
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

    # shared 在第二个账号时被 exclude_ids 过滤（任务内去重）
    # 第二次调用的 exclude_ids 应包含第一批结果
    second_call_kwargs = searcher.search_user_profile.call_args_list[1][1]
    assert "shared" in second_call_kwargs["exclude_ids"]
    assert "a_only" in second_call_kwargs["exclude_ids"]

    with Session(engine) as s:
        task = s.get(TaskRecord, task_id)
        # mock 返回了 shared+b_only，真实 Playwright 会过滤 shared；
        # 这里验证 exclude_ids 正确传递，total 为 mock 的实际返回数
        assert task.total == 4


@pytest.mark.asyncio
async def test_run_task_user_plain_sec_uid_string(engine, tmp_path):
    """query 直接填 sec_uid 字符串（非 JSON）时能兼容处理"""
    with Session(engine) as s:
        cfg = SearchConfig(
            name="兼容测试",
            query="MS4wLjABAAAAtest",
            search_type="user",
            limit=5,
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_user_profile.return_value = (_mock_items(["x1"]), None)
    downloader = AsyncMock()
    downloader.download.return_value = []
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=config_id, engine=engine)

    searcher.search_user_profile.assert_called_once_with(
        sec_uid="MS4wLjABAAAAtest", limit=5, tab="post", exclude_ids=set()
    )


@pytest.mark.asyncio
async def test_run_task_user_favorite_tab(engine, tmp_path):
    """tab=favorite 时 search_user_profile 以 tab='favorite' 调用"""
    with Session(engine) as s:
        users = [{"sec_uid": "uid_fav", "limit": 5, "nickname": "我", "tab": "favorite"}]
        cfg = SearchConfig(
            name="收藏测试",
            query=json.dumps(users),
            search_type="user",
            limit=10,
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        config_id = cfg.id

    searcher = AsyncMock()
    searcher.search_user_profile.return_value = (_mock_items(["f1", "f2"]), None)
    downloader = AsyncMock()
    downloader.download.return_value = []
    notifier = AsyncMock()
    notifier.send_media_items.return_value = 0

    with patch("backend.task_runner.DouyinSearcher", return_value=searcher), \
         patch("backend.task_runner.Downloader", return_value=downloader), \
         patch("backend.task_runner.FeishuNotifier", return_value=notifier), \
         patch("backend.task_runner.get_setting", return_value=str(tmp_path)), \
         patch("backend.task_runner.write_log_entry"):

        await run_task(config_id=config_id, engine=engine)

    searcher.search_user_profile.assert_called_once_with(
        sec_uid="uid_fav", limit=5, tab="favorite", exclude_ids=set()
    )


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
