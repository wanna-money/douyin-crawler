"""
通过 Playwright 拦截真实抖音搜索请求，提取 a_bogus 和 msToken。
在 DouyinSearcher 里调用 intercept_search_params(keyword) 获取签名参数。
"""
import asyncio
import re
import sqlite3
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent / "douyin.db"

async def intercept_search_params(keyword: str, cookie: str, timeout: int = 15) -> dict:
    """
    打开抖音搜索页，拦截第一个 search/item 请求，
    返回 {'a_bogus': ..., 'msToken': ..., 'webid': ..., 'verifyFp': ...}
    """
    from playwright.async_api import async_playwright

    result = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            )
        )
        # 注入 cookie
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                try:
                    await context.add_cookies([{
                        "name": name.strip(), "value": value.strip(),
                        "domain": ".douyin.com", "path": "/",
                    }])
                except Exception:
                    pass

        page = await context.new_page()
        captured = asyncio.Event()

        def on_request(request):
            if "aweme/v1/web/search/item" in request.url and not result:
                qs = parse_qs(urlparse(request.url).query)
                result["a_bogus"] = qs.get("a_bogus", [""])[0]
                result["msToken"] = qs.get("msToken", [""])[0]
                result["webid"] = qs.get("webid", [""])[0]
                verifyFp = qs.get("verifyFp", [""])[0]
                result["verifyFp"] = verifyFp
                result["fp"] = verifyFp
                captured.set()

        page.on("request", on_request)

        try:
            await page.goto(
                f"https://www.douyin.com/search/{quote(keyword)}?type=general",
                wait_until="domcontentloaded",
                timeout=timeout * 1000,
            )
            await asyncio.wait_for(captured.wait(), timeout=timeout)
        except Exception:
            pass
        finally:
            await browser.close()

    return result
