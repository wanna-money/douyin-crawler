import asyncio
import concurrent.futures
from urllib.parse import quote

from backend.crawler.client import DouyinClient

_HASHTAG_URL = "https://www.douyin.com/aweme/v1/web/challenge/aweme/"

_NIL_REASONS = {
    "invalid_app": "请求参数不合法（缺少设备/浏览器参数）",
    "verify_check": "需要人机验证（Cookie 已失效，请重新获取）",
    "no_result": "该关键词暂无搜索结果",
}


async def _playwright_search(
    keyword: str,
    cookie: str,
    limit: int,
    exclude_ids: set[str],
) -> tuple[list[dict], str | None]:
    """
    用 Playwright 在真实浏览器里搜索，拦截 general/search/single 响应直接取数据。
    完全绕过签名问题。
    """
    from playwright.async_api import async_playwright

    new_results: list[dict] = []
    nil_reason: str | None = None
    seen = set(exclude_ids)
    pages_done = asyncio.Event()
    has_more = True
    page_ref = {}   # 用 dict 传递 page 引用（避免闭包问题）

    def _parse_aweme(aweme: dict) -> dict | None:
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

    async def _run():
        nonlocal has_more, nil_reason

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
                )
            )
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, val = part.partition("=")
                    try:
                        await context.add_cookies([{
                            "name": name.strip(), "value": val.strip(),
                            "domain": ".douyin.com", "path": "/",
                        }])
                    except Exception:
                        pass

            page = await context.new_page()
            page_ref["page"] = page

            # 只拦截搜索 API，其他请求（图片/JS/CSS等）直接放行
            async def on_route(route):
                nonlocal has_more, nil_reason
                if "general/search/single" not in route.request.url:
                    await route.continue_()
                    return
                try:
                    resp = await route.fetch()
                    body = await resp.json()
                    for item in (body.get("data") or []):
                        aweme = item.get("aweme_info")
                        if not aweme:
                            continue
                        parsed = _parse_aweme(aweme)
                        if parsed and parsed["aweme_id"] not in seen:
                            seen.add(parsed["aweme_id"])
                            new_results.append(parsed)
                    has_more = bool(body.get("has_more"))
                    nil = body.get("search_nil_info")
                    if nil and not new_results:
                        item_key = nil.get("search_nil_item", "") or nil.get("search_nil_type", "")
                        nil_reason = _NIL_REASONS.get(item_key, f"搜索为空：{nil.get('search_nil_type')}/{nil.get('search_nil_item')}")
                    await route.fulfill(response=resp)
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", on_route)

            # 访问主页预热，再跳搜索页
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            await page.goto(
                f"https://www.douyin.com/search/{quote(keyword)}?type=general",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(5)  # 等第一页加载完

            # 翻页：通过 JS 滚动到底部触发加载更多
            max_pages = (limit // 10) + 3
            for _ in range(max_pages):
                if len(new_results) >= limit or not has_more:
                    break
                # 滚动到底部触发下一页
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)

            await browser.close()

    await _run()
    return new_results[:limit], nil_reason


def _playwright_search_sync(keyword: str, cookie: str, limit: int, exclude_ids: set[str]) -> tuple[list[dict], str | None]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_playwright_search(keyword, cookie, limit, exclude_ids))
    finally:
        loop.close()


class DouyinSearcher:
    def __init__(self, client: DouyinClient):
        self.client = client

    async def search_keyword(
        self,
        keyword: str,
        limit: int = 50,
        sort_type: int = 0,
        publish_time: int = 0,
        content_type: int = 0,
        filter_duration: str = "",
        exclude_ids: set[str] | None = None,
    ) -> tuple[list[dict], str | None]:
        """在独立线程里运行 Playwright 搜索，不阻塞 uvicorn event loop。"""
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(
                pool,
                _playwright_search_sync,
                keyword,
                self.client.cookie,
                limit,
                exclude_ids or set(),
            )
        return result

    async def search_hashtag(self, ch_id: str, limit: int = 50) -> tuple[list[dict], str | None]:
        results = []
        cursor = 0
        nil_reason: str | None = None
        while len(results) < limit:
            params = {"ch_id": ch_id, "cursor": cursor, "count": min(20, limit - len(results))}
            data = await self.client.get(_HASHTAG_URL, params)
            if not isinstance(data, dict):
                nil_reason = f"API 返回非预期格式：{type(data).__name__}"
                break
            aweme_list = data.get("aweme_list") or []
            for aweme in aweme_list:
                parsed = self._parse_aweme(aweme)
                if parsed:
                    results.append(parsed)
            if not aweme_list:
                item_key = ""
                nil = data.get("search_nil_info")
                if nil:
                    item_key = nil.get("search_nil_item", "") or nil.get("search_nil_type", "")
                nil_reason = _NIL_REASONS.get(item_key, "话题下暂无内容")
                break
            if not data.get("has_more"):
                break
            cursor = data.get("cursor", cursor + 20)
            await asyncio.sleep(1)
        return results[:limit], nil_reason

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
