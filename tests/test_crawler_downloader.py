import pytest
from unittest.mock import AsyncMock, patch
from backend.crawler.downloader import Downloader
from backend.crawler.client import DouyinClient


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def downloader(tmp_dir):
    client = DouyinClient(cookie="test=1")
    return Downloader(client=client, base_dir=tmp_dir)


@pytest.mark.asyncio
async def test_download_video_creates_file(downloader, tmp_dir):
    item = {
        "aweme_id": "abc123",
        "media_type": "video",
        "video_url": "https://example.com/video.mp4",
        "image_urls": [],
        "desc": "test video",
    }
    with patch.object(downloader.client, "download_file", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = None
        paths = await downloader.download(item)
    assert len(paths) == 1
    assert "abc123" in paths[0]
    assert paths[0].endswith(".mp4")


@pytest.mark.asyncio
async def test_download_images_creates_files(downloader, tmp_dir):
    item = {
        "aweme_id": "img456",
        "media_type": "image",
        "video_url": None,
        "image_urls": [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
        ],
        "desc": "test images",
    }
    with patch.object(downloader.client, "download_file", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = None
        paths = await downloader.download(item)
    assert len(paths) == 2
    assert all("img456" in p for p in paths)
