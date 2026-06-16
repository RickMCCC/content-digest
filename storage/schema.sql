-- 内容条目表
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,          -- bilibili / xiaohongshu / zhihu
    author_id TEXT NOT NULL,         -- 平台用户 ID
    author_name TEXT NOT NULL,       -- 用户显示名
    content_id TEXT NOT NULL,        -- 内容唯一 ID（如 B站 aid）
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT DEFAULT '',         -- 内容简介
    translation TEXT DEFAULT '',     -- 英文推文中文翻译
    published_at TEXT NOT NULL,      -- ISO 8601 时间
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, content_id)
);

-- 日报缓存表（每天一条）
CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,       -- 日期 YYYY-MM-DD
    title TEXT NOT NULL,
    content_html TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 爬虫运行日志
CREATE TABLE IF NOT EXISTS crawl_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    author_id TEXT NOT NULL,
    status TEXT NOT NULL,            -- success / error / skipped
    new_items INTEGER DEFAULT 0,
    error_msg TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_items_platform ON items(platform);
CREATE INDEX IF NOT EXISTS idx_items_author ON items(platform, author_id);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_created ON crawl_logs(created_at);
