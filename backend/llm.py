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


def _build_openai_datauri_messages(prompt: str, b64_data: str) -> list[dict]:
    """OpenAI 标准格式：content 数组 + data URI"""
    data_uri = f"data:image/jpeg;base64,{b64_data}"
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]


def _build_openai_url_messages(prompt: str, url: str) -> list[dict]:
    """OpenAI 标准格式：content 数组 + 远程 URL（部分托管服务支持）"""
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        }
    ]


async def _fetch_as_base64(url: str, timeout: int) -> str:
    """下载图片，返回裸 base64 字符串（不含 data URI 前缀）"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode()


def _is_yes(answer: str) -> bool:
    return "是" in answer or "yes" in answer.lower()


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
    判断内容是否相关，返回 (是否相关, curl命令字符串)。

    有图时按以下顺序尝试：
      1. OpenAI content 数组 + data URI（优先）
      2. OpenAI content 数组 + 远程 URL（托管 API 兜底）
    任何格式失败或无图时直接放行，不降级文字判断，不切换其他 LLM。
    """
    last_curl: list[str] = []

    def _build_curl(messages: list) -> str:
        import json as _json
        body = _json.dumps(
            {"model": model, "messages": messages, "max_tokens": 10, "temperature": 0},
            ensure_ascii=False,
        )
        auth = f' -H "Authorization: Bearer {api_key}"' if api_key else ""
        return (
            f'curl {base_url.rstrip("/")}/chat/completions'
            f' -H "Content-Type: application/json"'
            f"{auth}"
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
                json={"model": model, "messages": messages, "max_tokens": 10, "temperature": 0},
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()
            result = _is_yes(answer)
            logger.debug("LLM[%s] -> %s (%s)", mode, result, answer)
            return result

    prompt = build_prompt(prompt_template, keyword=keyword, desc=desc, author=author)

    if cover_url:
        # 先下载图片，后续所有 vision 格式都需要 base64
        try:
            b64_data = await _fetch_as_base64(cover_url, timeout)
        except Exception as exc:
            logger.warning("LLM 图片下载失败，默认放行: %s", exc)
            return True, ""

        if b64_data:
            # 格式1：OpenAI content 数组 + data URI（优先，兼容 LM Studio / OpenAI 等）
            try:
                result = await _call(_build_openai_datauri_messages(prompt, b64_data), "vision-datauri")
                return result, last_curl[0] if last_curl else ""
            except Exception as exc:
                if _is_vision_unsupported(str(exc)):
                    logger.warning("LLM 不支持图片识别，默认放行: %s", exc)
                    return True, last_curl[0] if last_curl else ""
                logger.debug("LLM vision-datauri 失败，尝试 openai url: %s", exc)

            # 格式2：OpenAI content 数组 + 远程 URL（托管 API，如 OpenAI / Claude）
            try:
                result = await _call(_build_openai_url_messages(prompt, cover_url), "vision-url")
                return result, last_curl[0] if last_curl else ""
            except Exception as exc:
                if _is_vision_unsupported(str(exc)):
                    logger.warning("LLM 不支持图片识别，默认放行: %s", exc)
                    return True, last_curl[0] if last_curl else ""
                logger.warning("LLM 所有 vision 格式均失败，默认放行: %s", exc)
                return True, last_curl[0] if last_curl else ""

    # 无图片时直接放行，不调用 LLM
    logger.warning("LLM 无图片，默认放行")
    return True, ""
