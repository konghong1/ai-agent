# Configurable AI Agent Platform with Knowledge Base

一个本地可运行的 AI Agent 项目框架，包含知识库管理能力：

- 用户注册 / 登录 / JWT 认证
- Agent 配置管理（支持绑定知识库、MCP Server、Skill）
- 会话与消息持久化
- **知识库管理**（创建、文件夹树、文件上传、自动分块、向量化、语义检索）
- Agent 自动调用知识库检索工具回答问题
- MCP Server 配置管理骨架
- Skill 配置管理骨架
- 用户管理（列表、角色、启用/禁用）
- 系统设置（全局键值配置）
- React 控制面板
- LangSmith trace

## 1. 安装后端依赖

`powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
`

## 2. 配置环境变量

复制 .env.example 为 .env，然后填写模型服务配置：

`env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=ai-agent-platform

DATABASE_URL=sqlite:///agent.db
SECRET_KEY=replace-with-a-long-random-secret
`

## 3. 启动后端

`powershell
uvicorn app.server:app --reload --host 127.0.0.1 --port 8010
`

可访问：

- 健康检查：http://127.0.0.1:8010/health
- API 文档：http://127.0.0.1:8010/docs

## 4. 启动前端

`powershell
cd web
npm install
npm run dev
`

打开：http://127.0.0.1:5173

## 5. 知识库功能说明

### 文件处理流水线

1. **上传**：用户通过前端上传文件到指定文件夹
2. **文本提取**：根据文件类型自动选择解析器（PDF/DOCX/TXT/MD/Code）
3. **文本分块**：使用 RecursiveCharacterTextSplitter 按 chunk_size 切分
4. **向量化**：调用 OpenAI Embeddings 生成向量
5. **存储**：向量存入 ChromaDB，元数据存入 SQLite

### Agent 集成

Agent 内置 search_knowledge_base 工具，LLM 自主判断何时检索知识库。

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PATCH/DELETE | /knowledge-bases | 知识库 CRUD |
| POST | /knowledge-bases/{id}/folders | 创建文件夹 |
| GET | /knowledge-bases/{id}/folders/tree | 获取文件夹树 |
| POST | /knowledge-bases/{id}/upload | 上传文档（自动处理） |
| GET | /knowledge-bases/{id}/documents | 列出文档 |
| DELETE | /knowledge-bases/{id}/documents/{id} | 删除文档 |
| POST | /knowledge-bases/search | 检索知识库 |
| GET/POST/PATCH/DELETE | /users | 用户管理 |
| GET/POST/PATCH/DELETE | /settings | 系统设置 |
