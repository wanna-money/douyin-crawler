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


def _build_card(item: dict, config_name: str, image_key: Optional[str]) -> dict:
    """
    构建单条内容的飞书卡片（Schema 2.0）。
    包含：封面图 / 博主名 / 描述 / 抖音原链接按钮
    """
    aweme_id = item.get("aweme_id", "")
    desc = item.get("desc", "")[:200]
    author = item.get("author", "")
    media_type = item.get("media_type", "")
    douyin_url = f"https://www.douyin.com/video/{aweme_id}" if aweme_id else ""
    type_label = "📹 视频" if media_type == "video" else "🖼 图文"
    header_color = "wathet" if media_type == "video" else "purple"

    elements = []

    # 封面图（图集第一张 / 视频封面）
    if image_key:
        elements.append({
            "tag": "img",
            "img_key": image_key,
            "alt": {"tag": "plain_text", "content": desc[:30] or author},
            "mode": "fit_horizontal",
            "preview": True,
        })

    # 作者
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**{author}**",
        },
    })

    # 描述
    if desc:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": desc,
            },
        })

    # 分割线
    elements.append({"tag": "hr"})

    # 跳转按钮（仅视频有有效链接）
    if douyin_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "在抖音中查看"},
                "type": "primary",
                "multi_url": {
                    "url": douyin_url,
                    "pc_url": douyin_url,
                    "android_url": douyin_url,
                    "ios_url": douyin_url,
                },
            }],
        })

    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"{type_label} · {config_name}"},
            "template": header_color,
        },
        "body": {"elements": elements},
    }


async def upload_video(token: str, file_path: str) -> Optional[str]:
    """上传视频文件到飞书，返回 file_key；失败返回 None"""
    if not os.path.exists(file_path):
        return None
    try:
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        async with _http_client(timeout=120) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    f"{_FEISHU_API}/im/v1/files",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"file_type": "mp4", "file_name": filename, "file_size": str(file_size)},
                    files={"file": (filename, f, "video/mp4")},
                )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", -1) != 0:
            logger.warning("上传视频失败: %s", data.get("msg"))
            return None
        return data["data"]["file_key"]
    except Exception as e:
        logger.warning("上传视频异常: %s", e)
        return None


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
        token = await get_tenant_token(self.app_id, self.app_secret)
        sent = 0
        for item in items:
            try:
                media_type = item.get("media_type", "")
                file_paths = item.get("file_paths", [])

                # 获取封面 image_key
                image_key: Optional[str] = None
                if media_type == "image":
                    # 图集：用下载好的第一张图
                    for path in file_paths:
                        if os.path.exists(path) and path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                            image_key = await upload_image(token, path)
                            if image_key:
                                break
                            await asyncio.sleep(0.2)
                elif media_type == "video":
                    # 视频：用下载时保存的封面图
                    cover_path = item.get("cover_path")
                    if cover_path and os.path.exists(cover_path):
                        image_key = await upload_image(token, cover_path)

                # 发卡片（封面 + 作者 + 描述 + 跳转按钮）
                card = _build_card(item, config_name, image_key)
                await _send(token, self.chat_id, "interactive", json.dumps(card))

                # 视频：再发一条 media 消息（App 内可直接播放）
                if media_type == "video":
                    for path in file_paths:
                        if path.endswith(".mp4") and os.path.exists(path):
                            file_key = await upload_video(token, path)
                            if file_key:
                                await _send(
                                    token, self.chat_id, "media",
                                    json.dumps({"file_key": file_key}),
                                )
                            break

                sent += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("发送单条内容失败 aweme_id=%s: %s", item.get("aweme_id"), e)

        return sent


# 向后兼容
class FeishuNotifier(FeishuBotNotifier):
    pass
