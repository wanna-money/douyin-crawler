# backend/notify/feishu.py
import asyncio
import json
import logging
import os
import time
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"

_token_cache: dict[str, tuple[str, float]] = {}

_FEISHU_ERROR_HINTS: dict[int, str] = {
    99991663: "应用未安装到企业，请在飞书管理后台发布应用",
    99991401: "app_id 或 app_secret 错误",
    10003: "chat_id 无效或机器人未加入该群",
    10013: "机器人没有发消息权限，请在应用管理页开启 im:message 权限",
    10014: "机器人被群管理员禁止发言",
    11000: "应用权限不足，请检查是否已开启「发送消息」能力",
}


def _http_client(**kwargs) -> httpx.AsyncClient:
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("ALL_PROXY")
    )
    if proxy:
        return httpx.AsyncClient(proxy=proxy, **kwargs)
    return httpx.AsyncClient(**kwargs)


async def get_tenant_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    cached = _token_cache.get(app_id)
    if cached and cached[1] > now:
        return cached[0]
    async with _http_client(timeout=10) as client:
        resp = await client.post(
            f"{_FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", -1) != 0:
            code = data.get("code", -1)
            msg = data.get("msg", "未知错误")
            hint = _FEISHU_ERROR_HINTS.get(code, "")
            raise RuntimeError(f"获取飞书 token 失败 [code={code}]: {msg}" + (f"（{hint}）" if hint else ""))
        token = data["tenant_access_token"]
        _token_cache[app_id] = (token, now + data.get("expire", 7200) - 360)
        return token


async def upload_image(token: str, file_path: str) -> Optional[str]:
    if not os.path.exists(file_path):
        return None
    try:
        async with _http_client(timeout=30) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    f"{_FEISHU_API}/im/v1/images",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"image_type": "message"},
                    files={"image": f},
                )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", -1) != 0:
            logger.warning("上传图片失败: %s", data.get("msg"))
            return None
        return data["data"]["image_key"]
    except Exception as e:
        logger.warning("上传图片异常: %s", e)
        return None


def _build_post(items: list[dict], config_name: str, image_keys: dict[str, str]) -> dict:
    """
    构建飞书 post 富文本消息。
    post 格式是飞书最稳定的富文本格式，支持加粗/图片，无版本兼容问题。
    content 结构: {"zh_cn": {"title": "...", "content": [[line], [line], ...]}}
    每行是一个列表，列表内是行内元素（text / img）。
    """
    lines = []

    # 标题行
    lines.append([{"tag": "text", "text": f"共 {len(items)} 条新内容", "style": ["bold"]}])

    for item in items[:20]:
        desc = item.get("desc", "")[:120]
        author = item.get("author", "")
        media_type = item.get("media_type", "")
        file_paths = item.get("file_paths", [])
        type_label = "视频" if media_type == "video" else "图文"

        # 作者 + 类型行
        line: list = [
            {"tag": "text", "text": f"[{type_label}] ", "style": ["bold"]},
            {"tag": "text", "text": author, "style": ["bold"]},
        ]
        lines.append(line)

        # 描述行
        if desc:
            lines.append([{"tag": "text", "text": desc}])

        # 图片（仅图集第一张）
        for path in file_paths:
            if path in image_keys:
                lines.append([{"tag": "img", "image_key": image_keys[path]}])
                break

        # 视频文件名
        if media_type == "video" and file_paths:
            lines.append([{"tag": "text", "text": f"  ▶ {os.path.basename(file_paths[0])}", "style": ["italic"]}])

        # 空行分隔
        lines.append([{"tag": "text", "text": ""}])

    if len(items) > 20:
        lines.append([{"tag": "text", "text": f"…还有 {len(items) - 20} 条，请查看下载目录", "style": ["italic"]}])

    return {
        "zh_cn": {
            "title": f"📡 抖音采集 · {config_name}",
            "content": lines,
        }
    }


async def _send(token: str, chat_id: str, msg_type: str, content: str) -> bool:
    async with _http_client(timeout=15) as client:
        resp = await client.post(
            f"{_FEISHU_API}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "receive_id": chat_id,
                "msg_type": msg_type,
                "content": content,
            },
        )
    data = resp.json()
    if not resp.is_success or data.get("code", -1) != 0:
        code = data.get("code", resp.status_code)
        msg = data.get("msg", resp.text)
        hint = _FEISHU_ERROR_HINTS.get(code, "")
        err = f"发送消息失败 [code={code}]: {msg}" + (f"（{hint}）" if hint else "")
        logger.warning("飞书发送失败: %s | 响应: %s", err, data)
        raise RuntimeError(err)
    return True


async def list_bot_chats(app_id: str, app_secret: str) -> list[dict]:
    token = await get_tenant_token(app_id, app_secret)
    chats = []
    page_token = None
    async with _http_client(timeout=15) as client:
        while True:
            params: dict = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            resp = await client.get(
                f"{_FEISHU_API}/im/v1/chats",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", -1) != 0:
                raise RuntimeError(f"查询群列表失败: {data.get('msg')}")
            for item in data.get("data", {}).get("items", []):
                chats.append({
                    "chat_id": item.get("chat_id", ""),
                    "name": item.get("name", ""),
                    "avatar": item.get("avatar", ""),
                    "description": item.get("description", ""),
                })
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")
    return chats


class FeishuBotNotifier:
    def __init__(self, app_id: str, app_secret: str, chat_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.chat_id = chat_id

    async def send_media_items(self, items: list[dict], config_name: str = "") -> int:
        if not items:
            return 0
        try:
            token = await get_tenant_token(self.app_id, self.app_secret)

            # 上传图集封面图
            image_keys: dict[str, str] = {}
            for item in items:
                if item.get("media_type") != "image":
                    continue
                for path in item.get("file_paths", []):
                    if path.endswith((".jpg", ".jpeg", ".png", ".webp")) and path not in image_keys:
                        key = await upload_image(token, path)
                        if key:
                            image_keys[path] = key
                        await asyncio.sleep(0.2)

            post = _build_post(items, config_name, image_keys)
            await _send(token, self.chat_id, "post", json.dumps(post))
            return len(items)
        except Exception as e:
            logger.error("飞书机器人发送失败: %s", e)
            return 0


# 向后兼容
class FeishuNotifier(FeishuBotNotifier):
    pass
