"""荆州学院公开资讯 AI 助手：FastAPI + LangChain AgentExecutor。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

import assistant_core
import rag_agent


BASE_DIR = Path(__file__).resolve().parent
PLACEHOLDER_KEY = "sk-请填入你的DeepSeek_KEY"

app = FastAPI(
    title="荆州学院公开资讯 AI 助手 API",
    description="基于 LangChain AgentExecutor、DeepSeek 和本地公开新闻库的问答接口。",
    version="2.0.0",
)

# 允许任意 localhost / 127.0.0.1 端口访问，包括本地开发服务器。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message 不能为空")
        return value


class NewsSource(BaseModel):
    title: str
    publish_date: str
    summary: str
    url: str


class ChatResponse(BaseModel):
    reply: str
    sources: List[NewsSource] = Field(default_factory=list)
    tool_used: bool = False
    framework: str = "LangChain AgentExecutor"


def get_news_meta() -> dict:
    """读取网页展示所需新闻统计，只执行 SELECT 查询。"""
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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """返回网页，保留单服务部署能力。"""
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def api_meta() -> dict:
    return get_news_meta()


@app.get("/api/health")
def api_health() -> dict:
    return {
        "status": "ok",
        "api_key_configured": assistant_core.API_KEY != PLACEHOLDER_KEY,
        "database": get_news_meta(),
        "agent_framework": "LangChain AgentExecutor",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(payload: ChatRequest) -> ChatResponse:
    if assistant_core.API_KEY == PLACEHOLDER_KEY:
        raise HTTPException(status_code=503, detail="尚未配置 DeepSeek API Key。")

    meta = get_news_meta()
    if not meta["ready"]:
        raise HTTPException(
            status_code=503,
            detail="新闻数据库为空，请先运行 python fetch_news.py。",
        )

    try:
        result = await run_in_threadpool(rag_agent.chat, payload.message)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="AI 服务暂时不可用，请稍后重试。",
        ) from exc

    return ChatResponse(
        reply=result["reply"],
        sources=result["sources"],
        tool_used=result["tool_used"],
    )
