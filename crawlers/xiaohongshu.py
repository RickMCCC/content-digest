"""小红书爬虫：移动端 API 优先 + Playwright 备选"""
import os
import logging
from datetime import datetime, timezone, timedelta

from crawlers.base import BaseCrawler, CrawlerConfig

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))


class XiaohongshuCrawler(BaseCrawler):
    platform = "xiaohongshu"

    API_BASE = "https://edith.xiaohongshu.com"

    def __init__(self, config: CrawlerConfig, token: str = None, use_playwright: bool = False, api_fail_threshold: int = 3):
        super().__init__(config)
        self.token = token
        self.use_playwright = use_playwright
        self.api_fail_threshold = api_fail_threshold
        self._api_fail_count = 0

        # Set mobile API headers
        self.client.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Mobile/15E148"
            ),
            "X-S": "0",
            "X-T": "",
        })
        if token:
            self.client.headers["x-mini-token"] = token

    def fetch_items(self, author_id: str, author_name: str) -> list[dict]:
        """
        Fetch user's notes via mobile API.
        Falls back to Playwright if API fails repeatedly.
        """
        if self.use_playwright or self._api_fail_count >= self.api_fail_threshold:
            return self._fetch_playwright(author_id, author_name)

        try:
            return self._fetch_api(author_id, author_name)
        except Exception as e:
            self._api_fail_count += 1
            logger.warning(
                f"[小红书] API failed for {author_name} "
                f"(fail count: {self._api_fail_count}/{self.api_fail_threshold}): {e}"
            )
            if self._api_fail_count >= self.api_fail_threshold:
                logger.warning("[小红书] Switching to Playwright fallback")
                return self._fetch_playwright(author_id, author_name)
            raise

    def _fetch_api(self, author_id: str, author_name: str) -> list[dict]:
        """Fetch user notes via mobile API."""
        url = f"{self.API_BASE}/api/sns/web/v1/user/notes"
        params = {
            "user_id": author_id,
            "page_size": 20,
            "page": 1,
            "sort": "time",
        }

        resp = self._request(url, params=params)
        data = resp.json()

        if not data.get("success"):
            raise Exception(f"API error: {data.get('msg', 'unknown')}")

        notes = data.get("data", {}).get("notes", [])
        items = []

        for note in notes[:10]:
            note_id = note.get("note_id", "")
            title = note.get("display_title", note.get("title", ""))
            note_type = note.get("type", "normal")

            url_str = f"https://www.xiaohongshu.com/explore/{note_id}"
            summary = note.get("desc", "")[:200]

            pub_ts = note.get("time", 0)
            if pub_ts:
                pub_date = datetime.fromtimestamp(pub_ts / 1000, tz=CN_TZ).isoformat()
            else:
                pub_date = datetime.now(CN_TZ).isoformat()

            items.append({
                "content_id": note_id,
                "title": title or f"小红书笔记 {note_id[:8]}",
                "url": url_str,
                "summary": summary,
                "published_at": pub_date,
            })

        return items

    def _fetch_playwright(self, author_id: str, author_name: str) -> list[dict]:
        """
        Playwright-based fallback for when API fails.
        Opens the user's page and extracts note data.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed, cannot fallback")
            raise Exception("Playwright not installed")

        logger.info(f"[小红书] Using Playwright for {author_name}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
                ),
                viewport={"width": 390, "height": 844},
            )

            page = context.new_page()
            user_url = f"https://www.xiaohongshu.com/user/profile/{author_id}"
            page.goto(user_url, wait_until="networkidle", timeout=30000)

            # Wait for note cards to appear
            try:
                page.wait_for_selector("[class*='note-item'], .note-item, .card", timeout=15000)
            except Exception:
                logger.warning(f"[小红书] Playwright: no notes found for {author_name}")
                browser.close()
                return []

            # Extract note data from page
            notes = page.evaluate("""() => {
                const items = [];
                // Try multiple selectors
                const cards = document.querySelectorAll('[class*="note-item"], .note-item, .feeds-page .note-item');
                cards.forEach((card, i) => {
                    if (i >= 10) return;
                    const link = card.querySelector('a[href*="/explore/"]');
                    const titleEl = card.querySelector('.title, [class*="title"]');
                    const descEl = card.querySelector('.desc, [class*="desc"]');
                    if (link) {
                        const href = link.getAttribute('href') || '';
                        const match = href.match(/\\/explore\\/([a-zA-Z0-9]+)/);
                        items.push({
                            note_id: match ? match[1] : '',
                            title: titleEl ? titleEl.textContent.trim() : '',
                            desc: descEl ? descEl.textContent.trim() : '',
                        });
                    }
                });
                return items;
            }""")

            browser.close()

            items = []
            for note in notes:
                if not note.get("note_id"):
                    continue
                items.append({
                    "content_id": note["note_id"],
                    "title": note.get("title", f"小红书笔记 {note['note_id'][:8]}"),
                    "url": f"https://www.xiaohongshu.com/explore/{note['note_id']}",
                    "summary": note.get("desc", "")[:200],
                    "published_at": datetime.now(CN_TZ).isoformat(),
                })

            return items
