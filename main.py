"""内容聚合 + AI 日报 主入口"""
import os
import sys
import hashlib
import logging
import yaml
from pathlib import Path

from storage.db import init_db, get_recent_items, get_today_items, insert_digest, get_item_count
from crawlers.base import CrawlerConfig
from crawlers.bilibili import BilibiliCrawler
from crawlers.zhihu import ZhihuCrawler
from crawlers.xiaohongshu import XiaohongshuCrawler
from crawlers.rss_source import RssSourceCrawler
from storage.db import insert_item, log_crawl
from digest.generator import generate_digest
from feed.generator import generate_feed, group_by_author_day

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.yaml"
HEARTBEAT_PATH = ROOT_DIR / "data" / ".last_run"

RUNNER_MODE = (
    "fallback" if os.environ.get("FALLBACK_MODE") == "1" else
    "local" if os.environ.get("LOCAL_RUNNER") == "1" else
    "cloud"
)


def load_config() -> dict:
    """Load YAML configuration."""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run():
    """Main execution flow."""
    logger.info("=" * 60)
    logger.info("Content Digest: Starting...")
    logger.info("=" * 60)

    # 1. Initialize database
    init_db()
    logger.info(f"Database initialized, current items: {get_item_count()}")

    # 2. Load config
    config = load_config()
    crawler_config = CrawlerConfig(config.get("crawler", {}))

    # 3. Crawl all platforms
    total_new = 0

    # B站
    bilibili_subs = config.get("subscriptions", {}).get("bilibili", [])
    if bilibili_subs:
        logger.info(f"[bilibili] Processing {len(bilibili_subs)} subscriptions...")
        cookie = os.environ.get("BILIBILI_COOKIE", "")
        crawler = BilibiliCrawler(crawler_config, cookie)
        try:
            for sub in bilibili_subs:
                n = crawler.process_author(sub["id"], sub["name"])
                total_new += n
        finally:
            crawler.close()

    # 知乎（仅在非 fallback 模式运行）
    zhihu_subs = config.get("subscriptions", {}).get("zhihu", [])
    if RUNNER_MODE == "fallback":
        logger.info("[zhihu] Skipped (fallback mode, local runner offline)")
    elif zhihu_subs:
        logger.info(f"[zhihu] Processing {len(zhihu_subs)} subscriptions...")
        cookie = os.environ.get("ZHIHU_COOKIE", "")
        crawler = ZhihuCrawler(crawler_config, cookie)
        try:
            for sub in zhihu_subs:
                n = crawler.process_author(sub["id"], sub["name"])
                total_new += n
        finally:
            crawler.close()

    # 小红书（仅在非 fallback 模式运行）
    xhs_subs = config.get("subscriptions", {}).get("xiaohongshu", [])
    if RUNNER_MODE == "fallback":
        logger.info("[xiaohongshu] Skipped (fallback mode, local runner offline)")
    elif xhs_subs:
        logger.info(f"[xiaohongshu] Processing {len(xhs_subs)} subscriptions...")
        cookie = os.environ.get("XIAOHONGSHU_COOKIE", "")
        crawler = XiaohongshuCrawler(crawler_config, cookie)
        try:
            for sub in xhs_subs:
                n = crawler.process_author(sub["id"], sub["name"])
                total_new += n
        finally:
            crawler.close()

    # RSS 源（仅在非 fallback 模式运行）
    rss_sources = config.get("rss_sources", [])
    if RUNNER_MODE == "fallback":
        logger.info("[rss] Skipped (fallback mode, local runner offline)")
    elif rss_sources:
        logger.info(f"[rss] Processing {len(rss_sources)} RSS sources...")
        rss_crawler = RssSourceCrawler(crawler_config)
        try:
            for src in rss_sources:
                try:
                    items = rss_crawler.fetch_feed(src["url"], src["platform"], src["name"])
                    for item in items:
                        inserted = insert_item(
                            platform=item["platform"],
                            author_id=hashlib.md5(src["url"].encode()).hexdigest()[:12],
                            author_name=item.get("author_name", src["name"]),
                            content_id=item["content_id"],
                            title=item["title"],
                            url=item["url"],
                            summary=item.get("summary", ""),
                            published_at=item["published_at"],
                        )
                        if inserted:
                            total_new += 1
                            logger.info(f"[rss] New ({src['platform']}): {item['title'][:50]}")
                    log_crawl(src["platform"], src["url"], "success", len(items), None, 0)
                except Exception as e:
                    logger.error(f"[rss] Failed for {src['name']}: {e}")
                    log_crawl(src["platform"], src["url"], "error", 0, str(e), 0)
        finally:
            rss_crawler.close()

    logger.info(f"Crawl complete: {total_new} new items found")

    # 4. Generate AI digest (only on morning run or if there are new items)
    today_items = get_today_items()
    digest = None

    # Fallback mode: 注入离线警告
    if RUNNER_MODE == "fallback":
        from datetime import datetime as dt
        now_str = dt.utcnow().strftime("%m月%d日")
        fallback_digest = {
            "title": f"⚠️ 本地 Runner 离线 | {now_str}",
            "content_html": (
                "<p style='color:#e67e22;font-weight:bold;'>"
                "⚠️ 本地 Runner 离线，今日仅包含 B站更新。"
                "小红书、知乎、RSS 源暂不可用。</p>"
                "<p style='color:#888;font-size:12px;'>"
                "请检查本地 PC 是否开机且网络正常，恢复后将自动补全。</p>"
            ),
            "item_count": len(today_items),
            "date": dt.utcnow().strftime("%Y-%m-%d"),
            "generated_at": dt.utcnow().isoformat(),
        }
        insert_digest(
            fallback_digest["date"],
            fallback_digest["title"],
            fallback_digest["content_html"],
            fallback_digest["item_count"],
        )
        digest = fallback_digest
        logger.info(f"Fallback digest saved: {fallback_digest['title']}")
    elif today_items:
        deepseek_config = config.get("deepseek", {})
        digest_data = generate_digest(today_items, deepseek_config)
        if digest_data:
            insert_digest(
                digest_data["date"],
                digest_data["title"],
                digest_data["content_html"],
                digest_data["item_count"],
            )
            digest = digest_data
            logger.info(f"Digest saved: {digest_data['title']}")
    else:
        logger.info("No items today, skipping digest generation")

    # 5. Build stream mapping and group-daily authors from config
    stream_map = {}  # {(platform, author_id): stream}
    group_author_ids = set()  # {(platform, author_id)} to group daily
    subs = config.get("subscriptions") or {}
    for platform in subs:
        for sub in subs.get(platform) or []:
            sid = sub.get("id", "")
            if sid:
                stream_map[(platform, sid)] = sub.get("stream", "tech")
                if sub.get("group_daily"):
                    group_author_ids.add((platform, sid))
    for src in config.get("rss_sources", []):
        aid = hashlib.md5(src["url"].encode()).hexdigest()[:12]
        stream_map[(src["platform"], aid)] = src.get("stream", "tech")
        if src.get("group_daily"):
            group_author_ids.add((src["platform"], aid))

    # 6. Generate RSS feeds per stream
    feed_config = config.get("feed", {})
    max_items = feed_config.get("max_items", 200)
    max_days = feed_config.get("max_days", 7)
    recent_items = get_recent_items(max_days=max_days, max_items=max_items * 2)

    github_user = os.environ.get("GITHUB_REPOSITORY_OWNER", "YOUR_USERNAME")
    github_repo = os.environ.get("GITHUB_REPOSITORY", "content-digest").split("/")[-1]
    base_url = f"https://raw.githubusercontent.com/{github_user}/{github_repo}/main/output"

    streams_config = feed_config.get("streams", {
        "tech": {"file": "feed_tech.xml", "title": "技术资讯流", "description": "AI/科技/财经"},
        "life": {"file": "feed_life.xml", "title": "生活分享流", "description": "生活/娱乐/艺术"},
    })

    for stream_key, stream_cfg in streams_config.items():
        stream_items = []
        for item in recent_items:
            item_aid = item.get("author_id", "")
            # Map DB author_name back to stream via config subscriptions
            item_stream = stream_map.get((item["platform"], item_aid))
            if item_stream is None:
                # Fallback: check RSS sources by matching author_name
                for src in config.get("rss_sources", []):
                    if item["platform"] == src["platform"] and item["author_name"] in (src["name"], item.get("author_name", "")):
                        item_stream = src.get("stream", "tech")
                        break
            if item_stream is None:
                item_stream = "tech"  # default
            if item_stream == stream_key:
                stream_items.append(item)

        # Group same-author same-day posts (X auto, others per config)
        stream_items = group_by_author_day(stream_items, author_ids=group_author_ids)

        feed_url = f"{base_url}/{stream_cfg['file']}"
        stream_feed_config = {
            "title": stream_cfg.get("title", feed_config.get("title", "")),
            "description": stream_cfg.get("description", feed_config.get("description", "")),
            "link": feed_config.get("link", ""),
            "language": feed_config.get("language", "zh-CN"),
        }
        # Only include digest in tech stream
        stream_digest = digest if stream_key == "tech" else None
        output_path = generate_feed(stream_feed_config, stream_items[:max_items], stream_digest, feed_url, filename=stream_cfg["file"])
        logger.info(f"Feed [{stream_key}] written: {output_path} ({len(stream_items[:max_items])} items)")

    # Backward-compatible combined feed
    all_feed_url = f"{base_url}/feed.xml"
    all_config = {
        "title": feed_config.get("title", "个人内容聚合日报"),
        "description": feed_config.get("description", ""),
        "link": feed_config.get("link", ""),
        "language": feed_config.get("language", "zh-CN"),
    }
    generate_feed(all_config, group_by_author_day(recent_items, author_ids=group_author_ids)[:max_items], digest, all_feed_url, filename="feed.xml")
    logger.info(f"Feed [combined] written for backward compatibility")

    # 7. Write heartbeat for local runner
    if RUNNER_MODE == "local":
        from datetime import datetime as dt
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_PATH.write_text(dt.utcnow().isoformat())
        logger.info(f"Heartbeat written: {HEARTBEAT_PATH}")

    logger.info("=" * 60)
    logger.info(f"Done! [{RUNNER_MODE}] {total_new} new")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
