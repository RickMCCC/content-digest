"""RSS Feed 生成器 —— Jinja2 → RSS 2.0 XML"""
import hashlib
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
    platform_names = {"bilibili": "B站", "xiaohongshu": "小红书", "zhihu": "知乎", "x": "X"}

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

    if item.get("_grouped"):
        # Pre-built grouped item (same-author same-day merge)
        p_name = platform_names.get(item["platform"], item["platform"])
        date_str = item["published_at"][:10]
        count = item.get("_group_count", 0)
        return {
            "title": f"[{p_name}] {item['author_name']} ({date_str}): {count} posts",
            "link": item["url"],
            "guid": f"{item['platform']}-{item['content_id']}",
            "pub_date": _to_rss_date(item["published_at"]),
            "description": item.get("_group_html", ""),
            "author": item["author_name"],
            "platform": p_name,
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


def group_by_author_day(items: list[dict], platforms: set = None, author_ids: set = None) -> list[dict]:
    """Group same-author same-day items for high-volume platforms.

    Items whose platform is in *platforms* (or whose (platform, author_id)
    is in *author_ids*) are grouped by (platform, author_id, published_at date).
    Groups of 2+ are merged into a single item with a bullet-point link list.
    Single items and non-target items pass through unchanged.
    """
    if platforms is None:
        platforms = {"x"}
    if author_ids is None:
        author_ids = set()

    # Partition: items to group vs pass-through
    to_group = []
    pass_through = []
    for item in items:
        pid = item.get("platform", "")
        aid = item.get("author_id", "")
        if pid in platforms or (pid, aid) in author_ids:
            to_group.append(item)
        else:
            pass_through.append(item)

    if not to_group:
        return items

    # Group by (platform, author_id, "YYYY-MM-DD")
    groups = {}  # (platform, author_id, date) -> list of items
    for item in to_group:
        date_str = item["published_at"][:10]
        key = (item["platform"], item["author_id"], date_str)
        groups.setdefault(key, []).append(item)

    # Build merged result
    result = list(pass_through)
    for (platform, author_id, date_str), group_items in groups.items():
        if len(group_items) == 1:
            result.append(group_items[0])
        else:
            group_items.sort(key=lambda x: x["published_at"], reverse=True)
            latest = group_items[0]
            author_name = latest["author_name"]
            post_count = len(group_items)

            # Build bullet-list HTML
            li_items = []
            for it in group_items:
                li_items.append(
                    f'<li><a href="{it["url"]}">{it["title"]}</a></li>'
                )
            group_html = "<ul>\n" + "\n".join(li_items) + "\n</ul>"

            # Deterministic content_id for stable RSS GUID
            cid = (
                "grouped-"
                + date_str
                + "-"
                + hashlib.md5(author_id.encode()).hexdigest()[:8]
            )

            result.append({
                "platform": platform,
                "author_id": author_id,
                "author_name": author_name,
                "content_id": cid,
                "title": latest["title"],
                "url": latest["url"],
                "summary": latest.get("summary", ""),
                "published_at": latest["published_at"],
                "_grouped": True,
                "_group_html": group_html,
                "_group_count": post_count,
            })

    # Sort final list by published_at DESC
    result.sort(key=lambda x: x["published_at"], reverse=True)
    return result


def group_by_category(items: list[dict], category_map: dict) -> list[dict]:
    """Merge same-category same-day items across authors into one feed item.

    Items whose (platform, author_id) is in *category_map* are grouped
    by (category_name, date). Single items pass through unchanged.
    Items already grouped by author (have _group_html) are merged per-author.
    """
    if not category_map:
        return items

    # Partition: items to group vs pass-through
    to_group = []
    pass_through = []
    for item in items:
        key = (item.get("platform", ""), item.get("author_id", ""))
        if key in category_map:
            to_group.append(item)
        else:
            pass_through.append(item)

    if not to_group:
        return items

    # Group by (category_name, date)
    groups = {}  # (category, date) -> list of items
    for item in to_group:
        date_str = item["published_at"][:10]
        cat = category_map[(item["platform"], item["author_id"])]
        key = (cat, date_str)
        groups.setdefault(key, []).append(item)

    # Build merged result
    result = list(pass_through)
    for (cat, date_str), group_items in groups.items():
        if len(group_items) == 1:
            result.append(group_items[0])
            continue

        group_items.sort(key=lambda x: x["published_at"], reverse=True)
        latest = group_items[0]
        author_count = len(group_items)
        total_posts = sum(it.get("_group_count", 1) for it in group_items)

        # Build per-author sections
        author_sections = []
        for it in group_items:
            author = it["author_name"]
            if it.get("_grouped"):
                # Already grouped by author — reuse its HTML
                author_sections.append(
                    f"<h5>{author} · {it['_group_count']}条</h5>\n{it['_group_html']}"
                )
            else:
                author_sections.append(
                    f"<h5>{author}</h5>\n"
                    f'<ul><li><a href="{it["url"]}">{it["title"]}</a></li></ul>'
                )

        group_html = (
            f"<h4>{cat} · {author_count}位作者 · {total_posts}条</h4>\n"
            + "\n".join(author_sections)
        )

        cid = (
            "cat-"
            + hashlib.md5(cat.encode()).hexdigest()[:8]
            + "-"
            + date_str
        )

        result.append({
            "platform": latest["platform"],
            "author_id": hashlib.md5(cat.encode()).hexdigest()[:12],
            "author_name": cat,
            "content_id": cid,
            "title": f"[X] {cat} ({date_str}): {author_count}位作者, {total_posts}条",
            "url": latest["url"],
            "summary": "",
            "published_at": latest["published_at"],
            "_grouped": True,
            "_group_html": group_html,
            "_group_count": total_posts,
        })

    result.sort(key=lambda x: x["published_at"], reverse=True)
    return result


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
