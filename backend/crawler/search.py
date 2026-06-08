import asyncio
import concurrent.futures
from urllib.parse import quote

from backend.crawler.client import DouyinClient

_HASHTAG_URL = "https://www.douyin.com/aweme/v1/web/challenge/aweme/"

_NIL_REASONS = {
    "invalid_app": "请求参数不合法（缺少设备/浏览器参数）",
    "verify_check": "需要人机验证（Cookie 已失效，请重新获取）",
    "no_result": "该关键词暂无搜索结果",
    "service_empty": "服务端拒绝返回结果（Cookie 已失效或被风控，请重新获取 Cookie）",
    "search_service_resp_nil": "服务端拒绝返回结果（Cookie 已失效或被风控，请重新获取 Cookie）",
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
    api_hit_count = 0  # 记录搜索 API 被拦截的次数

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
        nonlocal has_more, nil_reason, api_hit_count

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
                nonlocal has_more, nil_reason, api_hit_count
                url = route.request.url
                if "general/search/single" not in url and "general/search/stream" not in url:
                    await route.continue_()
                    return
                api_hit_count += 1
                try:
                    resp = await route.fetch()
                    raw = await resp.body()
                    # stream 接口返回 chunked 格式（十六进制长度\r\n数据\r\n），需提取 JSON 部分
                    try:
                        body = await resp.json()
                    except Exception:
                        text = raw.decode("utf-8", errors="ignore")
                        # 跳过开头的 chunked 长度行，找到第一个 { 开始的 JSON
                        idx = text.find("{")
                        if idx != -1:
                            import json as _json
                            body = _json.loads(text[idx:])
                        else:
                            body = {}
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
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).warning("拦截搜索 API 异常: %s", e)
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", on_route)

            # 访问主页预热，再跳搜索页
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            import logging as _logging
            _log = _logging.getLogger(__name__)
            _log.info("[搜索诊断] 主页加载完成，当前 URL: %s", page.url)
            await page.goto(
                f"https://www.douyin.com/search/{quote(keyword)}?type=general",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            # 等待第一个搜索 API 请求被触发，最多等 15 秒
            for _ in range(30):
                await asyncio.sleep(0.5)
                if api_hit_count > 0 or nil_reason:
                    break
            _log.info("[搜索诊断] 搜索页加载完成，当前 URL: %s，api_hit_count=%d，new_results=%d", page.url, api_hit_count, len(new_results))

            # 翻页：通过 JS 滚动到底部触发加载更多，限制最多 5 次避免触发风控
            max_pages = min((limit * 5 // 10) + 5, 5)
            consecutive_empty = 0
            for _ in range(max_pages):
                if len(new_results) >= limit or not has_more:
                    break
                prev_count = len(new_results)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                # 等待新内容加载，最多 6 秒
                for _ in range(12):
                    await asyncio.sleep(0.5)
                    if len(new_results) > prev_count:
                        break
                if len(new_results) == prev_count:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                else:
                    consecutive_empty = 0

            await browser.close()

        if api_hit_count == 0 and not nil_reason:
            nil_reason = "搜索 API 未被触发（Cookie 已失效或页面加载失败，请重新获取 Cookie）"

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
