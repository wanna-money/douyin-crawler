# backend/llm.py
import logging
import httpx

logger = logging.getLogger(__name__)


def build_prompt(template: str, keyword: str, desc: str, author: str) -> str:
    return template.format(
        keyword=keyword,
        desc=desc[:200],
        author=author,
    )


def _build_vision_messages(keyword: str, cover_url: str) -> list[dict]:
    """构造多模态消息：封面图 + 文字问题"""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": cover_url},
                },
                {
                    "type": "text",
                    "text": (
                        f'这张图片的内容是否与搜索关键词「{keyword}」相关？\n'
                        '只回答"是"或"否"，不要解释。'
                    ),
                },
            ],
        }
    ]


def _build_text_messages(prompt: str) -> list[dict]:
    """构造纯文本消息（降级方案）"""
    return [{"role": "user", "content": prompt}]


def _is_yes(answer: str) -> bool:
    return "是" in answer or "yes" in answer.lower()


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
) -> bool:
    """
    判断内容是否与关键词相关。
    - 有封面图时：优先发封面图给多模态 LLM 判断（更准确）
    - 无封面图时：降级为纯文字描述判断
    - 网络异常或解析失败时默认返回 True（放行），避免误过滤
    """
    async def _call(messages: list, mode: str) -> bool:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
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

    # 有封面图时优先走 vision，失败则降级为文字
    if cover_url:
        try:
            return await _call(_build_vision_messages(keyword, cover_url), "vision")
        except Exception as exc:
            logger.warning("LLM vision 失败，降级为文字判断: %s", exc)

    prompt = build_prompt(prompt_template, keyword=keyword, desc=desc, author=author)
    try:
        return await _call(_build_text_messages(prompt), "text")
    except Exception as exc:
        logger.warning("LLM 相关性检测失败，默认放行 [text]: %s", exc)
        return True
