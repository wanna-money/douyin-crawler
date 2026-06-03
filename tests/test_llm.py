# tests/test_llm.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.llm import check_relevance, build_prompt, _build_vision_messages, _build_text_messages


def test_build_prompt_substitutes_variables():
    template = "关键词：{keyword}\n描述：{desc}\n作者：{author}\n相关："
    result = build_prompt(template, keyword="美食", desc="探店火锅", author="小王")
    assert "美食" in result
    assert "探店火锅" in result
    assert "小王" in result


def test_build_prompt_truncates_long_desc():
    long_desc = "a" * 300
    template = "描述：{desc}"
    result = build_prompt(template, keyword="k", desc=long_desc, author="a")
    assert "a" * 201 not in result  # desc 被截断为 200 字符


def test_build_vision_messages_contains_image_and_text():
    msgs = _build_vision_messages("美食探店", "https://example.com/cover.jpg")
    assert len(msgs) == 1
    content = msgs[0]["content"]
    types = [c["type"] for c in content]
    assert "image_url" in types
    assert "text" in types
    # 图片 URL 正确传入
    img = next(c for c in content if c["type"] == "image_url")
    assert img["image_url"]["url"] == "https://example.com/cover.jpg"
    # 文字包含关键词
    txt = next(c for c in content if c["type"] == "text")
    assert "美食探店" in txt["text"]


def test_build_text_messages_is_plain_string():
    msgs = _build_text_messages("关键词：美食\n相关：")
    assert len(msgs) == 1
    assert isinstance(msgs[0]["content"], str)


@pytest.mark.asyncio
async def test_check_relevance_uses_vision_when_cover_url_provided():
    """有封面图时应发多模态消息"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "是"}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await check_relevance(
            keyword="美食探店",
            desc="探店火锅",
            author="美食达人",
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="qwen-vl-plus",
            prompt_template="关键词：{keyword}\n描述：{desc}\n作者：{author}\n相关：",
            cover_url="https://example.com/cover.jpg",
        )
    assert result is True
    # 验证发送的是多模态消息（content 是 list）
    call_json = mock_post.call_args.kwargs["json"]
    assert isinstance(call_json["messages"][0]["content"], list)


@pytest.mark.asyncio
async def test_check_relevance_uses_text_when_no_cover_url():
    """无封面图时降级为纯文字消息"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "是"}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await check_relevance(
            keyword="美食探店",
            desc="探店火锅",
            author="美食达人",
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4o-mini",
            prompt_template="关键词：{keyword}\n描述：{desc}\n作者：{author}\n相关：",
            cover_url="",
        )
    assert result is True
    # 验证发送的是纯文本消息（content 是 str）
    call_json = mock_post.call_args.kwargs["json"]
    assert isinstance(call_json["messages"][0]["content"], str)


@pytest.mark.asyncio
async def test_check_relevance_returns_true_on_yes():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "是"}}]}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await check_relevance(
            keyword="美食探店", desc="探店北京最好吃的火锅", author="美食达人",
            base_url="https://api.example.com/v1", api_key="test-key",
            model="gpt-4o-mini",
            prompt_template="关键词：{keyword}\n描述：{desc}\n作者：{author}\n相关：",
        )
    assert result is True


@pytest.mark.asyncio
async def test_check_relevance_returns_false_on_no():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "否"}}]}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await check_relevance(
            keyword="美食探店", desc="股市今日大涨", author="财经频道",
            base_url="https://api.example.com/v1", api_key="test-key",
            model="gpt-4o-mini",
            prompt_template="关键词：{keyword}\n描述：{desc}\n作者：{author}\n相关：",
        )
    assert result is False


@pytest.mark.asyncio
async def test_check_relevance_returns_true_on_network_error():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("connection timeout")
        result = await check_relevance(
            keyword="美食", desc="好吃的", author="a",
            base_url="https://api.example.com/v1", api_key="key",
            model="gpt-4o-mini", prompt_template="{keyword}{desc}{author}",
        )
    assert result is True


@pytest.mark.asyncio
async def test_check_relevance_accepts_yes_in_english():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "yes"}}]}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await check_relevance(
            keyword="food", desc="delicious hotpot", author="foodie",
            base_url="https://api.example.com/v1", api_key="key",
            model="gpt-4o-mini", prompt_template="{keyword}{desc}{author}",
        )
    assert result is True
