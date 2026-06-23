# Configurable AI Agent Platform

一个本地可运行的 AI Agent 项目骨架，包含：

- 用户注册 / 登录
- JWT 鉴权
- Agent 配置管理
- 会话与消息持久化
- 内置 LangChain tools
- MCP Server 配置管理骨架
- Skill 配置管理骨架
- React 控制台
- LangSmith trace

## 1. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. 配置环境变量

复制 `.env.example` 为 `.env`，然后填写模型服务配置：

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=ai-agent-platform

DATABASE_URL=sqlite:///D:/workspace/ai-agent/agent.db
SECRET_KEY=replace-with-a-long-random-secret
```

注意：`.env` 里的注释请使用 `#`，不要使用 `;`。

## 3. 启动后端

```powershell
uvicorn app.server:app --reload --host 127.0.0.1 --port 8010
```

可访问：

- 健康检查：http://127.0.0.1:8010/health
- API 文档：http://127.0.0.1:8010/docs

首次启动会自动创建 SQLite 数据库。

## 4. 启动前端

```powershell
cd web
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 5. 当前功能范围

已经实现：

- 注册 / 登录 / 当前用户接口
- 默认 Agent 自动创建
- Agent 创建和配置
- 会话创建、列表、消息读取
- 登录后聊天
- MCP Server 配置保存和基础校验
- Skill 配置保存

下一步建议实现：

- MCP runtime 连接和 tool 适配
- Skill prompt 注入和 skill tools 加载
- Tool 调用前确认
- Agent 与 MCP/Skill 的绑定表
- Alembic 数据库迁移
- Docker Compose 部署
