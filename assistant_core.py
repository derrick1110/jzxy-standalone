"""共享配置、Agent 提示词和只读新闻检索工具。"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().with_name(".env"))

API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-请填入你的DeepSeek_KEY")
MODEL = "deepseek-chat"
DB_PATH = Path(__file__).resolve().with_name("campus.db")

SYSTEM_PROMPT = """你是“荆州学院公开资讯 AI 助手”。
你的职责是依据荆州学院官网公开新闻回答用户问题。
当用户询问学校新闻、活动、人物、会议、政策动态等可能需要公开资讯佐证的问题时，
必须先调用 search_public_news 工具，不能仅凭模型记忆编造校方信息。
工具没有找到结果时，应明确说明当前数据库中没有相关新闻，并建议用户调整关键词。
回答要准确、简洁，提到具体新闻时请给出新闻标题和发布日期。
如果问题与荆州学院公开资讯无关，可以正常回答，但要说明哪些内容不属于本地新闻库。"""


def search_public_news(keyword: str) -> str:
    """只读查询公开新闻；该函数不执行任何写操作。"""
    keyword = keyword.strip()
    if not keyword:
        return json.dumps(
            {"success": False, "message": "搜索关键词不能为空", "news": []},
            ensure_ascii=False,
        )

    if not DB_PATH.exists():
        return json.dumps(
            {
                "success": False,
                "message": "新闻数据库不存在，请先运行 python fetch_news.py",
                "news": [],
            },
            ensure_ascii=False,
        )

    pattern = f"%{keyword}%"
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT title, publish_date, content, url
            FROM public_news
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY publish_date DESC
            LIMIT 5
            """,
            (pattern, pattern),
        ).fetchall()

    news = [
        {
            "title": title,
            "publish_date": publish_date,
            "summary": content[:400] + ("……" if len(content) > 400 else ""),
            "url": url,
        }
        for title, publish_date, content, url in rows
    ]
    return json.dumps(
        {
            "success": True,
            "keyword": keyword,
            "count": len(news),
            "news": news,
        },
        ensure_ascii=False,
    )
