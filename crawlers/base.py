"""Base crawler with retry, rate limiting, and logging."""
import time
import random
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta

import httpx

from storage.db import insert_item, log_crawl

logger = logging.getLogger(__name__)

# 北京时间时区
CN_TZ = timezone(timedelta(hours=8))


class CrawlerConfig:
    def __init__(self, config: dict):
        self.min_interval = config.get("min_interval", 5)
        self.max_interval = config.get("max_interval", 15)
        self.max_retries = config.get("max_retries", 3)
        self.timeout = config.get("timeout", 30)


class BaseCrawler(ABC):
    """Abstract base crawler with rate limiting and error handling."""

    platform: str = ""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.client = httpx.Client(
            timeout=config.timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
            follow_redirects=True,
        )

    def _rate_limit(self):
        """Random delay between requests to avoid detection."""
        delay = random.uniform(self.config.min_interval, self.config.max_interval)
        logger.debug(f"[{self.platform}] Rate limit: sleeping {delay:.1f}s")
        time.sleep(delay)

    def _request(self, url: str, **kwargs) -> httpx.Response:
        """Make HTTP request with retry logic."""
        last_exc = None
        for attempt in range(self.config.max_retries):
            try:
                resp = self.client.get(url, **kwargs)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"[{self.platform}] Rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                last_exc = e
                logger.warning(f"[{self.platform}] HTTP error (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)
            except httpx.RequestError as e:
                last_exc = e
                logger.warning(f"[{self.platform}] Request error (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)
        raise last_exc

    def process_author(self, author_id: str, author_name: str) -> int:
        """Crawl an author and save new items. Returns count of new items."""
        start = time.time()
        new_count = 0
        error_msg = None
        try:
            self._rate_limit()
            items = self.fetch_items(author_id, author_name)
            for item in items:
                inserted = insert_item(
                    platform=self.platform,
                    author_id=author_id,
                    author_name=author_name,
                    content_id=item["content_id"],
                    title=item["title"],
                    url=item["url"],
                    summary=item.get("summary", ""),
                    published_at=item["published_at"],
                )
                if inserted:
                    new_count += 1
                    logger.info(f"[{self.platform}] New: {item['title'][:50]}")
            status = "success"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{self.platform}] Failed for {author_name}: {e}")
            status = "error"
        elapsed = int((time.time() - start) * 1000)
        log_crawl(self.platform, author_id, status, new_count, error_msg, elapsed)
        return new_count

    @abstractmethod
    def fetch_items(self, author_id: str, author_name: str) -> list[dict]:
        """
        Fetch items for an author. Returns list of dicts with:
        - content_id: str (unique platform ID)
        - title: str
        - url: str
        - summary: str
        - published_at: str (ISO 8601)
        """
        ...

    def close(self):
        self.client.close()
