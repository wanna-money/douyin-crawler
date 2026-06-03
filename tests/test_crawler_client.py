import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.crawler.client import DouyinClient


@pytest.fixture
def client():
    return DouyinClient(cookie="test_cookie=123")


def test_client_headers(client):
    headers = client._build_headers()
    assert headers["Cookie"] == "test_cookie=123"
    assert "User-Agent" in headers
    assert "Referer" in headers


@pytest.mark.asyncio
async def test_get_returns_json_on_success(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"status_code": 0, "data": []}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client.get("https://www.douyin.com/aweme/v1/web/search/item/", params={})
    assert result == {"status_code": 0, "data": []}
