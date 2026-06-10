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
from feed.generator import generate_feed

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.yaml"


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

    # 知乎
    zhihu_subs = config.get("subscriptions", {}).get("zhihu", [])
    if zhihu_subs:
        logger.info(f"[zhihu] Processing {len(zhihu_subs)} subscriptions...")
        cookie = os.environ.get("ZHIHU_COOKIE", "")
        crawler = ZhihuCrawler(crawler_config, cookie)
        try:
            for sub in zhihu_subs:
                n = crawler.process_author(sub["id"], sub["name"])
                total_new += n
        finally:
            crawler.close()

    # 小红书
    xhs_subs = config.get("subscriptions", {}).get("xiaohongshu", [])
    if xhs_subs:
        logger.info(f"[xiaohongshu] Processing {len(xhs_subs)} subscriptions...")
        cookie = os.environ.get("XIAOHONGSHU_COOKIE", "")
        crawler = XiaohongshuCrawler(crawler_config, cookie)
        try:
            for sub in xhs_subs:
                n = crawler.process_author(sub["id"], sub["name"])
                total_new += n
        finally:
            crawler.close()

    # RSS 源（如 RSSHub）
    rss_sources = config.get("rss_sources", [])
    if rss_sources:
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
    if today_items:
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

    # 5. Generate RSS feed
    feed_config = config.get("feed", {})
    max_items = feed_config.get("max_items", 200)
    max_days = feed_config.get("max_days", 7)
    recent_items = get_recent_items(max_days=max_days, max_items=max_items)

    # Feed URL (user should update this with their actual GitHub username/repo)
    github_user = os.environ.get("GITHUB_REPOSITORY_OWNER", "YOUR_USERNAME")
    github_repo = os.environ.get("GITHUB_REPOSITORY", "content-digest").split("/")[-1]
    feed_url = f"https://raw.githubusercontent.com/{github_user}/{github_repo}/main/output/feed.xml"

    output_path = generate_feed(feed_config, recent_items, digest, feed_url)
    logger.info(f"Feed written to: {output_path}")

    logger.info("=" * 60)
    logger.info(f"Done! {total_new} new, {len(recent_items)} in feed")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
