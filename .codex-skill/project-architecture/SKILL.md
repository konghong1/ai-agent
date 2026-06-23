---
name: project-architecture
description: 理解 ai-agent 项目的完整架构设计，包括后端 FastAPI 分层、前端 React 控制台、数据库模型、API 路由、Agent 运行时。当需要新增表、新增字段、修改 API、理解数据流、或扩展功能时使用此 skill。触发词: 架构、新增表、新增字段、数据库变更、表结构、schema、model、API路由、项目结构。
---

# ai-agent 项目架构

## 技术栈

- **后端**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2
- **前端**: React 18 / Vite / lucide-react / react-markdown
- **数据库**: SQLite (默认) / MySQL 8.0+ (via DATABASE_URL 切换)
- **LLM**: LangChain Agent + OpenAI Compatible API

## 目录结构

`
app/
├── core/
│   ├── database.py    # 引擎创建 / session / init_db (多库适配)
│   └── security.py    # JWT / 密码哈希
├── models.py          # ORM 模型 (6 张表)
├── schemas.py         # Pydantic 请求/响应模型
├── api.py             # FastAPI Router (RESTful CRUD + chat)
├── agent.py           # LangChain Agent 构建 + 对话逻辑
├── services.py        # 业务逻辑 (用户/Agent 创建)
├── deps.py            # FastAPI 依赖注入 (JWT 鉴权)
├── settings.py        # 配置加载 (pydantic-settings)
├── tools.py           # LangChain tools (计算器/时间/文件)
└── cli.py             # 命令行入口
web/
├── src/
│   ├── main.jsx       # React 入口 (单页控制台)
│   ├── styles.css     # 全局样式 (多主题支持)
│   └── components/
│       ├── MessageRenderer.jsx  # 消息渲染 (Markdown + blocks)
│       ├── CardBlock.jsx        # 卡片组件
│       ├── CodeBlock.jsx        # 代码块 + 复制
│       ├── FormBlock.jsx        # 表单组件
│       ├── ImageBlock.jsx       # 图片预览
│       ├── TableBlock.jsx       # 表格渲染
│       ├── TextBlock.jsx        # 纯文本
│       ├── ChoiceButton.jsx     # 选择按钮
│       └── index.jsx            # 组件导出
├── package.json       # 前端依赖
└── vite.config.js     # Vite + proxy 配置
schema/
└── mysql_create_tables.sql   # MySQL 建表 DDL
`

## 数据库模型 (6 张表)

所有表均继承 TimestampMixin (created_at / updated_at)。

| 表名 | 对应 Model | 说明 |
|------|-----------|------|
| users | User | 用户 (email/username/password_hash/role) |
| gents | AgentConfig | Agent 配置 (model_name/system_prompt/temperature/enabled) |
| 	hreads | Thread | 会话 (user_id/agent_id/title) |
| messages | Message | 消息 (thread_id/role/content/extra[JSON]) |
| mcp_servers | McpServer | MCP Server 配置 (transport/args[JSON]/env[JSON]) |
| skills | Skill | Skill 配置 (source_type/path/enabled) |

**关系**: User 1→N Agents, User 1→N Threads, Agent 1→N Threads, Thread 1→N Messages, User 1→N McpServers, User 1→N Skills。

## API 路由

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | /auth/register | 注册 | ❌ |
| POST | /auth/login | 登录 | ❌ |
| GET | /auth/me | 当前用户 | ✅ |
| GET | /agents | Agent 列表 | ✅ |
| POST | /agents | 创建 Agent | ✅ |
| PATCH | /agents/{id} | 更新 Agent | ✅ |
| DELETE | /agents/{id} | 删除 Agent | ✅ |
| GET | /threads | 会话列表 | ✅ |
| POST | /threads | 创建会话 | ✅ |
| GET | /threads/{id}/messages | 消息列表 | ✅ |
| POST | /chat | 发送对话 | ✅ |
| GET | /mcp-servers | MCP 列表 | ✅ |
| POST | /mcp-servers | 创建 MCP | ✅ |
| PATCH | /mcp-servers/{id} | 更新 MCP | ✅ |
| DELETE | /mcp-servers/{id} | 删除 MCP | ✅ |
| POST | /mcp-servers/{id}/test | 测试 MCP | ✅ |
| GET | /skills | Skill 列表 | ✅ |
| POST | /skills | 创建 Skill | ✅ |
| PATCH | /skills/{id} | 更新 Skill | ✅ |
| DELETE | /skills/{id} | 删除 Skill | ✅ |

## 前端架构

单页 React 应用 (web/src/main.jsx)，通过 iew 状态切换四个视图：
- **chat** — 对话界面 (左侧 Agent 列表 + 中间消息流 + 底部输入框)
- **agents** — Agent 配置面板
- **mcp** — MCP Server 配置面板
- **skills** — Skill 管理面板

主题系统: data-theme 属性切换 (dark / ice / planet)，CSS 变量驱动。

## 新增表/字段的规范流程

1. **修改 pp/models.py** — 新增 SQLAlchemy ORM Model 或在现有 Model 加 mapped_column
2. **修改 pp/schemas.py** — 新增对应的 Pydantic Create/Read/Update schema
3. **修改 pp/api.py** — 新增 RESTful 路由 (CRUD)
4. **更新 schema/mysql_create_tables.sql** — 同步 MySQL DDL
5. **更新前端 web/src/main.jsx** — 新增页面/组件/API 调用
6. **运行 init_db()** — 自动建表 (首次启动时 pp/server.py startup 事件触发)

**重要**: database.py 的 init_db() 会在 Base.metadata.create_all() 时自动创建新表，无需手动迁移。
