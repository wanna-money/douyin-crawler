import asyncio
from backend.crawler.client import DouyinClient

_SEARCH_URL = "https://www.douyin.com/aweme/v1/web/search/item/"
_HASHTAG_URL = "https://www.douyin.com/aweme/v1/web/challenge/aweme/"


class DouyinSearcher:
    def __init__(self, client: DouyinClient):
        self.client = client

    def _parse_aweme(self, aweme: dict) -> dict | None:
        aweme_id = aweme.get("aweme_id", "")
        if not aweme_id:
            return None
        images = aweme.get("images")
        if images:
            image_urls = [img["url_list"][0] for img in images if img.get("url_list")]
            return {
                "aweme_id": aweme_id,
                "desc": aweme.get("desc", ""),
                "author": aweme.get("author", {}).get("nickname", ""),
                "media_type": "image",
                "image_urls": image_urls,
                "video_url": None,
                "cover_url": None,
            }
        video = aweme.get("video")
        if video:
            url_list = video.get("play_addr", {}).get("url_list", [])
            cover_list = video.get("cover", {}).get("url_list", [])
            return {
                "aweme_id": aweme_id,
                "desc": aweme.get("desc", ""),
                "author": aweme.get("author", {}).get("nickname", ""),
                "media_type": "video",
                "image_urls": [],
                "video_url": url_list[0] if url_list else None,
                "cover_url": cover_list[0] if cover_list else None,
            }
        return None

    async def search_keyword(
        self,
        keyword: str,
        limit: int = 50,
        sort_type: int = 0,
        publish_time: int = 0,
        content_type: int = 0,
        filter_duration: str = "",
    ) -> list[dict]:
        results = []
        cursor = 0
        while len(results) < limit:
            params = {
                "keyword": keyword,
                "search_channel": "aweme_general",
                "sort_type": sort_type,
                "publish_time": publish_time,
                "filter_duration": filter_duration,
                "content_type": content_type,
                "cursor": cursor,
                "count": min(20, limit - len(results)),
            }
            data = await self.client.get(_SEARCH_URL, params)
            if not isinstance(data, dict):
                break
            inner = data.get("data") or {}
            if not isinstance(inner, dict):
                break
            items = inner.get("data") or []
            for item in items:
                aweme = item.get("aweme_info") or item
                parsed = self._parse_aweme(aweme)
                if parsed:
                    results.append(parsed)
            if not inner.get("has_more") or not items:
                break
            cursor = inner.get("cursor", cursor + 20)
            await asyncio.sleep(1)
        return results[:limit]

    async def search_hashtag(self, ch_id: str, limit: int = 50) -> list[dict]:
        results = []
        cursor = 0
        while len(results) < limit:
            params = {"ch_id": ch_id, "cursor": cursor, "count": min(20, limit - len(results))}
            data = await self.client.get(_HASHTAG_URL, params)
            if not isinstance(data, dict):
                break
            aweme_list = data.get("aweme_list") or []
            for aweme in aweme_list:
                parsed = self._parse_aweme(aweme)
                if parsed:
                    results.append(parsed)
            if not data.get("has_more") or not aweme_list:
                break
            cursor = data.get("cursor", cursor + 20)
            await asyncio.sleep(1)
        return results[:limit]
