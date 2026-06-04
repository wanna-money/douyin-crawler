import httpx
from typing import Any

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)


class DouyinClient:
    def __init__(self, cookie: str, timeout: int = 30):
        self.cookie = cookie
        self.timeout = timeout

    def _build_headers(self) -> dict:
        return {
            "User-Agent": _DEFAULT_UA,
            "Referer": "https://www.douyin.com/?recommend=1",
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "priority": "u=1, i",
        }

    async def get(self, url: str, params: dict) -> Any:
        async with httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def download_file(self, url: str, dest_path: str) -> None:
        async with httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=120,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                import aiofiles
                async with aiofiles.open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)
