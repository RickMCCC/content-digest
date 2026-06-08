"""Prompt templates for DeepSeek digest generation."""

SYSTEM_PROMPT = """你是内容摘要助手。你的任务是从关注创作者发布的新内容中生成一份精炼、有用的中文日报。

要求：
- 使用中文
- 精炼、直接、不过度修饰
- 不超过 800 字
- 使用 HTML 格式化输出（适合 RSS 阅读器渲染）
- 不要编造信息，仅基于提供的内容列表"""

DAILY_DIGEST_PROMPT = """以下是今天关注的创作者发布的新内容。请生成中文日报，格式如下：

<h2>📊 今日概览</h2>
<p>共 {total} 条新内容，其中{platform_dist}</p>

<h2>⭐ TOP 5 推荐</h2>
<ol>
  <li><strong>标题</strong>（{platform} · 作者）— 推荐理由一句话</li>
  ...
</ol>

<h2>📁 分类速览</h2>
<h3>B站</h3>
<ul>
  <li><strong>标题</strong>（作者）— 一句话概括</li>
  ...
</ul>

<h3>知乎</h3>
<ul>
  <li><strong>标题</strong>（作者）— 一句话概括</li>
  ...
</ul>

<h3>小红书</h3>
<ul>
  <li><strong>标题</strong>（作者）— 一句话概括</li>
  ...
</ul>

<p style="color:#888;font-size:12px;">🤖 本日报由 DeepSeek 自动生成</p>

以下是今天的内容列表：

{items_text}"""


def build_digest_prompt(items: list[dict]) -> str:
    """Build the digest prompt from content items."""
    from collections import Counter
    platforms = Counter(item["platform"] for item in items)
    platform_parts = []
    for p, c in platforms.items():
        name_map = {"bilibili": "B站", "zhihu": "知乎", "xiaohongshu": "小红书"}
        platform_parts.append(f"{name_map.get(p, p)} {c} 条")
    platform_dist = "、".join(platform_parts)

    items_text_parts = []
    for i, item in enumerate(items, 1):
        p_name = {"bilibili": "B站", "zhihu": "知乎", "xiaohongshu": "小红书"}.get(item["platform"], item["platform"])
        items_text_parts.append(
            f"{i}. [{p_name}] {item['title']}（作者：{item['author_name']}）\n"
            f"   链接：{item['url']}\n"
            f"   简介：{item.get('summary', '暂无简介')}"
        )

    items_text = "\n\n".join(items_text_parts)

    return DAILY_DIGEST_PROMPT.format(
        total=len(items),
        platform_dist=platform_dist,
        items_text=items_text,
    )
