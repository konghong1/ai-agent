# Local LangChain AI Agent

一个可本地启动调试的 LangChain Agent 示例，支持：

- LangChain tool-calling agent
- LangSmith trace 调试
- FastAPI HTTP 接口
- React 可视化聊天界面
- CLI 交互
- 内置工具：计算器、当前时间、工作区文件列表、读取工作区文本文件

## 1. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写：

```env
OPENAI_API_KEY=your-nvidia-nim-api-key
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_MODEL=moonshotai/kimi-k2.6

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=local-langchain-agent
```

## 3. 启动后端 API

```powershell
uvicorn app.server:app --reload --host 127.0.0.1 --port 8010
```

访问：

- 健康检查：http://127.0.0.1:8010/health
- Agent 调用：`POST http://127.0.0.1:8010/chat`

## 4. 启动 React 前端

```powershell
cd web
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

前端会通过 Vite proxy 调用后端 `/chat`，聊天调用会继续写入 LangSmith。

## 5. CLI 调试

```powershell
python -m app.cli "列出当前工作区文件，并计算 23*19"
```

或进入交互：

```powershell
python -m app.cli
```

## 6. 工具扩展

在 `app/tools.py` 里新增 `@tool` 函数，然后把它加入 `get_tools()` 返回列表即可。

相关官方文档：

- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- LangSmith tracing: https://docs.langchain.com/langsmith/trace-with-langchain
