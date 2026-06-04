"""
持久签名服务。启动时初始化一个持久 Playwright 浏览器实例，
之后每次签名请求只需在已有页面跳转搜索页（~3s），无需重新启动浏览器（~15s）。

POST /sign  body: {"keyword": "...", "cookie": "..."}
返回: {"a_bogus": "...", "verifyFp": "...", "webid": "...", "uifid": "..."}
"""
import asyncio
import json
import logging
import os
import random
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path

PORT = 18690

# 日志写到项目 logs/ 目录
_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sign_server] %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "sign_server.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# 全局持久状态
_loop: asyncio.AbstractEventLoop | None = None
_page = None
_page_cookie: str = ""
_lock = threading.Lock()


async def _init_browser(cookie: str):
    global _page, _page_cookie
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",                    # 容器/服务器环境必须
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",         # /dev/shm 空间不足时防崩溃
            "--disable-gpu",                   # 无 GPU 环境
            "--disable-software-rasterizer",
            "--no-first-run",
            "--no-zygote",
        ],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        )
    )
    # 注入 cookie（在异步上下文里直接 await）
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
    try:
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        logger.error("goto douyin.com failed: %s", e)
    await asyncio.sleep(2)
    _page = page
    _page_cookie = cookie
    logger.info("Browser initialized")
    # 预热：触发一次搜索让页面 JS 完全就绪
    await _do_sign("美食", cookie)


async def _do_sign(keyword: str, cookie: str) -> dict:
    global _page, _page_cookie

    # Cookie 变了就重新初始化浏览器
    if _page is None or cookie != _page_cookie:
        await _init_browser(cookie)

    captured: dict = {}
    done = asyncio.Event()

    def on_request(req):
        if "general/search/single" in req.url and not captured:
            qs = parse_qs(urlparse(req.url).query)
            for k in ["a_bogus", "webid", "verifyFp", "fp", "uifid"]:
                captured[k] = qs.get(k, [""])[0]
            done.set()

    _page.on("request", on_request)
    try:
        rand = random.randint(10000, 99999)
        await _page.goto(
            f"https://www.douyin.com/search/{quote(keyword)}?type=general&_t={rand}",
            wait_until="commit",
            timeout=15000,
        )
        await asyncio.wait_for(done.wait(), timeout=20)
    except Exception as e:
        logger.error("goto/wait failed: %s", e)
    finally:
        _page.remove_listener("request", on_request)

    # 读取页面最新 Cookie 中的 msToken，回传给调用方用于刷新
    try:
        cookies = await _page.context.cookies()
        ms_token = next(
            (c['value'] for c in cookies if c['name'] == 'msToken' and c.get('domain', '').endswith('douyin.com')),
            None
        )
        if ms_token:
            captured["fresh_ms_token"] = ms_token
    except Exception:
        pass

    return captured


def sign_sync(keyword: str, cookie: str) -> dict:
    """在持久 event loop 里执行签名，线程安全，失败时最多重试 2 次。"""
    with _lock:
        for attempt in range(3):
            future = asyncio.run_coroutine_threadsafe(_do_sign(keyword, cookie), _loop)
            result = future.result(timeout=30)
            if result.get("a_bogus"):
                return result
            time.sleep(1)
        return {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        try:
            result = sign_sync(body["keyword"], body["cookie"])
        except Exception as e:
            result = {"error": str(e)}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def log_message(self, *args):
        pass


def _run_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


if __name__ == "__main__":
    # 在独立线程里跑 event loop
    _loop = asyncio.new_event_loop()
    t = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
    t.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    logger.info("sign_server ready on %d", PORT)
    server.serve_forever()