"""RSS Feed 生成器 —— Jinja2 → RSS 2.0 XML"""
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

FEED_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = FEED_DIR.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def _to_rss_date(iso_str: str) -> str:
    """Convert ISO 8601 to RFC 2822 (RSS pubDate format)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return format_datetime(dt, usegmt=True)
    except (ValueError, TypeError):
        return format_datetime(datetime.now(timezone.utc), usegmt=True)


def _build_item(item: dict) -> dict:
    """Build a single RSS item dict from a DB row or digest."""
    platform_names = {"bilibili": "B站", "xiaohongshu": "小红书", "zhihu": "知乎"}

    if "content_html" in item:
        # This is a digest entry
        return {
            "title": item["title"],
            "link": item.get("url", ""),
            "guid": f"digest-{item.get('date', '')}",
            "pub_date": _to_rss_date(item.get("generated_at", "")),
            "description": item["content_html"],
            "author": "AI Digest Bot",
            "platform": "AI日报",
        }

    # Regular content entry
    p_name = platform_names.get(item["platform"], item["platform"])
    return {
        "title": f"[{p_name}] {item['author_name']}：{item['title']}",
        "link": item["url"],
        "guid": f"{item['platform']}-{item['content_id']}",
        "pub_date": _to_rss_date(item["published_at"]),
        "description": (
            f"<p>📱 平台：{p_name}</p>\n"
            f"<p>✍️ 作者：{item['author_name']}</p>\n"
            + (f"<p>{item['summary']}</p>" if item.get("summary") else "")
            + f'<p><a href="{item["url"]}">查看原文 →</a></p>'
        ),
        "author": item["author_name"],
        "platform": p_name,
    }


def generate_feed(config: dict, recent_items: list[dict], digest: dict | None = None, feed_url: str = "", filename: str = "feed.xml") -> Path:
    """Generate feed.xml from items and optional digest."""
    env = Environment(loader=FileSystemLoader(str(FEED_DIR)))
    template = env.get_template("template.xml")

    items = []

    # Digest as first item if available
    if digest:
        items.append(_build_item({
            "title": digest["title"],
            "url": config.get("link", ""),
            "date": digest["date"],
            "generated_at": digest.get("generated_at", datetime.now(timezone.utc).isoformat()),
            "content_html": digest["content_html"],
        }))

    # Content items
    for item in recent_items:
        items.append(_build_item(item))

    now = datetime.now(timezone.utc)
    xml_str = template.render(
        title=config.get("title", "Personal Content Digest"),
        link=config.get("link", ""),
        description=config.get("description", ""),
        language=config.get("language", "zh-CN"),
        last_build_date=format_datetime(now, usegmt=True),
        feed_url=feed_url,
        items=items,
    )

    output_path = OUTPUT_DIR / filename
    output_path.write_text(xml_str, encoding="utf-8")
    logger.info(f"Feed generated: {output_path} ({len(items)} items)")
    return output_path
