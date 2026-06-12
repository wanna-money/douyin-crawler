import asyncio
import concurrent.futures
import json as _json
import logging
import os
import sys
from urllib.parse import quote

from backend.crawler.client import DouyinClient

_CDP_PORT = int(os.environ.get("CHROME_CDP_PORT", "9222"))

logger = logging.getLogger(__name__)

_NIL_REASONS = {
    "invalid_app": "请求参数不合法（缺少设备/浏览器参数）",
    "verify_check": "需要人机验证（Cookie 已失效，请重新获取）",
    "no_result": "该关键词暂无搜索结果",
    "service_empty": "服务端拒绝返回结果（Cookie 已失效或被风控，请重新获取 Cookie）",
    "search_service_resp_nil": "服务端拒绝返回结果（Cookie 已失效或被风控，请重新获取 Cookie）",
}


def _is_local() -> bool:
    return sys.platform in ("darwin", "win32") or os.environ.get("DISPLAY") is not None


async def _playwright_resolve_uid(douyin_id: str, cookie: str) -> str | None:
    """
    通过抖音号搜索用户，拦截 discover/search 接口，返回第一个匹配用户的 sec_uid。
    抖音号精确匹配时第一条即为目标用户。
    """
    from playwright.async_api import async_playwright

    sec_uid: str | None = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage", "--disable-gpu"],
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

        async def on_route(route):
            nonlocal sec_uid
            url = route.request.url
            if "aweme/v1/web/discover/search" not in url or "aweme_user_web" not in url:
                await route.continue_()
                return
            # 已获取到结果则不再覆盖
            if sec_uid:
                await route.fulfill(response=await route.fetch())
                return
            try:
                resp = await route.fetch()
                body = await resp.json()
                user_list = body.get("user_list") or []
                if user_list:
                    user_info = user_list[0].get("user_info") or {}
                    sec_uid = user_info.get("sec_uid") or user_info.get("sec_user_id")
                await route.fulfill(response=resp)
            except Exception as e:
                logger.warning("拦截用户搜索 API 异常: %s", e)
                try:
                    await route.continue_()
                except Exception:
                    pass

        await page.route("**/*", on_route)
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)
        await page.goto(
            f"https://www.douyin.com/search/{quote(douyin_id)}?type=user",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        for _ in range(20):
            await asyncio.sleep(0.5)
            if sec_uid:
                break
        await browser.close()

    logger.info("[抖音号解析] %s → sec_uid=%s", douyin_id, sec_uid)
    return sec_uid


def _playwright_resolve_uid_sync(douyin_id: str, cookie: str) -> str | None:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_playwright_resolve_uid(douyin_id, cookie))
    finally:
        loop.close()


async def _playwright_search(
    keyword: str,
    cookie: str,
    limit: int,
    exclude_ids: set[str],
    headless: bool = True,
) -> tuple[list[dict], str | None]:
    """
    用 Playwright 在真实浏览器里搜索，拦截 general/search/single 响应直接取数据。
    完全绕过签名问题。
    """
    from playwright.async_api import async_playwright

    new_results: list[dict] = []
    nil_reason: str | None = None
    seen = set(exclude_ids)
    has_more = True
    api_hit_count = 0

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

    async def _run_launch(use_headless: bool):
        nonlocal has_more, nil_reason, api_hit_count

        async with async_playwright() as p:
            launch_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            if use_headless:
                launch_args += ["--disable-dev-shm-usage", "--disable-gpu"]
            browser = await p.chromium.launch(headless=use_headless, args=launch_args)
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
                            try:
                                body, _ = _json.JSONDecoder().raw_decode(text, idx)
                            except _json.JSONDecodeError:
                                body = {}
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
                    logger.warning("拦截搜索 API 异常: %s", e)
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", on_route)

            # 访问主页预热，再跳搜索页
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            logger.info("[搜索诊断] 主页加载完成，当前 URL: %s", page.url)
            await page.goto(
                f"https://www.douyin.com/search/{quote(keyword)}?type=general",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            # 等待第一个搜索 API 请求被触发，最多等 15 秒
            wait_rounds = 30 if use_headless else 60  # 有头模式给更多时间处理验证码
            for _ in range(wait_rounds):
                await asyncio.sleep(0.5)
                if api_hit_count > 0 or nil_reason:
                    break
            logger.info("[搜索诊断] 搜索页加载完成，当前 URL: %s，api_hit_count=%d，new_results=%d", page.url, api_hit_count, len(new_results))

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

    # 1. headless 搜索
    await _run_launch(headless)

    # 2. 本地环境 headless 无结果时，弹有头浏览器重试（用户可处理验证码）
    if not new_results and headless and not nil_reason and _is_local():
        logger.warning("headless 搜索无结果，切换有头浏览器重试（请在弹出窗口完成验证码）")
        seen.clear()
        seen.update(exclude_ids)
        api_hit_count = 0
        has_more = True  # 重置翻页状态，避免 headless 末尾 has_more=False 阻断翻页
        await _run_launch(False)

    if api_hit_count == 0 and not nil_reason:
        nil_reason = "搜索 API 未被触发（Cookie 已失效或页面加载失败，请重新获取 Cookie）"

    return new_results[:limit], nil_reason


async def _playwright_user_profile(
    sec_uid: str,
    cookie: str,
    limit: int,
    exclude_ids: set[str],
    tab: str = "post",
    headless: bool = True,
) -> tuple[list[dict], str | None]:
    """
    用 Playwright 访问用户主页，拦截作品或收藏列表接口。
    tab="post"     → 作品页，拦截 /aweme/v1/web/aweme/post/
    tab="favorite" → 收藏页，拦截 /aweme/v1/web/aweme/favorite/
    与关键词搜索逻辑保持一致，支持本地环境自动切换有头浏览器。
    """
    from playwright.async_api import async_playwright

    # 根据 tab 决定页面 URL 和要拦截的 API 路径
    if tab == "favorite":
        page_url = f"https://www.douyin.com/user/{sec_uid}?showTab=favorite_collection"
        api_pattern = "aweme/v1/web/aweme/favorite"
        nil_msg_empty = "该用户暂无收藏内容或 Cookie 已失效"
        nil_msg_no_trigger = "收藏 API 未被触发（Cookie 已失效或用户不存在，请重新获取 Cookie）"
    else:
        page_url = f"https://www.douyin.com/user/{sec_uid}"
        api_pattern = "aweme/v1/web/aweme/post"
        nil_msg_empty = "该用户暂无公开作品或 Cookie 已失效"
        nil_msg_no_trigger = "用户主页 API 未被触发（Cookie 已失效或用户不存在，请重新获取 Cookie）"

    new_results: list[dict] = []
    nil_reason: str | None = None
    seen = set(exclude_ids)
    api_hit_count = 0

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

    async def _run_launch(use_headless: bool):
        nonlocal nil_reason, api_hit_count

        async with async_playwright() as p:
            launch_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            if use_headless:
                launch_args += ["--disable-dev-shm-usage", "--disable-gpu"]
            browser = await p.chromium.launch(headless=use_headless, args=launch_args)
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

            async def on_route(route):
                nonlocal nil_reason, api_hit_count
                url = route.request.url
                if api_pattern not in url:
                    await route.continue_()
                    return
                api_hit_count += 1
                try:
                    resp = await route.fetch()
                    body = await resp.json()
                    for aweme in (body.get("aweme_list") or []):
                        parsed = _parse_aweme(aweme)
                        if parsed and parsed["aweme_id"] not in seen:
                            seen.add(parsed["aweme_id"])
                            new_results.append(parsed)
                    if not body.get("aweme_list") and not new_results:
                        # 只在 api_hit_count==1（第一次触发）时标记，避免末尾空页覆盖已有结果
                        if api_hit_count == 1:
                            nil_reason = nil_msg_empty
                    await route.fulfill(response=resp)
                except Exception as e:
                    logger.warning("拦截用户主页 API 异常: %s", e)
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", on_route)

            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            await page.goto(
                page_url,
                wait_until="domcontentloaded",
                timeout=15000,
            )

            wait_rounds = 30 if use_headless else 60
            for _ in range(wait_rounds):
                await asyncio.sleep(0.5)
                if api_hit_count > 0 or nil_reason:
                    break

            logger.info("[用户采集] sec_uid=%s，api_hit_count=%d，new_results=%d", sec_uid, api_hit_count, len(new_results))

            # 翻页，最多 5 次
            max_pages = min((limit * 5 // 10) + 5, 5)
            consecutive_empty = 0
            for _ in range(max_pages):
                if len(new_results) >= limit:
                    break
                prev_count = len(new_results)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
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

    await _run_launch(headless)

    if not new_results and headless and not nil_reason and _is_local():
        logger.warning("用户主页 headless 搜索无结果，切换有头浏览器重试")
        seen.clear()
        seen.update(exclude_ids)
        api_hit_count = 0
        nil_reason = None  # 清除 headless 阶段因空响应设置的 nil_reason，给有头模式重试机会
        await _run_launch(False)

    if api_hit_count == 0 and not nil_reason:
        nil_reason = nil_msg_no_trigger

    return new_results[:limit], nil_reason


def _playwright_search_sync(keyword: str, cookie: str, limit: int, exclude_ids: set[str]) -> tuple[list[dict], str | None]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_playwright_search(keyword, cookie, limit, exclude_ids))
    finally:
        loop.close()


def _playwright_user_profile_sync(sec_uid: str, cookie: str, limit: int, exclude_ids: set[str], tab: str = "post") -> tuple[list[dict], str | None]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_playwright_user_profile(sec_uid, cookie, limit, exclude_ids, tab=tab))
    finally:
        loop.close()


class DouyinSearcher:
    def __init__(self, client: DouyinClient):
        self.client = client

    async def resolve_sec_uid(self, douyin_id: str) -> str | None:
        """通过抖音号查找对应用户的 sec_uid，找不到返回 None。"""
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(
                pool,
                _playwright_resolve_uid_sync,
                douyin_id,
                self.client.cookie,
            )

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

    async def search_user_profile(
        self,
        sec_uid: str,
        limit: int = 50,
        tab: str = "post",
        exclude_ids: set[str] | None = None,
    ) -> tuple[list[dict], str | None]:
        """
        采集指定用户的作品或收藏列表，不阻塞 uvicorn event loop。
        tab="post"     → 用户作品
        tab="favorite" → 用户收藏（仅限自己账号或对方公开收藏）
        """
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(
                pool,
                _playwright_user_profile_sync,
                sec_uid,
                self.client.cookie,
                limit,
                exclude_ids or set(),
                tab,
            )
        return result

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
