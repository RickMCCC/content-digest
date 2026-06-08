"""DeepSeek AI 日报生成器"""
import os
import logging
from datetime import datetime

from openai import OpenAI

from digest.prompt import build_digest_prompt, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def generate_digest(items: list[dict], config: dict) -> dict | None:
    """
    Generate daily digest using DeepSeek API.

    Returns dict with keys:
    - title: str
    - content_html: str
    - item_count: int
    - date: str
    Or None if no items or API error.
    """
    if not items:
        logger.info("No items to generate digest for")
        return None

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set, skipping digest generation")
        return None

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    today = datetime.utcnow()
    date_str = today.strftime("%Y-%m-%d")
    # Use Beijing time for display
    month_day = today.strftime("%m月%d日")

    prompt = build_digest_prompt(items)

    try:
        response = client.chat.completions.create(
            model=config.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=config.get("max_tokens", 2000),
            temperature=config.get("temperature", 0.7),
        )

        content_html = response.choices[0].message.content
        title = f"📊 今日热点速览 | {month_day} | 共 {len(items)} 篇"

        logger.info(f"Digest generated: {title}")

        return {
            "title": title,
            "content_html": content_html,
            "item_count": len(items),
            "date": date_str,
        }
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        return None
