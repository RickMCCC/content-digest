"""X/Twitter English tweet translation via DeepSeek API."""
import logging
import os
import re

from openai import OpenAI

logger = logging.getLogger(__name__)


def is_mostly_english(text: str, threshold: float = 0.7) -> bool:
    """Check if text is mostly English (Latin/ASCII characters)."""
    if not text or len(text) < 30:
        return False
    # Remove URLs, @mentions, hashtags, RT prefix
    cleaned = re.sub(r"https?://\S+|@\w+|#\w+|RT\s*", "", text)
    cleaned = cleaned.strip()
    if len(cleaned) < 20:
        return False
    # Ratio of ASCII to non-space characters
    ascii_chars = sum(1 for c in cleaned if ord(c) < 128)
    total = sum(1 for c in cleaned if not c.isspace())
    if total == 0:
        return False
    return ascii_chars / total > threshold


def translate_to_chinese(text: str, config: dict) -> str | None:
    """Translate English text to Chinese using DeepSeek API. Returns None on failure."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        return None

    truncated = text[:800]  # don't send huge texts
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = client.chat.completions.create(
            model=config.get("model", "deepseek-chat"),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Translate the following English text to natural, "
                        "fluent Chinese. Output only the Chinese translation, "
                        "no explanations:\n\n" + truncated
                    ),
                }
            ],
            max_tokens=config.get("translation_max_tokens", 500),
            temperature=0.3,
        )
        result = resp.choices[0].message.content.strip()
        return result if result else None
    except Exception as e:
        logger.warning(f"[translate] Failed: {e}")
        return None
