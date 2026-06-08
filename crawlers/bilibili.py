"""B站爬虫：WBI 签名 API"""
import hashlib
import time
import urllib.parse
import logging
from datetime import datetime, timezone, timedelta

from crawlers.base import BaseCrawler, CrawlerConfig

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    """Reorder concatenated keys using MIXIN_KEY_ENC_TAB, keep first 32 chars."""
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """Add wts timestamp and compute w_rid signature."""
    mixin_key = _get_mixin_key(img_key, sub_key)
    params["wts"] = int(time.time())
    sorted_params = dict(sorted(params.items()))
    encoded = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
    for ch in "!'()*":
        encoded = encoded.replace(ch, "")
    w_rid = hashlib.md5((encoded + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


class BilibiliCrawler(BaseCrawler):
    platform = "bilibili"

    BASE_URL = "https://api.bilibili.com"

    def __init__(self, config: CrawlerConfig, cookie: str = None):
        super().__init__(config)
        self.client.headers.update({
            "Referer": "https://www.bilibili.com",
        })
        if cookie:
            self.client.headers["Cookie"] = cookie
        self._img_key = ""
        self._sub_key = ""
        self._session_ready = False

    def _ensure_session(self):
        """Visit B站 homepage to get buvid3 cookie for better API access."""
        try:
            self._request("https://www.bilibili.com")
            self._session_ready = True
            logger.debug("[bilibili] Session initialized with homepage cookies")
        except Exception as e:
            logger.debug(f"[bilibili] Session init failed (non-fatal): {e}")

    def _fetch_wbi_keys(self):
        """Fetch fresh WBI keys from B站 nav endpoint."""
        try:
            nav = self._request(f"{self.BASE_URL}/x/web-interface/nav").json()["data"]
            wbi_img = nav["wbi_img"]
            self._img_key = wbi_img["img_url"].rsplit("/", 1)[-1].split(".")[0]
            self._sub_key = wbi_img["sub_url"].rsplit("/", 1)[-1].split(".")[0]
            logger.debug(f"[bilibili] WBI keys fetched")
        except Exception as e:
            logger.warning(f"[bilibili] Failed to fetch WBI keys: {e}")

    def fetch_items(self, author_id: str, author_name: str) -> list[dict]:
        """Fetch UP main's video list via WBI-signed API."""
        if not self._session_ready:
            self._ensure_session()
        if not self._img_key or not self._sub_key:
            self._fetch_wbi_keys()

        params = {"mid": author_id, "ps": 30, "pn": 1, "order": "pubdate"}
        params = _enc_wbi(params, self._img_key, self._sub_key)

        url = f"{self.BASE_URL}/x/space/wbi/arc/search"
        resp = self._request(url, params=params)
        data = resp.json()

        if data.get("code") != 0:
            # Try refreshing WBI keys and retry once
            self._fetch_wbi_keys()
            params = {"mid": author_id, "ps": 30, "pn": 1, "order": "pubdate"}
            params = _enc_wbi(params, self._img_key, self._sub_key)
            resp = self._request(url, params=params)
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"B站 API error: {data.get('message', 'unknown')}")

        vlist = data.get("data", {}).get("list", {}).get("vlist", [])
        if not vlist:
            return []

        items = []
        for v in vlist[:10]:
            pub_ts = v.get("created", v.get("pubdate", 0))
            pub_date = datetime.fromtimestamp(pub_ts, tz=CN_TZ).isoformat()
            items.append({
                "content_id": str(v.get("aid", v.get("bvid", ""))),
                "title": v.get("title", ""),
                "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
                "summary": v.get("description", "")[:200],
                "published_at": pub_date,
            })

        logger.debug(f"[bilibili] Fetched {len(items)} videos for {author_name}")
        return items
