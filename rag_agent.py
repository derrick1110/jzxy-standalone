"""LangChain Tool Calling Agent：连接 DeepSeek 与本地公开新闻检索工具。"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

import assistant_core


class NewsSearchInput(BaseModel):
    """LangChain 工具的结构化入参。"""

    keyword: str = Field(
        description="要搜索的关键词，例如“招聘”“思政育人”“产教融合”。"
    )


@tool("search_public_news", args_schema=NewsSearchInput)
def search_public_news_tool(keyword: str) -> str:
    """在荆州学院公开新闻库中搜索标题或正文，返回最多五条带官网链接的新闻。"""
    return assistant_core.search_public_news(keyword)


TOOLS = [search_public_news_tool]

LLM = ChatOpenAI(
    model=assistant_core.MODEL,
    api_key=assistant_core.API_KEY,
    base_url="https://api.deepseek.com",
    temperature=0,
    timeout=60,
    max_retries=2,
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", assistant_core.SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

AGENT = create_tool_calling_agent(LLM, TOOLS, PROMPT)

AGENT_EXECUTOR = AgentExecutor(
    agent=AGENT,
    tools=TOOLS,
    verbose=False,
    max_iterations=4,
    max_execution_time=90,
    return_intermediate_steps=True,
    handle_parsing_errors=True,
)


def _payload_from_observation(observation: Any) -> Dict[str, Any]:
    if isinstance(observation, dict):
        return observation
    if isinstance(observation, str):
        try:
            data = json.loads(observation)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _extract_sources(intermediate_steps: List[Any]) -> List[Dict[str, str]]:
    """从 AgentExecutor 的工具中间步骤中提取并去重官网来源。"""
    sources: List[Dict[str, str]] = []
    seen = set()

    for step in intermediate_steps:
        if not isinstance(step, (tuple, list)) or len(step) != 2:
            continue
        action, observation = step
        if getattr(action, "tool", None) != "search_public_news":
            continue

        payload = _payload_from_observation(observation)
        for item in payload.get("news", []):
            source_key = item.get("url") or (
                item.get("title", ""),
                item.get("publish_date", ""),
            )
            if source_key and source_key not in seen:
                seen.add(source_key)
                sources.append(
                    {
                        "title": str(item.get("title", "")),
                        "publish_date": str(item.get("publish_date", "")),
                        "summary": str(item.get("summary", "")),
                        "url": str(item.get("url", "")),
                    }
                )
    return sources


def chat(question: str) -> Dict[str, Any]:
    """运行 LangChain AgentExecutor，并返回最终回答及检索来源。"""
    result = AGENT_EXECUTOR.invoke({"input": question})
    steps = result.get("intermediate_steps") or []
    reply = result.get("output", "模型未返回文字回答。")

    return {
        "reply": str(reply),
        "sources": _extract_sources(steps),
        "tool_used": bool(steps),
    }
