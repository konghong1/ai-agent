# AI Agent 管理平台 - 产品需求文档 (PRD)

| 字段 | 内容 |
|------|------|
| 产品名称 | AI Agent 管理平台 |
| 版本 | v1.0 |
| 日期 | 2026-06-24 |
| 作者 | Agnes-2.0-Flash |
| 状态 | 草案 - 待评审 |

---

## 1. 产品概述

### 1.1 产品定位

一个本地可部署的 **AI Agent 管理平台**，集智能体管理、知识库 RAG、用户权限、系统配置于一体，提供 **3D 动感 + 冰晶色** 风格的现代化管理后台界面。

### 1.2 目标用户

| 用户角色 | 描述 | 核心诉求 |
|---------|------|---------|
| 管理员 (Admin) | 系统运维人员 | 用户管理、系统配置、Agent 全局管控 |
| 开发者 (Developer) | 技术团队 | Agent 编排、知识库维护、MCP/Skill 配置 |
| 普通用户 (User) | 业务人员 | 对话测试、知识库检索 |

### 1.3 核心价值主张

1. **一站式管理**：Agent、知识库、用户、MCP、Skill 统一后台管理
2. **工业级 RAG**：混合检索 + 重排序 + 上下文组装 + 反馈闭环
3. **极致体验**：3D 动感 + 冰晶色视觉风格，Ant Design Pro 级布局
4. **开箱即用**：本地部署，无需云服务，数据完全私有

---

## 2. 技术架构

### 2.1 整体架构

``
客户端 (浏览器)
  React 18 + Vite + Ant Design 5 + ProComponents
  Zustand 状态管理 + Framer Motion 动画 + TypeScript
       │ REST API (JSON)
       ▼
服务端 (FastAPI)
  Auth 认证模块 │ Agent 编排模块 │ KB RAG 检索模块 │ User 管理模块
  LangChain Agent + OpenAI Compatible LLM
       │              │              │
   SQLite/PostgreSQL │  ChromaDB    │  OpenAI Embed
``

### 2.2 技术栈明细

| 层级 | 技术选型 | 版本要求 | 说明 |
|------|---------|---------|------|
| 前端框架 | React | ^18.2 | 函数组件 + Hooks |
| 构建工具 | Vite | ^5.0 | 极速 HMR |
| 语言 | TypeScript | ^5.3 | 全量 TS |
| UI 组件库 | Ant Design | ^5.15 | 企业级组件 |
| Pro 组件 | @ant-design/pro-components | ^2.7 | ProLayout/ProTable/ProForm |
| 路由 | react-router-dom | ^6.22 | 菜单驱动路由 |
| 状态管理 | Zustand | ^4.5 | 轻量响应式 |
| HTTP 客户端 | axios | ^1.6 | 拦截器 + 类型定义 |
| 动画库 | framer-motion | ^10.18 | 3D 翻转/悬浮动效 |
| 图表 | echarts-for-react | ^3.0 | 仪表盘图表 |
| 后端框架 | FastAPI | ^0.111 | Python ASGI |
| ORM | SQLAlchemy | ^2.0 | 对象关系映射 |
| Agent 框架 | LangChain | ^0.2 | Agent + Tools |
| 向量数据库 | ChromaDB | ^0.5 | 本地持久化 |
| 嵌入模型 | OpenAI Embeddings | text-embedding-3-small | 兼容 API |
| 数据库 | SQLite / PostgreSQL | - | 开发用 SQLite，生产 PG |
| 认证 | JWT (HS256) | - | Bearer Token |

### 2.3 项目目录结构

`
ai-agent/
├── app/                          # 后端
│   ├── core/database.py          # 数据库引擎 + Session
│   ├── core/security.py          # JWT + 密码哈希
│   ├── models.py                 # SQLAlchemy 模型
│   ├── schemas.py                # Pydantic Schema
│   ├── services.py               # 业务逻辑 (含 RAG)
│   ├── tools.py                  # LangChain Tools
│   ├── agent.py                  # Agent 编排
│   ├── api.py                    # FastAPI 路由
│   ├── server.py                 # FastAPI 应用入口
│   └── settings.py               # 配置管理
├── web/                          # 前端
│   ├── src/
│   │   ├── assets/               # 静态资源
│   │   ├── components/           # 全局组件
│   │   │   ├── IceCrystalCard/   # 冰晶卡片 (3D 悬浮)
│   │   │   ├── GlassButton/      # 玻璃拟态按钮
│   │   │   └── ParticleBg/       # Canvas 粒子背景
│   │   ├── layouts/              # 布局
│   │   │   ├── BasicLayout.tsx   # ProLayout 主布局
│   │   │   └── LoginLayout.tsx   # 登录页布局
│   │   ├── pages/                # 页面
│   │   │   ├── Login/            # 登录/注册
│   │   │   ├── Dashboard/        # 仪表盘
│   │   │   ├── AgentList/        # Agent 目录
│   │   │   ├── AgentDetail/      # Agent 详情 + 对话测试
│   │   │   ├── KnowledgeBase/    # 知识库 (RAG 核心)
│   │   │   ├── UserManagement/   # 用户管理
│   │   │   ├── MCPManagement/    # MCP Server 管理
│   │   │   ├── SkillManagement/  # Skill 管理
│   │   │   └── Settings/         # 系统设置
│   │   ├── services/             # API 请求层
│   │   ├── stores/               # Zustand Store
│   │   ├── utils/                # 工具函数
│   │   ├── App.tsx               # 路由配置
│   │   └── main.tsx              # 入口
│   ├── package.json
│   └── vite.config.ts
├── uploads/                      # 文件上传存储
├── chroma_db/                    # ChromaDB 持久化
├── agent.db                      # SQLite 数据库
├── requirements.txt              # Python 依赖
├── .env                          # 环境变量
└── README.md
`

---

## 3. 功能需求

### 3.1 模块总览

| 模块 | 路由 | 核心功能 | 优先级 |
|------|------|---------|--------|
| 认证 | /login | 注册/登录/JWT | P0 |
| 仪表盘 | /dashboard | 数据概览/统计 | P0 |
| Agent 目录 | /agents | 列表/创建/编辑/删除/绑定 | P0 |
| Agent 详情 | /agents/:id | 配置详情/对话测试 | P0 |
| 知识库 | /knowledge-bases | 列表/创建/管理 | P0 |
| 知识库详情 | /knowledge-bases/:id | 文件夹树/文档/上传/RAG配置 | P0 |
| 用户管理 | /users | 列表/编辑/角色/启用禁用 | P1 |
| MCP 管理 | /mcp-servers | 列表/创建/编辑/测试连接 | P1 |
| Skill 管理 | /skills | 列表/创建/编辑/启用禁用 | P1 |
| 系统设置 | /settings | 全局配置/主题 | P1 |

---

### 3.2 认证模块 (/login)

#### 3.2.1 登录页

**页面布局**：
- 左侧：Canvas 冰晶粒子动画
- 右侧：登录表单卡片（玻璃拟态）

**功能点**：
- 邮箱格式校验
- 密码最少 6 位
- 登录失败显示动画抖动提示
- 登录成功存储 token + user 信息 → 跳转 /dashboard
- 底部切换"注册"链接

**API**：

| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| POST | /auth/login | {email, password} | {access_token, token_type, user} |
| POST | /auth/register | {email, username, password} | {access_token, token_type, user} |
| GET | /auth/me | Bearer Token | {id, email, username, role} |

#### 3.2.2 未认证拦截

- 所有页面路由需携带有效 JWT
- 未认证 → 自动跳转 /login
- Token 过期 → 清除本地状态 → 跳转 /login

---

### 3.3 仪表盘 (/dashboard)

#### 3.3.1 页面结构

`
┌───────────────────────────────────────────────────────┐
│  欢迎回来, Admin  👋                                   │
├───────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 🤖 12   │ │ 📚 5    │ │ 📄 156   │ │ 👥 8    │ │
│  │ Agent数  │ │ 知识库数 │ │ 文档总数  │ │ 用户数  │ │
│  │ ↑12%    │ │ ↑2      │ │ ↑23      │ │ ↑1      │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├───────────────────────────┬───────────────────────────┤
│  近7天对话趋势             │  快捷操作                  │
│  ┌─────────────────────┐  │  ┌─────────────────────┐ │
│  │  ECharts 折线图      │  │  │ ➕ 新建 Agent        │ │
│  └─────────────────────┘  │  │  📚 新建知识库        │ │
│                           │  │  👥 用户管理          │ │
├───────────────────────────┤  │  🔧 系统设置          │ │
│  最近活动 (表格)          │  └─────────────────────┘ │
└───────────────────────────┴───────────────────────────┘
`

**功能点**：
- 统计卡片使用 IceCrystalCard 组件（悬浮 3D 倾斜 + 冰蓝发光边框）
- 趋势图使用 ECharts 折线图，冰晶配色
- 快捷操作按钮使用 GlassButton（玻璃拟态）
- 最近活动从各模块数据聚合展示

---

### 3.4 Agent 目录模块 (/agents)

#### 3.4.1 Agent 列表页

使用 Ant Design ProTable，支持：
- 名称搜索（模糊匹配）
- 状态筛选（全部/启用/禁用）
- 排序（创建时间/名称）
- 分页

**列定义**：

| 列 | 类型 | 宽度 | 说明 |
|----|------|------|------|
| 选择框 | Checkbox | 40px | 批量操作 |
| Agent 名称 | 链接 | 160px | 点击跳转详情 |
| 描述 | 文本 | 240px | 超长截断 + Tooltip |
| 模型 | 标签 | 100px | 显示 model_name |
| 绑定 KB | 标签组 | 160px | 显示前 2 个 KB 名称 |
| 状态 | Switch | 60px | 直接切换启用/禁用 |
| 操作 | 按钮组 | 120px | 编辑/详情/删除 |

#### 3.4.2 新建/编辑 Agent Drawer

从右侧滑出的抽屉表单：

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| 名称 | String | 是 | 1-120字符 |
| 描述 | String | 否 | 最大 500 字符 |
| 系统提示词 | String | 是 | 默认 RAG_SYSTEM_PROMPT |
| 模型提供商 | String | 是 | 默认: openai-compatible |
| 模型名称 | String | 是 | 默认: 系统配置值 |
| 温度 | Float | 是 | 0-2，默认 0.7 |
| 绑定知识库 | Array[int] | 否 | 多选 |
| 绑定 MCP | Array[int] | 否 | 多选 |
| 绑定 Skill | Array[int] | 否 | 多选 |
| 启用 | Boolean | 是 | 默认 true |

**API**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /agents | 列表 |
| POST | /agents | 新建 |
| PATCH | /agents/:id | 编辑 |
| DELETE | /agents/:id | 删除 |
| POST | /chat | 发送消息 (含 RAG) |
| GET | /agents/:id/threads | 获取对话线程 |
| POST | /agents/:id/threads | 创建新线程 |

---

### 3.5 Agent 详情页 (/agents/:id)

**双栏布局**：
- 左栏：基本信息 + 绑定信息（可展开/收起）
- 右栏：对话测试面板

**对话测试面板功能**：
- 输入框支持多行输入，Shift+Enter 换行，Enter 发送
- 显示完整对话历史（当前线程）
- 支持创建新对话 / 切换已有对话
- Agent 回复支持 Markdown 渲染
- 显示检索来源（如果有 RAG 上下文）
- 流式输出（SSE）

---

### 3.6 知识库模块 (/knowledge-bases) ⭐ 核心

#### 3.6.1 知识库列表页

使用 ProCard 网格布局（3列），每张卡片显示：
- 知识库名称、文档数、文件夹数
- 启用状态
- 进入管理按钮

#### 3.6.2 知识库详情页

**整体布局**：
`
┌──────────────────────────────────────────────────────────┐
│  ← 返回  📚 产品文档                       [编辑] [⚙]   │
├──────────────┬───────────────────────────────────────────┤
│ 文件夹树     │  主内容区 (Tabs)                          │
│ ──────────  │  [📄 文档管理] [🔍 检索测试]              │
│ 📁 root     │  [📊 统计] [⚙ RAG 配置]                  │
│  📁 产品    │                                           │
│    📄 api.md│  ── 文档管理 Tab ──                       │
│  📁 技术    │  [+ 新建文件夹] [📤 上传文件]             │
│  ─────────  │  文档表格 (ProTable)                      │
│  [+] 新建   │                                           │
└──────────────┴───────────────────────────────────────────┘
`

#### 3.6.3 RAG 流水线详细设计

**文档处理流水线**：

`
用户上传文件
    │
    ▼
[文件类型检测]  .pdf / .docx / .txt / .md / .code
    │
    ▼
[文本提取]     pdfminer / pypdf / python-docx / 直接读
    │
    ▼
[文本清洗]     去除空行、特殊字符、控制符
    │
    ▼
[智能分块]     RecursiveCharacterTextSplitter
              按 chunk_size + chunk_overlap 切割
              保留段落结构
    │
    ▼
[向量化]       OpenAI Embeddings (1536 维)
    │
    ▼
[存储]         ChromaDB (向量 + 原始文本)
              SQLite (元数据: 文档ID, 文件夹, 页码)
`

**分块策略配置**（每个知识库独立）：

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| chunk_size | 500 | 100-4000 | 每块最大 token 数 |
| chunk_overlap | 50 | 0-500 | 相邻块重叠 token 数 |
| separators | [\n\n, \n, . , 空格] | - | 分块分隔符优先级 |
| min_chunk_size | 50 | - | 小于此值的块被丢弃 |

**RAG 检索流水线**：

`
用户提问: "如何部署这个系统?"
    │
    ▼
[① Query 预处理]    清理空白 / 语言检测 / 意图分类
    │
    ▼
[② Query 改写]      扩展同义词 / 补全省略 / 提取关键词
    │
    ▼
[③ 混合检索]
    ┌────────────┐  ┌────────────┐
    │ 向量检索    │  │ 关键词检索  │
    │ (语义相似)  │  │ (BM25)     │
    │ Top 20      │  │ Top 20     │
    └─────┬──────┘  └─────┬──────┘
          │               │
          └───────┬───────┘
                  ▼
         Reciprocal Rank Fusion (RRF 融合)
                  ▼
            Top 10 候选
    │
    ▼
[④ MMR 去重]       保证结果多样性，消除重复片段
    │
    ▼
[⑤ Cross-Encoder 重排]  精确相关性评分，保留 Top 5
    │
    ▼
[⑥ 上下文组装]       按相关度排序，截断到 4000 tokens
                    添加来源标注 [来源: 文件名, 92%]
    │
    ▼
[⑦ Prompt 注入]      系统提示 + 检索上下文 + 对话历史 → LLM
    │
    ▼
[⑧ 回答生成]         要求引用来源，不知道就说不知道
`

**RAG 配置项**（每个知识库独立 JSON 存储）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| hybrid_search | true | 是否启用混合检索 |
| rerank_enabled | true | 是否启用 Cross-Encoder 重排 |
| rerank_model | bge-reranker-base | 重排模型 |
| top_k | 20 | 初筛返回数量 |
| rerank_top_k | 10 | 重排后保留数量 |
| mmr_enabled | true | 是否启用 MMR 去重 |
| mmr_threshold | 0.5 | MMR 相似度阈值 |
| max_context_tokens | 4000 | 最大上下文 token 数 |
| min_relevance_score | 0.3 | 最低相关度阈值 |
| query_rewrite | true | 是否启用查询改写 |
| include_sources | true | 是否在回答中标注来源 |

**文件上传**：
- 支持拖拽 + 点击选择
- 支持多选（最多 10 个文件）
- 单文件最大 50MB
- 自动触发向量化处理
- 实时显示处理进度

**检索测试**：
- 输入问题，选择知识库
- 显示命中结果及相关度分数
- 可展开查看原始文本
- 用户反馈（有用/没用）
- 显示检索耗时和 token 消耗

#### 3.6.4 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /knowledge-bases | KB 列表 |
| POST | /knowledge-bases | 新建 KB |
| PATCH | /knowledge-bases/:id | 编辑 KB (含 RAG 配置) |
| DELETE | /knowledge-bases/:id | 删除 KB |
| POST | /knowledge-bases/:id/folders | 创建文件夹 |
| GET | /knowledge-bases/:id/folders/tree | 文件夹树 |
| POST | /knowledge-bases/:id/upload | 上传文件 |
| GET | /knowledge-bases/:id/documents | 文档列表 |
| DELETE | /knowledge-bases/:id/documents/:docId | 删除文档 |
| POST | /knowledge-bases/search | 检索 KB (RAG) |
| GET | /knowledge-bases/:id/stats | KB 统计 (RAG 质量) |

---

### 3.7 用户管理模块 (/users)

**用户列表**：ProTable 展示，支持搜索、角色筛选、状态筛选

**角色体系**：

| 角色 | 颜色 | 权限 |
|------|------|------|
| admin | 绿色 | 全部权限 |
| editor | 蓝色 | 管理 Agent/知识库，不能管理用户 |
| user | 黄色 | 只能使用 Agent 对话 |

**API**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /users | 用户列表 (仅 admin) |
| PATCH | /users/:id | 更新用户 (admin) |
| DELETE | /users/:id | 删除用户 (admin) |

---

### 3.8 MCP Server 管理 (/mcp-servers)

**列表展示**：名称 + 传输方式 (stdio/http) + 状态 + 操作

**新建表单**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 名称 | String | 是 | 服务器名称 |
| 传输方式 | Select | 是 | stdio / http |
| 命令 | String | 条件 | stdio 模式必填 |
| 参数 | String[] | 否 | 命令行参数 |
| 环境变量 | KV Map | 否 | 运行时环境变量 |
| URL | String | 条件 | http 模式必填 |
| 启用 | Boolean | 是 | 默认 true |

**API**：GET/POST/PATCH/DELETE /mcp-servers

---

### 3.9 Skill 管理 (/skills)

类似 MCP 管理，展示技能列表。

**字段**：名称、标题、描述、源类型(local/remote)、路径、启用

**API**：GET/POST/PATCH/DELETE /skills

---

### 3.10 系统设置 (/settings)

**Tab 结构**：
1. 全局配置：KV 表格，可增删改
2. 主题：选择预设主题
3. API 配置：OpenAI API Key/URL/Model

**API**：GET/POST/PATCH/DELETE /settings

---

## 4. 视觉设计规范

### 4.1 冰晶色主题系统

**主色调 (冰蓝)**：
- Primary: #00D4FF
- Primary-10: rgba(0,212,255,0.10)
- Primary-30: rgba(0,212,255,0.30)
- Primary-DK: #0099CC

**辅助色 (冰紫)**：
- Secondary: #7B68EE
- Secondary-10: rgba(123,104,238,0.10)

**强调色 (冰绿)**：
- Accent: #00FFD5
- Accent-10: rgba(0,255,213,0.10)

**背景色**：
- BG-Primary: #0A0E17
- BG-Secondary: #111827
- BG-Glass: rgba(255,255,255,0.03)

**文字色**：
- Text-Primary: #E8F4F8
- Text-Secondary: #8899AA
- Text-Muted: #556677

**状态色**：Success=#00FFD5, Warning=#FFB800, Error=#FF6B6B, Info=#00D4FF

### 4.2 3D 动效规范

| 效果 | 实现方式 | 参数 |
|------|---------|------|
| 卡片倾斜 | framer-motion 3D perspective | 最大 8° |
| 边框发光 | box-shadow + gradient border | rgba(0,212,255,0.3) |
| 玻璃拟态 | backdrop-filter: blur(20px) | rgba(255,255,255,0.03) |
| 粒子背景 | Canvas + requestAnimationFrame | ≤60 粒子, 冰蓝半透明 |
| 按钮上浮 | translateY(-2px) + shadow | 过渡 200ms |
| 入场动画 | fadeInUp | duration 400ms |

### 4.3 字体规范

| 场景 | 字体 | 大小 | 字重 |
|------|------|------|------|
| H1 标题 | Inter | 24px | 700 |
| H2 标题 | Inter | 20px | 600 |
| 正文 | Inter | 14px | 400 |
| 小号 | Inter | 12px | 400 |
| 代码 | JetBrains Mono | 13px | 400 |

### 4.4 间距规范

| 级别 | 值 | 使用场景 |
|------|-----|---------|
| xs | 4px | 图标间距 |
| sm | 8px | 内边距小元素 |
| md | 16px | 常规间距 |
| lg | 24px | 区块间距 |
| xl | 32px | 大区块间距 |

### 4.5 圆角规范

| 元素 | 圆角 |
|------|------|
| 卡片/面板 | 12px |
| 按钮 | 8px |
| 输入框 | 8px |
| 标签 | 6px |

---

## 5. 数据模型

### 5.1 核心实体关系

`
User (1) ────< (N) AgentConfig
User (1) ────< (N) KnowledgeBase
User (1) ────< (N) McpServer
User (1) ────< (N) Skill
User (1) ────< (N) Thread
AgentConfig (1) ────< (N) Thread
Thread (1) ────< (N) Message
KnowledgeBase (1) ────< (N) KBFolder
KBFolder (1) ────< (N) KBFolder (自引用)
KBFolder (1) ────< (N) KBDocument
KBDocument (1) ────< (N) KBChunk
AgentConfig (N) ────< (N) KnowledgeBase (多对多)
`

### 5.2 新增实体 (RAG 增强)

**KBFeedback** - 用户对检索结果的反馈
- id, user_id, thread_id, chunk_id
- is_helpful (Boolean), comment (Text)
- created_at

**RetrievalLog** - 检索过程日志
- id, thread_id, query, rewritten_query
- kb_id, top_k, hit_count, avg_score, took_ms
- created_at

**KnowledgeBase.rag_config** (JSON 字段)
- 包含所有 RAG 配置项（见 3.6.3）

---

## 6. 非功能性需求

### 6.1 性能

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 首屏加载 | < 2s | 冷启动 |
| 页面切换 | < 300ms | 路由切换 |
| API 响应 | < 500ms | P95, 不含 LLM 调用 |
| 文件上传 | 支持 50MB | 分片上传 |
| 向量检索 | < 200ms | P95 |
| RAG 完整链路 | < 3s | 从提问到返回 |

### 6.2 安全性

| 项目 | 措施 |
|------|------|
| 认证 | JWT Bearer Token, 7天有效期 |
| 密码 | PBKDF2-SHA256 哈希 |
| 权限 | RBAC (admin/editor/user) |
| 文件上传 | 类型白名单 + 大小限制 + 路径校验 |
| CORS | 限制来源域 |
| SQL | ORM 防注入 |

### 6.3 兼容性

| 项目 | 支持 |
|------|------|
| 浏览器 | Chrome 120+, Edge 120+, Firefox 120+ |
| 分辨率 | 最小 1280x720, 推荐 1920x1080 |
| 移动端 | 不强制响应式 (管理后台) |

### 6.4 可观测性

| 项目 | 方案 |
|------|------|
| 前端错误 | Sentry (可选) |
| 后端日志 | Python logging + 结构化输出 |
| LLM Trace | LangSmith |
| 检索日志 | RetrievalLog 表 |
| 用户反馈 | KBFeedback 表 |

---

## 7. 开发计划

### Phase 1: 基础设施 + 主题系统 (1 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| 初始化 Vite + TS 项目 | web/package.json, vite.config.ts | 安装依赖 |
| 定义 CSS 变量 | web/src/styles/variables.css | 冰晶色主题 |
| 配置 Ant Design Token | web/src/App.tsx | ConfigProvider |
| 创建 IceCrystalCard 组件 | web/src/components/IceCrystalCard/ | 3D 悬浮卡片 |
| 创建 GlassButton 组件 | web/src/components/GlassButton/ | 玻璃拟态按钮 |
| 创建 ParticleBg 组件 | web/src/components/ParticleBg/ | Canvas 粒子背景 |
| 搭建 BasicLayout | web/src/layouts/BasicLayout.tsx | ProLayout 主布局 |
| 配置路由 | web/src/App.tsx | React Router |
| 创建 Zustand Store | web/src/stores/ | auth, theme, layout |
| 创建 API 请求封装 | web/src/services/request.ts | axios 拦截器 |

### Phase 2: 认证模块 (0.5 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| 登录页 | web/src/pages/Login/ | 表单 + 动画 |
| 注册页 | web/src/pages/Login/RegisterForm.tsx | 切换表单 |
| 认证守卫 | web/src/layouts/BasicLayout.tsx | 未登录跳转 |
| Token 管理 | web/src/stores/auth.ts | 持久化 |

### Phase 3: 仪表盘 (1 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| 统计卡片 | web/src/pages/Dashboard/StatCards.tsx | 4 列网格 |
| 趋势图 | web/src/pages/Dashboard/ActivityChart.tsx | ECharts |
| 快捷操作 | web/src/pages/Dashboard/QuickActions.tsx | 按钮组 |
| 最近活动 | web/src/pages/Dashboard/RecentActivity.tsx | 表格 |

### Phase 4: Agent 模块 (2 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| Agent 列表页 | web/src/pages/AgentList/index.tsx | ProTable |
| Agent Drawer | web/src/pages/AgentList/AgentDrawer.tsx | 新建/编辑 |
| Agent 详情页 | web/src/pages/AgentDetail/index.tsx | 双栏布局 |
| 对话测试 | web/src/pages/AgentDetail/TestChat.tsx | SSE 流式 |
| Markdown 渲染 | web/src/components/MessageRenderer.tsx | 复用已有 |
| Agent API 服务 | web/src/services/agent.ts | 全部 Agent 接口 |

### Phase 5: 知识库模块 (2 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| KB 列表页 | web/src/pages/KnowledgeBase/index.tsx | ProCard 网格 |
| KB 详情页 | web/src/pages/KnowledgeBase/KBDetail.tsx | Tab + 侧边树 |
| 文件夹树 | web/src/pages/KnowledgeBase/FolderTree.tsx | 递归组件 |
| 文档表格 | web/src/pages/KnowledgeBase/DocumentTable.tsx | ProTable |
| 文件上传 | web/src/pages/KnowledgeBase/FileUpload.tsx | 拖拽上传 |
| 向量化进度 | web/src/pages/KnowledgeBase/VectorStatus.tsx | 轮询更新 |
| 检索测试 | web/src/pages/KnowledgeBase/KBSearch.tsx | 检索 + 反馈 |
| KB API 服务 | web/src/services/knowledgeBase.ts | 全部 KB 接口 |

### Phase 6: RAG 后端增强 (1.5 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| 混合检索服务 | app/services.py | HybridRetriever |
| Reranker | app/services.py | Cross-Encoder 重排 |
| ContextBuilder | app/services.py | 上下文组装 |
| QueryRewriter | app/services.py | 查询改写 |
| RAG Prompt | app/services.py | RAG_SYSTEM_PROMPT |
| 检索日志 | app/models.py + services.py | RetrievalLog |
| 用户反馈 | app/models.py + services.py | KBFeedback |
| KB 配置扩展 | app/models.py | rag_config JSON 字段 |

### Phase 7: 用户管理 + MCP + Skill + 设置 (1.5 天)

| 任务 | 文件 | 说明 |
|------|------|------|
| 用户列表 + Drawer | web/src/pages/UserManagement/ | ProTable |
| MCP 管理 | web/src/pages/MCPManagement/ | 列表 + Drawer |
| Skill 管理 | web/src/pages/SkillManagement/ | 列表 + Drawer |
| 系统设置 | web/src/pages/Settings/ | KV 表格 |

### Phase 8: 打磨 + 联调 (1 天)

| 任务 | 说明 |
|------|------|
| 3D 动效统一 | 所有卡片/按钮动效一致性检查 |
| 响应式适配 | 最小宽度 1280px 验证 |
| 错误处理 | 全局错误边界 + Toast 提示 |
| 加载状态 | 骨架屏 + loading 态 |
| 端到端联调 | 全流程测试 |

**总计预估: 10.5 天**

---

## 8. 风险与约束

### 8.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Cross-Encoder 模型加载慢 | RAG 延迟高 | 首次加载缓存, 提供降级方案(关闭 rerank) |
| 大文件上传超时 | 用户体验差 | 分片上传 + 进度显示 |
| ChromaDB 数据量增大 | 检索变慢 | 定期清理 + 索引优化 |
| LLM API 不稳定 | 对话失败 | 重试机制 + 降级提示 |

### 8.2 约束条件

| 约束 | 说明 |
|------|------|
| 本地部署 | 不依赖外部云服务(除 LLM API) |
| SQLite 限制 | 并发写入有限, 生产环境建议 PG |
| 浏览器兼容 | 不支持 IE |
| 内存占用 | ChromaDB + 向量模型约 500MB |

---

## 9. 验收标准

### 9.1 功能验收

- [ ] 用户可以注册/登录/登出
- [ ] 仪表盘显示正确的统计数据
- [ ] 可以创建/编辑/删除 Agent
- [ ] 可以绑定知识库/MCP/Skill 到 Agent
- [ ] Agent 对话测试正常, 支持流式输出
- [ ] 可以创建/管理知识库
- [ ] 可以上传文件到知识库, 自动分块向量化
- [ ] 知识库检索返回相关结果
- [ ] 检索结果显示来源和分数
- [ ] 用户可以反馈检索结果(有用/没用)
- [ ] 可以管理用户(增删改查 + 角色)
- [ ] 可以管理 MCP Server
- [ ] 可以管理 Skill
- [ ] 可以修改系统设置

### 9.2 视觉验收

- [ ] 冰晶色主题一致应用
- [ ] 卡片悬浮 3D 动效正常
- [ ] 玻璃拟态效果正确
- [ ] 粒子背景流畅运行 (≥ 55fps)
- [ ] 按钮交互反馈完整 (hover/active/loading)

### 9.3 性能验收

- [ ] 首屏加载 < 2s
- [ ] RAG 检索 < 200ms
- [ ] 完整 RAG 链路 < 3s

---

*本文档结束。等待评审确认后进入开发阶段。*
