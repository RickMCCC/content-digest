"""知乎爬虫：关注动态 API"""
import logging
from datetime import datetime, timezone, timedelta

from crawlers.base import BaseCrawler, CrawlerConfig

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))


class ZhihuCrawler(BaseCrawler):
    platform = "zhihu"

    BASE_URL = "https://www.zhihu.com"

    def __init__(self, config: CrawlerConfig, cookie: str = None):
        super().__init__(config)
        self.client.headers.update({
            "Referer": "https://www.zhihu.com/",
        })
        if cookie:
            self.client.headers["Cookie"] = cookie

    def fetch_items(self, author_id: str, author_name: str) -> list[dict]:
        """
        Fetch recent activities from a Zhihu user.
        Uses the /api/v4/members/{url_token}/activities API.
        """
        url = f"{self.BASE_URL}/api/v4/members/{author_id}/activities"
        params = {
            "limit": 20,
            "after_id": 0,
        }

        resp = self._request(url, params=params)
        data = resp.json()

        if "error" in data:
            logger.error(f"Zhihu API error for {author_name}: {data.get('error', {}).get('message')}")
            raise Exception(f"Zhihu API error: {data.get('error', {}).get('message', 'unknown')}")

        activities = data.get("data", [])
        items = []

        for act in activities[:10]:
            action = act.get("action_text", "")
            target = act.get("target", {})
            if not target:
                continue

            # Determine content type and extract info
            content_type = target.get("type", "")
            title = target.get("title", "") or target.get("excerpt", "")[:100]
            if not title:
                title = f"{action}"

            # Build URL
            tid = str(target.get("id", ""))
            if content_type == "answer":
                qid = target.get("question", {}).get("id", "")
                url_str = f"https://www.zhihu.com/question/{qid}/answer/{tid}"
            elif content_type == "article":
                url_str = f"https://zhuanlan.zhihu.com/p/{tid}"
            elif content_type == "pin":
                url_str = f"https://www.zhihu.com/pin/{tid}"
            elif content_type == "question":
                url_str = f"https://www.zhihu.com/question/{tid}"
            else:
                url_str = target.get("url", f"https://www.zhihu.com/people/{author_id}")

            # Timestamp
            created_ts = target.get("created_time", act.get("created_time", 0))
            if created_ts:
                pub_date = datetime.fromtimestamp(created_ts, tz=CN_TZ).isoformat()
            else:
                pub_date = datetime.now(CN_TZ).isoformat()

            summary = target.get("excerpt", "")[:200]

            items.append({
                "content_id": f"{content_type}-{tid}",
                "title": title,
                "url": url_str,
                "summary": summary,
                "published_at": pub_date,
            })

        return items
