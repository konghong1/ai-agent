# 后端卡顿 & API 代理错误修复

## 问题现象

1. **ECONNREFUSED 127.0.0.1:8010** — Vite 代理连不上后端
2. **页面数据加载不出来** — 后端无法响应 API 请求
3. **聊天时后端非常卡，视频生成后更卡** — 服务器响应越来越慢直至卡死

## 根因分析

### 核心问题：asyncio 事件循环被同步调用阻塞

`chat_stream` 端点返回 `StreamingResponse`，内部的 `event_generator` 是 `async def`，
运行在 asyncio 事件循环中。但它**直接调用了三个同步阻塞函数**：

| 调用位置 | 同步函数 | 阻塞原因 | 阻塞时长 |
|---------|---------|---------|---------|
| api.py:431 | `_handle_video_generation()` | `requests.post` (timeout=30s) | 最多 30 秒 |
| api.py:435 | `_handle_image_generation()` | `requests.post` (timeout=120s) | 最多 120 秒 |
| api.py:489 | `ask_agent()` | `llm.invoke()` 网络 + RAG 检索 | 5~60 秒 |

在 `async def` 中直接调用同步函数 = **冻结整个事件循环**。
期间服务器无法接受新连接、无法处理其他请求、SSE 心跳停止 → 表现为"卡死"和 ECONNREFUSED。

### 次要问题

| 问题 | 影响 |
|------|------|
| 日志级别 = DEBUG（api.py + agent.py 的 openai/httpx） | 每次请求产生海量日志，I/O 开销巨大 |
| .env PORT=8000，实际运行 8010 | 配置不一致，容易混淆 |
| LANGSMITH_TRACING=true 但 API key 是占位符 | 每次 LLM 调用尝试上传 trace 失败，增加延迟 |

## 修复内容

### 1. 用 `asyncio.to_thread()` 包装同步调用（核心修复）

```python
# 修复前 — 直接在 async 函数中调用同步函数，阻塞事件循环
answer, thread_id, blocks = ask_agent(db=temp_db, ...)

# 修复后 — 在线程池中执行，不阻塞事件循环
answer, thread_id, blocks = await asyncio.to_thread(ask_agent, db=temp_db, ...)
```

三处调用全部修复：`_handle_video_generation`、`_handle_image_generation`、`ask_agent`

### 2. 降低日志级别

- `api.py`: `logging.DEBUG` → `logging.INFO`
- `agent.py`: openai/httpx `logging.DEBUG` → `logging.WARNING`

### 3. 统一端口配置

- `.env` / `.env.example`: `PORT=8000` → `PORT=8010`

### 4. 禁用无效的 LangSmith tracing

- `.env`: `LANGSMITH_TRACING=true` → `false`（API key 是占位符）

## 修改文件清单

| 文件 | 修改 |
|------|------|
| `app/api.py` | 3 处 asyncio.to_thread 包装 + 日志级别 INFO |
| `app/agent.py` | openai/httpx 日志级别 WARNING |
| `.env` | PORT=8010 + LANGSMITH_TRACING=false |
| `.env.example` | PORT=8010 |

## 部署步骤

**必须重启后端**让所有修改生效（`.env` 变更需要重启进程）：

```bash
# 停止当前后端，然后重新启动
uvicorn app.server:app --reload --host 127.0.0.1 --port 8010
```

前端无需改动，Vite 会自动检测到后端恢复。
