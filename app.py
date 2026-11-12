"""荆州学院公开资讯 AI 助手 Web 服务。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request

import assistant_core


BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


def get_news_meta() -> Dict[str, Any]:
    """读取页面展示所需的新闻库统计，只执行 SELECT 查询。"""
    if not assistant_core.DB_PATH.exists():
        return {"count": 0, "latest_date": "暂无数据", "ready": False}

    with sqlite3.connect(assistant_core.DB_PATH) as connection:
        count, latest_date = connection.execute(
            "SELECT COUNT(*), MAX(publish_date) FROM public_news"
        ).fetchone()
    return {
        "count": count or 0,
        "latest_date": latest_date or "暂无数据",
        "ready": bool(count),
    }


def normalize_history(raw_history: Any) -> List[Dict[str, str]]:
    """只保留允许的角色和字段，并限制发送给模型的历史长度。"""
    if not isinstance(raw_history, list):
        raise ValueError("对话历史格式不正确")

    history: List[Dict[str, str]] = []
    for item in raw_history[-12:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            history.append({"role": role, "content": content[:4000]})

    if not history or history[-1]["role"] != "user":
        raise ValueError("请先输入问题")
    return history


@app.get("/")
def index() -> str:
    return render_template("index.html", meta=get_news_meta())


@app.get("/api/meta")
def api_meta():
    return jsonify(get_news_meta())


@app.get("/api/health")
def api_health():
    return jsonify(
        {
            "status": "ok",
            "api_key_configured": assistant_core.API_KEY
            != "sk-请填入你的DeepSeek_KEY",
            "database": get_news_meta(),
        }
    )


@app.post("/api/chat")
def api_chat():
    payload = request.get_json(silent=True) or {}

    if assistant_core.API_KEY == "sk-请填入你的DeepSeek_KEY":
        return jsonify({"error": "尚未配置 DeepSeek API Key。"}), 503

    meta = get_news_meta()
    if not meta["ready"]:
        return (
            jsonify({"error": "新闻数据库为空，请先运行 python fetch_news.py。"}),
            503,
        )

    try:
        history = normalize_history(payload.get("messages"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        reply, sources, tool_used = assistant_core.answer_question(history)
    except Exception:
        app.logger.exception("DeepSeek 请求失败")
        return (
            jsonify({"error": "AI 服务暂时不可用，请稍后重试。"}),
            502,
        )

    return jsonify(
        {
            "reply": reply,
            "sources": sources,
            "tool_used": tool_used,
        }
    )


if __name__ == "__main__":
    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "5000"))
    print(f"荆州学院公开资讯 AI 助手已启动：http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)
