"""
抖音扫码登录 → 自动提取 Cookie 工具

用法：
    uv run python get_cookie.py

流程：
    1. 打开真实 Chromium 浏览器窗口，导航到抖音登录页
    2. 等待你用手机扫码登录（或手机号验证码登录）
    3. 检测到登录成功后自动提取 Cookie
    4. 将 Cookie 写入 .env 文件并打印到终端
"""

import asyncio
import os
import re
from pathlib import Path

try:
    from playwright.async_api import async_playwright, Page
except ImportError:
    print("请先安装 playwright：uv add playwright && uv run playwright install chromium")
    raise

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
LOGIN_URL = "https://www.douyin.com"


def _update_env(cookie_str: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    if re.search(r"^DOUYIN_COOKIE=", content, re.MULTILINE):
        content = re.sub(
            r"^DOUYIN_COOKIE=.*$",
            f"DOUYIN_COOKIE={cookie_str}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content = content.rstrip("\n") + f"\nDOUYIN_COOKIE={cookie_str}\n"
    ENV_FILE.write_text(content, encoding="utf-8")


async def _wait_for_login(page: Page, timeout_sec: int = 120) -> bool:
    """轮询检查是否已登录（uid_tt cookie 出现即视为成功）"""
    print("等待登录中", end="", flush=True)
    for _ in range(timeout_sec):
        cookies = await page.context.cookies()
        names = {c["name"] for c in cookies}
        if "uid_tt" in names or "sessionid" in names:
            print("\n✅ 检测到登录成功！")
            return True
        print(".", end="", flush=True)
        await asyncio.sleep(1)
    print("\n❌ 等待超时")
    return False


async def main() -> None:
    print("=" * 50)
    print("抖音 Cookie 获取工具")
    print("=" * 50)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print(f"\n正在打开 {LOGIN_URL} ...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        print("\n📱 请在弹出的浏览器窗口中完成登录（扫码或手机验证码）")
        print("   登录成功后程序会自动继续，无需手动操作\n")

        logged_in = await _wait_for_login(page)
        if not logged_in:
            print("登录超时，请重新运行脚本")
            await browser.close()
            return

        # 访问搜索页，触发 JS 生成 msToken
        print("正在访问搜索页以获取 msToken ...")
        try:
            await page.goto("https://www.douyin.com/search/美食?type=general", wait_until="load", timeout=60000)
        except Exception:
            # 抖音登录后可能触发内部重定向导致 ERR_ABORTED，忽略并继续
            pass
        await asyncio.sleep(3)

        # 等待 msToken 写入 cookie
        for _ in range(10):
            cookies_raw = await context.cookies()
            if any(c["name"] == "msToken" for c in cookies_raw):
                print("✅ msToken 已获取")
                break
            await asyncio.sleep(1)
        else:
            print("⚠️  未检测到 msToken，继续使用当前 Cookie")

        cookies = await context.cookies()
        cookie_str = "; ".join(
            f"{c['name']}={c['value']}"
            for c in cookies
            if c.get("domain", "").endswith("douyin.com")
        )

        print("\n=== Cookie（前 120 字符预览）===")
        print(cookie_str[:120] + "...\n")

        _update_env(cookie_str)
        print(f"✅ Cookie 已写入 {ENV_FILE}")
        print("\n现在可以启动服务并在「系统设置」中使用该 Cookie：")
        print("  uv run python -m backend.main")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())


def main_sync() -> None:
    asyncio.run(main())
