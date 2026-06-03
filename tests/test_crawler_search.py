import pytest
from unittest.mock import AsyncMock, patch
from backend.crawler.search import DouyinSearcher
from backend.crawler.client import DouyinClient


@pytest.fixture
def searcher():
    client = DouyinClient(cookie="test=1")
    return DouyinSearcher(client)


@pytest.mark.asyncio
async def test_search_keyword_returns_items(searcher):
    fake_response = {
        "status_code": 0,
        "data": {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "123",
                        "desc": "美食探店",
                        "aweme_type": 0,
                        "video": {
                            "play_addr": {"url_list": ["https://example.com/video.mp4"]},
                            "cover": {"url_list": ["https://example.com/cover.jpg"]},
                        },
                        "images": None,
                        "author": {"nickname": "测试用户"},
                    }
                }
            ],
            "has_more": 0,
            "cursor": 0,
        },
    }
    with patch.object(searcher.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_response
        items = await searcher.search_keyword("美食", limit=10)
    assert len(items) == 1
    assert items[0]["aweme_id"] == "123"
    assert items[0]["media_type"] == "video"


@pytest.mark.asyncio
async def test_search_returns_image_type(searcher):
    fake_response = {
        "status_code": 0,
        "data": {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "456",
                        "desc": "图文",
                        "aweme_type": 68,
                        "video": None,
                        "images": [
                            {"url_list": ["https://example.com/img1.jpg"]},
                            {"url_list": ["https://example.com/img2.jpg"]},
                        ],
                        "author": {"nickname": "用户2"},
                    }
                }
            ],
            "has_more": 0,
            "cursor": 0,
        },
    }
    with patch.object(searcher.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_response
        items = await searcher.search_keyword("图文", limit=10)
    assert items[0]["media_type"] == "image"
    assert len(items[0]["image_urls"]) == 2
