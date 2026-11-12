# 荆州学院公开资讯 AI 助手

一个完全独立运行的校园公开资讯问答项目。项目使用 FastAPI 提供 HTTP API，
通过 LangChain 的 Tool Calling Agent 和 `AgentExecutor` 调用 DeepSeek，
不依赖 Codex、MCP 或其他外部 Agent 平台。

网页前端会检索本地 `campus.db` 中的荆州学院公开新闻，并在回答下方展示官网来源。

## 功能

- 抓取荆州学院官网首页“综合要闻”及详情页正文
- 使用 SQLite 存储公开新闻，并通过 URL 唯一约束避免重复
- LangChain `AgentExecutor` 自动决定是否调用本地新闻搜索工具
- DeepSeek `deepseek-chat` 通过 `langchain-openai` 接入
- FastAPI `/api/chat` 接口
- 允许所有 localhost / 127.0.0.1 本地端口跨域访问
- 响应式网页聊天界面与可点击的官网来源卡片

## 环境

- Python 3.11+

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 配置 API Key

不要把真实 API Key 写入源码或提交到 Git。运行前通过环境变量配置：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

也可以在项目目录创建被 Git 忽略的 `.env` 文件：

```dotenv
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

## 抓取新闻

```powershell
python fetch_news.py
```

该命令会创建或更新 `campus.db`，抓取官网“综合要闻”详情正文，并打印前两条
新闻用于验证。

## 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app_api:app --reload --host 127.0.0.1 --port 8000
```

网页地址：`http://127.0.0.1:8000`

API 文档：`http://127.0.0.1:8000/docs`

## API 示例

请求：

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "message": "荆州学院最近有什么与思政育人相关的新闻？"
}
```

响应：

```json
{
  "reply": "模型最终回答",
  "sources": [
    {
      "title": "新闻标题",
      "publish_date": "2026-11-08",
      "summary": "新闻摘要",
      "url": "https://www.jzun.edu.cn/info/159/18270.htm"
    }
  ],
  "tool_used": true,
  "framework": "LangChain AgentExecutor"
}
```

## CORS

API 允许任意 `localhost` 和 `127.0.0.1` 端口访问，方便本地 HTML、
Streamlit、Gradio、Vite 等前端调用。

## 项目结构

```text
jzxy-standalone/
├── app_api.py              FastAPI 服务入口
├── rag_agent.py            LangChain Tool Calling Agent 与 AgentExecutor
├── assistant_core.py       配置、提示词和只读新闻检索工具
├── fetch_news.py           官网新闻抓取与入库
├── campus.db               SQLite 新闻数据库
├── requirements.txt        Python 依赖
├── templates/index.html    网页模板
└── static/                 CSS 与前端 JavaScript
```

## 安全说明

- `.env`、虚拟环境和本地个人数据不会提交到 Git。
- 新闻搜索函数只执行 `SELECT` 查询。
- API Key 仅从服务端环境变量读取。

## LangChain Agent 架构

```text
网页前端
   ↓ POST /api/chat
FastAPI
   ↓
LangChain AgentExecutor
   ↓
Tool Calling Agent ──→ search_public_news
   ↓                         ↓
DeepSeek API             SQLite 新闻库
```

`rag_agent.py` 使用 `ChatOpenAI`、`@tool`、`create_tool_calling_agent`
和 `AgentExecutor`。接口会从 Agent 的中间步骤中提取命中的公开新闻，并随最终
回答一起返回给网页。
