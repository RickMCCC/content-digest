"""SQLite storage layer with dedup logic."""
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "content.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database schema from schema.sql."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    conn = get_connection()
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def insert_item(
    platform: str,
    author_id: str,
    author_name: str,
    content_id: str,
    title: str,
    url: str,
    summary: str = "",
    published_at: str = None,
) -> bool:
    """Insert a new content item. Returns True if inserted, False if duplicate."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO items
               (platform, author_id, author_name, content_id, title, url, summary, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (platform, author_id, author_name, content_id, title, url, summary, published_at),
        )
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_recent_items(max_days: int = 7, max_items: int = 200) -> list[dict]:
    """Get recent items for feed generation."""
    conn = get_connection()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=max_days)).isoformat()
        rows = conn.execute(
            """SELECT * FROM items
               WHERE published_at >= ?
               ORDER BY published_at DESC
               LIMIT ?""",
            (cutoff, max_items),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_today_items() -> list[dict]:
    """Get items published today for digest generation."""
    conn = get_connection()
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT * FROM items
               WHERE date(published_at) = ?
               ORDER BY published_at DESC""",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_digest(date: str, title: str, content_html: str, item_count: int) -> bool:
    """Insert or replace daily digest."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO digests (date, title, content_html, item_count, generated_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (date, title, content_html, item_count),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_latest_digest() -> dict | None:
    """Get the most recent digest."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM digests ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def log_crawl(platform: str, author_id: str, status: str, new_items: int = 0, error_msg: str = None, duration_ms: int = None):
    """Record crawl attempt in log."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO crawl_logs (platform, author_id, status, new_items, error_msg, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (platform, author_id, status, new_items, error_msg, duration_ms),
        )
        conn.commit()
    finally:
        conn.close()


def get_item_count() -> int:
    """Get total item count."""
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    finally:
        conn.close()
