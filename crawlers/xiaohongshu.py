"""小红书爬虫：Web Cookie 方式 (与 RSSHub 同款方案)"""
import logging
from datetime import datetime, timezone, timedelta

from crawlers.base import BaseCrawler, CrawlerConfig

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))


class XiaohongshuCrawler(BaseCrawler):
    platform = "xiaohongshu"

    def __init__(self, config: CrawlerConfig, cookie: str = None):
        super().__init__(config)
        self.client.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.xiaohongshu.com",
            "Origin": "https://www.xiaohongshu.com",
        })
        if cookie:
            self.client.headers["Cookie"] = cookie

    def fetch_items(self, author_id: str, author_name: str) -> list[dict]:
        """Fetch user's notes via web API with Cookie."""
        # Web API endpoint (same as RSSHub uses)
        url = "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted"
        params = {
            "user_id": author_id,
            "num": 30,
            "cursor": "",
        }

        resp = self._request(url, params=params)
        data = resp.json()

        if not data.get("success"):
            raise Exception(f"API error: {data.get('msg', 'unknown')}")

        notes = data.get("data", {}).get("notes", [])
        if not notes:
            logger.warning(f"[xiaohongshu] No notes found for {author_name}")
            return []

        items = []
        for note in notes[:10]:
            note_id = note.get("note_id", "")
            title = note.get("display_title", note.get("title", ""))
            desc = note.get("desc", "")

            items.append({
                "content_id": note_id,
                "title": title or f"小红书笔记 {note_id[:8]}",
                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                "summary": desc[:200] if desc else "",
                "published_at": _parse_time(note.get("time", 0)),
            })

        logger.debug(f"[xiaohongshu] Fetched {len(items)} notes for {author_name}")
        return items


def _parse_time(ts: int) -> str:
    """Parse timestamp (milliseconds) to ISO 8601."""
    if ts:
        return datetime.fromtimestamp(ts / 1000, tz=CN_TZ).isoformat()
    return datetime.now(CN_TZ).isoformat()
