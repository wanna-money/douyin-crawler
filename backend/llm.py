# backend/llm.py
import base64
import logging
import httpx

logger = logging.getLogger(__name__)


def build_prompt(template: str, keyword: str, desc: str, author: str) -> str:
    return template.format(
        keyword=keyword,
        desc=desc[:200],
        author=author,
    )


def _build_vision_messages(prompt: str, cover_url: str) -> list[dict]:
    """构造多模态消息：文字 prompt + 封面图"""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {"url": cover_url},
                },
            ],
        }
    ]


async def _fetch_as_base64(url: str, timeout: int) -> str:
    """下载图片并转为 data URI（base64 编码），强制使用 image/jpeg 以兼容不支持 webp 的接口"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = base64.b64encode(resp.content).decode()
        return f"data:image/jpeg;base64,{data}"


def _build_text_messages(prompt: str) -> list[dict]:
    """构造纯文本消息（降级方案）"""
    return [{"role": "user", "content": prompt}]


def _is_yes(answer: str) -> bool:
    return "是" in answer or "yes" in answer.lower()


# 各家 API 不支持视觉时的错误关键词
_VISION_UNSUPPORTED_HINTS = (
    "does not support image",
    "does not support vision",
    "not support image",
    "not support vision",
    "image input",
    "multimodal",
    "vision is not",
    "无法识别图片",
    "不支持图片",
    "不支持图像",
)


def _is_vision_unsupported(err: str) -> bool:
    err_lower = err.lower()
    return any(hint.lower() in err_lower for hint in _VISION_UNSUPPORTED_HINTS)


async def check_relevance(
    keyword: str,
    desc: str,
    author: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt_template: str,
    cover_url: str = "",
    timeout: int = 20,
) -> tuple[bool, str]:
    """
    判断内容是否与关键词相关。
    返回 (是否相关, curl命令字符串)。
    - 有封面图时：优先发封面图给多模态 LLM 判断（更准确）
    - 无封面图时：降级为纯文字描述判断
    - 网络异常或解析失败时默认返回 True（放行），避免误过滤
    """
    last_curl: list[str] = []

    def _build_curl(messages: list) -> str:
        import json as _json
        body = _json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": 10,
            "temperature": 0,
        }, ensure_ascii=False)
        auth = f' -H "Authorization: Bearer {api_key}"' if api_key else ""
        return (
            f'curl {base_url.rstrip("/")}/chat/completions'
            f' -H "Content-Type: application/json"'
            f'{auth}'
            f" -d '{body}'"
        )

    async def _call(messages: list, mode: str) -> bool:
        last_curl.clear()
        last_curl.append(_build_curl(messages))
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()
            result = _is_yes(answer)
            logger.debug("LLM[%s] keyword=%s -> %s (%s)", mode, keyword, result, answer)
            return result

    prompt = build_prompt(prompt_template, keyword=keyword, desc=desc, author=author)

    # 有封面图时优先走 vision，失败则降级为文字
    if cover_url:
        try:
            result = await _call(_build_vision_messages(prompt, cover_url), "vision")
            return result, last_curl[0] if last_curl else ""
        except Exception as exc:
            exc_str = str(exc)
            # 400 或含 base64 关键词：接口不接受 URL，转 base64 重试
            is_400 = "400" in exc_str
            if is_400 or "base64" in exc_str.lower():
                try:
                    data_uri = await _fetch_as_base64(cover_url, timeout)
                    result = await _call(_build_vision_messages(prompt, data_uri), "vision-base64")
                    return result, last_curl[0] if last_curl else ""
                except Exception as exc2:
                    logger.warning("LLM vision base64 重试失败，降级为文字判断: %s", exc2)
            elif _is_vision_unsupported(exc_str):
                # 模型不支持图片识别，无法做 vision 判断，直接放行避免误过滤
                logger.warning("LLM 模型不支持图片识别，默认放行（建议更换支持视觉的模型）: %s", exc)
                return True, last_curl[0] if last_curl else ""
            else:
                logger.warning("LLM vision 失败，降级为文字判断: %s", exc)

    try:
        result = await _call(_build_text_messages(prompt), "text")
        return result, last_curl[0] if last_curl else ""
    except Exception as exc:
        logger.warning("LLM 相关性检测失败，默认放行 [text]: %s", exc)
        return True, last_curl[0] if last_curl else ""
