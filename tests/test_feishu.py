import pytest
from unittest.mock import AsyncMock, patch, MagicMock, mock_open
from backend.notify.feishu import FeishuBotNotifier, FeishuNotifier, get_tenant_token, send_message, _build_card


@pytest.mark.asyncio
async def test_get_tenant_token_fetches_and_caches():
    from backend.notify import feishu as feishu_mod
    feishu_mod._token_cache.clear()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "code": 0,
        "tenant_access_token": "test_token_123",
        "expire": 7200,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        token = await get_tenant_token("app_id_1", "secret_1")

    assert token == "test_token_123"
    assert "app_id_1" in feishu_mod._token_cache
    feishu_mod._token_cache.clear()


@pytest.mark.asyncio
async def test_get_tenant_token_uses_cache():
    import time
    from backend.notify import feishu as feishu_mod
    feishu_mod._token_cache["cached_app"] = ("cached_token", time.time() + 3600)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        token = await get_tenant_token("cached_app", "any_secret")

    mock_post.assert_not_called()
    assert token == "cached_token"
    feishu_mod._token_cache.clear()


@pytest.mark.asyncio
async def test_get_tenant_token_raises_on_error():
    from backend.notify import feishu as feishu_mod
    feishu_mod._token_cache.clear()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": 99991663, "msg": "app ticket invalid"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="获取飞书 token 失败"):
            await get_tenant_token("bad_app", "bad_secret")
    feishu_mod._token_cache.clear()


@pytest.mark.asyncio
async def test_send_message_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": 0}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await send_message("token123", "oc_chat1", "text", '{"text":"hello"}')

    assert result is True


@pytest.mark.asyncio
async def test_send_message_raises_on_api_error():
    """API 返回非 0 code 时应抛出 RuntimeError"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": 9999, "msg": "error"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="发送消息失败"):
            await send_message("token", "oc_chat", "text", '{"text":"hi"}')


def test_build_card_structure():
    items = [
        {"aweme_id": "1", "desc": "美食视频", "author": "小明", "media_type": "video", "file_paths": ["/tmp/v1.mp4"]},
        {"aweme_id": "2", "desc": "美图", "author": "小红", "media_type": "image", "file_paths": ["/tmp/img.jpg"]},
    ]
    card = _build_card(items, "美食探店", {})
    assert card["schema"] == "2.0"
    assert "header" in card
    assert card["header"]["template"] == "indigo"
    assert "body" in card
    assert len(card["body"]["elements"]) > 0


def test_build_card_truncates_at_10():
    items = [
        {"aweme_id": str(i), "desc": f"desc{i}", "author": f"a{i}", "media_type": "video", "file_paths": []}
        for i in range(15)
    ]
    card = _build_card(items, "big_config", {})
    # Should have a "还有 5 条" note
    last = card["body"]["elements"][-1]
    assert last["tag"] == "note"
    assert "5" in last["elements"][0]["content"]


@pytest.mark.asyncio
async def test_feishu_bot_notifier_send_media_items():
    notifier = FeishuBotNotifier(app_id="cli_abc", app_secret="secret", chat_id="oc_123")
    items = [
        {"aweme_id": "1", "desc": "视频1", "media_type": "video", "file_paths": ["/tmp/1.mp4"]},
        {"aweme_id": "2", "desc": "图文1", "media_type": "image", "file_paths": ["/tmp/2.jpg"]},
    ]

    with patch("backend.notify.feishu.get_tenant_token", new_callable=AsyncMock, return_value="tok") as mock_token, \
         patch("backend.notify.feishu.upload_image", new_callable=AsyncMock, return_value=None) as mock_upload, \
         patch("backend.notify.feishu.send_message", new_callable=AsyncMock, return_value=True) as mock_send:
        sent = await notifier.send_media_items(items, config_name="测试配置")

    assert sent == 2
    mock_send.assert_called_once()
    # Check card message_type is interactive
    call_args = mock_send.call_args
    assert call_args[0][2] == "interactive"


@pytest.mark.asyncio
async def test_feishu_bot_notifier_returns_zero_on_send_failure():
    notifier = FeishuBotNotifier(app_id="cli_abc", app_secret="secret", chat_id="oc_123")
    items = [{"aweme_id": "1", "desc": "test", "media_type": "video", "file_paths": []}]

    with patch("backend.notify.feishu.get_tenant_token", new_callable=AsyncMock, return_value="tok"), \
         patch("backend.notify.feishu.upload_image", new_callable=AsyncMock, return_value=None), \
         patch("backend.notify.feishu.send_message", new_callable=AsyncMock, return_value=False):
        sent = await notifier.send_media_items(items, config_name="test")

    assert sent == 0


@pytest.mark.asyncio
async def test_feishu_bot_notifier_returns_zero_for_empty():
    notifier = FeishuBotNotifier(app_id="cli_abc", app_secret="secret", chat_id="oc_123")
    sent = await notifier.send_media_items([], config_name="test")
    assert sent == 0


def test_feishu_notifier_is_alias():
    """FeishuNotifier should be a subclass of FeishuBotNotifier for backward compat"""
    assert issubclass(FeishuNotifier, FeishuBotNotifier)
    n = FeishuNotifier(app_id="a", app_secret="b", chat_id="c")
    assert n.app_id == "a"
    assert n.chat_id == "c"
