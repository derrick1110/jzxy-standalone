"""荆州学院公开资讯 AI 助手：终端对话 + DeepSeek Function Calling。"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from openai import OpenAI


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


load_dotenv(Path(__file__).resolve().with_name(".env"))
API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-请填入你的DeepSeek_KEY")
MODEL = "deepseek-chat"
DB_PATH = Path(__file__).resolve().with_name("campus.db")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

SYSTEM_PROMPT = """你是“荆州学院公开资讯 AI 助手”。
你的职责是依据荆州学院官网公开新闻回答用户问题。
当用户询问学校新闻、活动、人物、会议、政策动态等可能需要公开资讯佐证的问题时，
必须先调用 search_public_news 工具，不能仅凭模型记忆编造校方信息。
工具没有找到结果时，应明确说明当前数据库中没有相关新闻，并建议用户调整关键词。
回答要准确、简洁，提到具体新闻时请给出新闻标题和发布日期。
如果问题与荆州学院公开资讯无关，可以正常回答，但要说明哪些内容不属于本地新闻库。"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_public_news",
            "description": (
                "在荆州学院公开新闻数据库中按关键词搜索。会同时匹配新闻标题和正文，"
                "返回最多 5 条新闻的标题、发布日期和正文摘要。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "要搜索的关键词，例如“招聘”“思政育人”“产教融合”。"
                        ),
                    }
                },
                "required": ["keyword"],
                "additionalProperties": False,
            },
        },
    }
]


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


def run_tool_calls(assistant_message: Any) -> List[Dict[str, Any]]:
    """在 Python 端执行模型请求的工具，并生成 role=tool 消息。"""
    tool_messages: List[Dict[str, Any]] = []
    for tool_call in assistant_message.tool_calls or []:
        if tool_call.function.name != "search_public_news":
            result = json.dumps(
                {"success": False, "message": "未知工具"},
                ensure_ascii=False,
            )
        else:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                keyword = arguments.get("keyword", "")
                result = search_public_news(str(keyword))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                result = json.dumps(
                    {"success": False, "message": f"工具参数错误：{exc}"},
                    ensure_ascii=False,
                )

        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": result,
            }
        )
    return tool_messages


def answer_question(
    history: List[Dict[str, str]],
) -> Tuple[str, List[Dict[str, str]], bool]:
    """执行网页问答，并返回回答、命中的新闻来源和工具调用状态。"""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
    ]
    sources: List[Dict[str, str]] = []
    seen_sources = set()
    tool_used = False

    for _ in range(5):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_message = response.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))

        if not assistant_message.tool_calls:
            return (
                assistant_message.content or "模型未返回文字回答。",
                sources,
                tool_used,
            )

        tool_used = True
        tool_messages = run_tool_calls(assistant_message)
        messages.extend(tool_messages)

        for tool_message in tool_messages:
            try:
                payload = json.loads(tool_message["content"])
            except (json.JSONDecodeError, TypeError):
                continue
            for item in payload.get("news", []):
                source_key = item.get("url") or (
                    item.get("title", ""),
                    item.get("publish_date", ""),
                )
                if source_key and source_key not in seen_sources:
                    seen_sources.add(source_key)
                    sources.append(item)

    return "工具调用次数过多，未能生成最终回答。请换一种问法重试。", sources, tool_used
