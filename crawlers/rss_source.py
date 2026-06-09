"""RSS 源解析器 —— 从 RSSHub 等 RSS 源抓取内容"""
import hashlib
import logging
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from crawlers.base import BaseCrawler, CrawlerConfig

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

# RSS 2.0 / Atom namespaces
NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_date(text: str) -> str:
    """Parse various date formats to ISO 8601."""
    if not text:
        return datetime.now(CN_TZ).isoformat()
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CN_TZ).isoformat()
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(CN_TZ).isoformat()
        except (ValueError, TypeError):
            return datetime.now(CN_TZ).isoformat()


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def _extract_text(element, tag: str) -> str:
    """Get element text safely."""
    el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return ""


class RssSourceCrawler:
    """Fetches and parses an RSS feed source. Not a BaseCrawler subclass
    because it fetches a feed URL rather than per-author pages."""

    def __init__(self, config: CrawlerConfig):
        import httpx
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

    def fetch_feed(self, feed_url: str, platform: str, source_name: str) -> list[dict]:
        """Fetch and parse an RSS/Atom feed. Returns standardized items."""
        resp = self.client.get(feed_url)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

        # Detect feed type
        if root.tag == "rss":
            items = self._parse_rss(root, platform, source_name)
        elif root.tag.endswith("feed"):  # Atom
            items = self._parse_atom(root, platform, source_name)
        else:
            logger.warning(f"[rss] Unknown feed format for {source_name}")
            return []

        logger.info(f"[rss] {source_name}: {len(items)} items from {feed_url}")
        return items

    def _parse_rss(self, root, platform: str, source_name: str) -> list[dict]:
        """Parse RSS 2.0 feed."""
        results = []
        for item in root.iter("item"):
            try:
                title = _extract_text(item, "title")
                link = _extract_text(item, "link")
                desc = _extract_text(item, "description")
                pub_date = _extract_text(item, "pubDate")
                author = _extract_text(item, "author")

                if not title or not link:
                    continue

                content_id = hashlib.md5(link.encode()).hexdigest()[:16]
                results.append({
                    "content_id": content_id,
                    "title": title,
                    "url": link,
                    "summary": _strip_html(desc)[:200] if desc else "",
                    "published_at": _parse_date(pub_date),
                    "author_name": author or source_name,
                    "platform": platform,
                })
            except Exception as e:
                logger.debug(f"[rss] Skip item in {source_name}: {e}")
                continue
        return results

    def _parse_atom(self, root, platform: str, source_name: str) -> list[dict]:
        """Parse Atom feed."""
        results = []
        for entry in root.findall("atom:entry", NS) or root.findall("entry"):
            try:
                title_el = entry.find("atom:title", NS) or entry.find("title")
                title = title_el.text.strip() if title_el is not None and title_el.text else ""

                link_el = entry.find("atom:link", NS) or entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                # Alternate link fallback
                for l in entry.findall("atom:link", NS):
                    if l.get("rel") == "alternate" or not l.get("rel"):
                        link = l.get("href", "")
                        break
                if not link:
                    for l in entry.findall("link"):
                        if l.get("type") == "text/html":
                            link = l.get("href", "")
                            break

                summary_el = entry.find("atom:summary", NS) or entry.find("summary")
                summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

                updated_el = entry.find("atom:updated", NS) or entry.find("updated")
                pub_str = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

                author_el = entry.find("atom:author", NS) or entry.find("author")
                author = ""
                if author_el is not None:
                    name_el = author_el.find("atom:name", NS) or author_el.find("name")
                    if name_el is not None and name_el.text:
                        author = name_el.text.strip()

                if not title or not link:
                    continue

                content_id = hashlib.md5(link.encode()).hexdigest()[:16]
                results.append({
                    "content_id": content_id,
                    "title": title,
                    "url": link,
                    "summary": _strip_html(summary)[:200] if summary else "",
                    "published_at": _parse_date(pub_str),
                    "author_name": author or source_name,
                    "platform": platform,
                })
            except Exception as e:
                logger.debug(f"[rss] Skip atom entry in {source_name}: {e}")
                continue
        return results

    def close(self):
        self.client.close()
