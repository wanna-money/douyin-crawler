import asyncio
import json
import os
import subprocess
import time
import urllib.request
from urllib.parse import urlparse, parse_qs, quote

from backend.crawler.client import DouyinClient

_SEARCH_URL = "https://www.douyin.com/aweme/v1/web/general/search/single/"
_HASHTAG_URL = "https://www.douyin.com/aweme/v1/web/challenge/aweme/"
_SIGN_SERVER_URL = "http://127.0.0.1:18690"
_SIGN_SERVER_PY = os.path.join(os.path.dirname(__file__), "sign_server.py")

_NIL_REASONS = {
    "invalid_app": "请求参数不合法（缺少设备/浏览器参数）",
    "verify_check": "需要人机验证（Cookie 已失效，请重新获取）",
    "no_result": "该关键词暂无搜索结果",
}

_sign_proc = None


def _call_sign_server_sync(keyword: str, cookie: str) -> dict:
    """用标准库 urllib 同步调用签名服务（避免 httpx async 问题）。"""
    global _sign_proc
    # 启动服务（如果未运行）
    try:
        urllib.request.urlopen(_SIGN_SERVER_URL, timeout=3)
    except Exception:
        _sign_proc = subprocess.Popen(
            [os.sys.executable, _SIGN_SERVER_PY],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(_SIGN_SERVER_URL, timeout=1)
                break
            except Exception:
                continue

    body = json.dumps({"keyword": keyword, "cookie": cookie}).encode()
    req = urllib.request.Request(
        _SIGN_SERVER_URL + "/sign",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 第一次调用需要浏览器初始化（~15s），后续复用页面（~3s），给足 60s
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


async def _get_sign(keyword: str, cookie: str) -> dict:
    """在线程池里同步调用签名服务，不阻塞事件循环。"""
    return await asyncio.to_thread(_call_sign_server_sync, keyword, cookie)


class DouyinSearcher:
    def __init__(self, client: DouyinClient):
        self.client = client
        # 缓存签名参数，避免每次翻页都重新打开浏览器
        self._sign_cache: dict = {}

    def _extract_cookie_val(self, key: str) -> str:
        for part in self.client.cookie.split(";"):
            part = part.strip()
            if part.startswith(key + "="):
                return part[len(key) + 1:]
        return ""

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

    def _nil_reason(self, data: dict) -> str | None:
        nil = data.get("search_nil_info")
        if not nil:
            return None
        item = nil.get("search_nil_item", "")
        nil_type = nil.get("search_nil_type", "")
        key = item or nil_type
        return _NIL_REASONS.get(key, f"搜索为空：{nil_type}/{item}")

    def _extract_awemes(self, data: dict) -> list[dict]:
        """从 general/search/single 响应中提取 aweme 列表。"""
        results = []
        # data[] 每项含 aweme_info
        for item in data.get("data") or []:
            aweme = item.get("aweme_info")
            if aweme:
                parsed = self._parse_aweme(aweme)
                if parsed:
                    results.append(parsed)
        return results

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
        """
        搜索关键词，返回 (新内容列表, nil_reason)。
        exclude_ids: 已见过的 aweme_id 集合，搜索时跳过，直到累计够 limit 条新内容或无更多数据。
        """
        new_results = []       # 只计去重后的新内容
        all_fetched: list[dict] = []  # 本次搜到的全部（含重复）
        seen = exclude_ids or set()
        offset = 0
        nil_reason: str | None = None
        search_id = ""
        max_fetch = limit * 5  # 最多多搜 5 倍防止死循环

        sign = await _get_sign(keyword, self.client.cookie)
        if not sign.get("a_bogus"):
            return [], "无法获取签名参数（Playwright 拦截失败）"

        verify_fp = sign.get("verifyFp") or self._extract_cookie_val("s_v_web_id")
        webid = sign.get("webid") or "7647400631514613294"
        uifid = sign.get("uifid") or ""
        a_bogus = sign["a_bogus"]

        while len(new_results) < limit and len(all_fetched) < max_fetch:
            params = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "search_channel": "aweme_general",
                "enable_history": 1,
                "keyword": keyword,
                "search_source": "normal_search",
                "query_correct_type": 1,
                "is_filter_search": 0,
                "disable_rs": 0,
                "offset": offset,
                "count": 10,
                "need_filter_settings": 0 if offset > 0 else 1,
                "list_type": "single",
                "update_version_code": "170400",
                "pc_client_type": 1,
                "pc_libra_divert": "Mac",
                "version_code": "190600",
                "version_name": "19.6.0",
                "cookie_enabled": "true",
                "screen_width": 1280,
                "screen_height": 720,
                "browser_language": "zh-CN",
                "browser_platform": "MacIntel",
                "browser_name": "Chrome",
                "browser_version": "148.0.0.0",
                "browser_online": "true",
                "engine_name": "Blink",
                "engine_version": "148.0.0.0",
                "os_name": "Mac OS",
                "os_version": "10.15.7",
                "device_memory": 16,
                "platform": "PC",
                "downlink": 10,
                "effective_type": "4g",
                "round_trip_time": 0,
                "webid": webid,
                "verifyFp": verify_fp,
                "fp": verify_fp,
                "a_bogus": a_bogus,
            }
            if uifid:
                params["uifid"] = uifid
            if search_id:
                params["search_id"] = search_id

            data = await self.client.get(_SEARCH_URL, params)
            if not isinstance(data, dict):
                nil_reason = f"API 返回非预期格式：{type(data).__name__}"
                break

            awemes = self._extract_awemes(data)
            all_fetched.extend(awemes)

            for aweme in awemes:
                if aweme["aweme_id"] not in seen:
                    seen.add(aweme["aweme_id"])
                    new_results.append(aweme)
                    if len(new_results) >= limit:
                        break

            if not search_id:
                search_id = (data.get("extra") or {}).get("search_request_id", "")

            if not awemes:
                nil_reason = self._nil_reason(data)
                break
            if not data.get("has_more"):
                break

            offset += len(awemes)
            new_sign = await _get_sign(keyword, self.client.cookie)
            if new_sign.get("a_bogus"):
                a_bogus = new_sign["a_bogus"]
            await asyncio.sleep(1)

        return new_results, nil_reason

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
                nil_reason = self._nil_reason(data) or "话题下暂无内容"
                break
            if not data.get("has_more"):
                break
            cursor = data.get("cursor", cursor + 20)
            await asyncio.sleep(1)
        return results[:limit], nil_reason
