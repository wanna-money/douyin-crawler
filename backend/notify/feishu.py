# backend/notify/feishu.py
import asyncio
import logging
import os
import time
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"

# token 缓存：{ app_id: (token, expire_at) }
_token_cache: dict[str, tuple[str, float]] = {}


_FEISHU_ERROR_HINTS: dict[int, str] = {
    99991663: "应用未安装到企业，请在飞书管理后台发布应用",
    99991401: "app_id 或 app_secret 错误",
    10003: "chat_id 无效或机器人未加入该群",
    10012: "消息内容格式错误",
    10013: "机器人没有发消息权限，请在应用管理页开启 im:message 权限",
    10014: "机器人被群管理员禁止发言",
    11000: "应用权限不足，请检查是否已开启「发送消息」能力",
}


async def get_tenant_token(app_id: str, app_secret: str) -> str:
    """获取 tenant_access_token，缓存 1.8 小时"""
    now = time.time()
    cached = _token_cache.get(app_id)
    if cached and cached[1] > now:
        return cached[0]

    async with httpx.AsyncClient(timeout=10) as client:
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
        expire = data.get("expire", 7200)
        _token_cache[app_id] = (token, now + expire - 360)  # 提前 6 分钟过期
        return token


async def upload_image(token: str, file_path: str) -> Optional[str]:
    """上传图片到飞书，返回 image_key；失败返回 None"""
    if not os.path.exists(file_path):
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
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


def _build_card(items: list[dict], config_name: str, image_keys: dict[str, str]) -> dict:
    """构建飞书卡片消息，每条采集结果一个卡片块"""
    elements = []

    # 标题行
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📡 {config_name}** · 本次采集 {len(items)} 条新内容",
        }
    })
    elements.append({"tag": "hr"})

    for item in items[:10]:  # 单卡片最多展示 10 条，避免消息过长
        aweme_id = item.get("aweme_id", "")
        desc = item.get("desc", "")[:80]
        author = item.get("author", "")
        media_type = item.get("media_type", "")
        file_paths = item.get("file_paths", [])
        type_icon = "📹" if media_type == "video" else "🖼"

        # 文字块
        text_md = f"**{type_icon} {author}**\n{desc}" if desc else f"**{type_icon} {author}**"
        block: dict = {
            "tag": "div",
            "text": {"tag": "lark_md", "content": text_md},
        }

        # 图片：优先用已上传的 image_key，附到卡片
        img_key = None
        for path in file_paths:
            if path in image_keys:
                img_key = image_keys[path]
                break
        if img_key:
            block["extra"] = {
                "tag": "img",
                "img_key": img_key,
                "alt": {"tag": "plain_text", "content": desc[:20]},
            }

        elements.append(block)

        # 视频提示
        if media_type == "video" and file_paths:
            elements.append({
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"视频已下载: {os.path.basename(file_paths[0])}"}]
            })

    if len(items) > 10:
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"还有 {len(items) - 10} 条，请查看下载目录"}]
        })

    return {
        "schema": "2.0",
        "body": {"elements": elements},
        "header": {
            "title": {"tag": "plain_text", "content": f"抖音采集 · {config_name}"},
            "template": "indigo",
        },
    }


async def send_message(
    token: str,
    chat_id: str,
    msg_type: str,
    content: str,
) -> bool:
    """发送消息到指定群"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_FEISHU_API}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": chat_id,
                "msg_type": msg_type,
                "content": content,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", -1) != 0:
            code = data.get("code", -1)
            msg = data.get("msg", "未知错误")
            hint = _FEISHU_ERROR_HINTS.get(code, "")
            err = f"发送消息失败 [code={code}]: {msg}" + (f"（{hint}）" if hint else "")
            logger.warning(err)
            raise RuntimeError(err)
        return True
        return True


async def list_bot_chats(app_id: str, app_secret: str) -> list[dict]:
    """查询机器人所在的群列表，返回 [{chat_id, name, avatar}]"""
    token = await get_tenant_token(app_id, app_secret)
    chats = []
    page_token = None
    async with httpx.AsyncClient(timeout=15) as client:
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

    async def _token(self) -> str:
        return await get_tenant_token(self.app_id, self.app_secret)

    async def send_media_items(self, items: list[dict], config_name: str = "") -> int:
        """上传图片并发送卡片消息，返回成功发送条数"""
        if not items:
            return 0
        try:
            token = await self._token()

            # 上传所有图片文件，建立 path -> image_key 映射
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

            import json
            card = _build_card(items, config_name, image_keys)
            ok = await send_message(token, self.chat_id, "interactive", json.dumps(card))
            return len(items) if ok else 0
        except Exception as e:
            logger.error("飞书机器人发送失败: %s", e)
            return 0


# 保持向后兼容：旧代码调用 FeishuNotifier 的地方
class FeishuNotifier(FeishuBotNotifier):
    """别名，保持 task_runner 的调用兼容"""
    pass
