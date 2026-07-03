# 任务完成概述

## 任务一：视频加载状态优化

### 问题
聊天中选择视频模型生成视频时，视频一直显示"视频加载中"，但后端一直在刷（轮询）。

### 根因
SSE 端点 `watch_video_status` 的 `async def event_generator` 内直接调用同步 `requests.get()`（15s 超时），**阻塞整个 FastAPI 事件循环**。这导致：
1. SSE 事件无法推送到前端
2. 前端 EventSource 连接超时
3. 前端 `es.onerror` 关闭连接，且无重连机制
4. 视频永久卡在 "processing" 状态

### 修复方案

**后端 (`app/api.py`)**:
- 用 `asyncio.to_thread()` 包装 `MediaService.get_video_status`，避免阻塞事件循环
- 首次轮询立即执行（不再等待 2 秒）
- 增加 SSE 心跳（`: connected` 注释行）
- 修复 `remixed_from_video_id` 字段判断（仅当以 `http` 开头时才作为 URL）
- 轮询间隔从 2s 调整为 3s，最大轮询次数从 150 提升到 200（~10 分钟超时）
- 推送 `poll_count` 让前端显示实时进度

**前端 (`ChatInterface/index.tsx`)**:
- 添加指数退避重连机制（2s → 4s → 8s → 16s → 32s，最大 5 次）
- 处理 processing 状态更新（显示 "第 N 次状态检查"）
- 超时后自动标记为 failed
- 添加 `reconnectTimerRef` 管理重连定时器
- 重连前检查消息是否仍在 processing 状态

**前端 (`MediaCard/index.tsx`)**:
- `VideoBlock` 接口添加 `progress` 字段
- 处理状态显示进度信息

---

## 任务二：知识库全流程重构

### 发现的 8 个 Bug

| # | Bug | 影响 |
|---|-----|------|
| 1 | `or_` 未从 sqlalchemy 导入 | `_keyword_search` 运行时崩溃 |
| 2 | 关键词搜索遍历字符串字符而非词 | 搜索结果不正确 |
| 3 | `self.kb.rag_config` 不存在 | `HybridRetriever` 崩溃 |
| 4 | MMR 做 O(n²) embedding API 调用 | 检索极慢（20 个候选 = 400+ API 调用）|
| 5 | ContextBuilder/RAG_SYSTEM_PROMPT 编码乱码 | 中文显示为 mojibake |
| 6 | CrossEncoder 每次检索重新加载模型 | 检索延迟高 |
| 7 | folder_id 元数据类型不匹配 | 文件夹过滤失效 |
| 8 | ChromaDB 硬编码在所有方法中 | 无法切换向量数据库 |

### 修复方案

**新建 `app/vector_store.py` — 向量数据库抽象层**:
- 抽象接口 `VectorStoreBackend`：`upsert`、`query`、`delete`、`delete_collection`、`ensure_collection`
- 三种后端实现：
  - `ChromaBackend`（默认，本地持久化）
  - `FAISSBackend`（内存 + 文件持久化，适合小数据集）
  - `MilvusBackend`（远程，生产级）
- 通过环境变量 `VECTOR_STORE_BACKEND` 配置切换
- 单例模式，线程安全

**`app/settings.py` — 配置扩展**:
- `VECTOR_STORE_BACKEND` = `"chroma"` | `"faiss"` | `"milvus"`
- `VECTOR_STORE_PATH` = 向量数据库存储路径
- `MILVUS_HOST` / `MILVUS_PORT` = Milvus 连接配置

**`app/models.py` — 模型扩展**:
- `KnowledgeBase` 添加 `rag_config` JSON 字段（存储检索策略配置）

**`app/core/database.py` — 数据库迁移**:
- 添加 `_migrate_sqlite_columns()` 自动给已有表添加新列

**`app/services.py` — 全面修复**:
- 修复 `or_` 导入
- 关键词搜索用 `re.split` 正确分词
- `HybridRetriever` 使用 `self.rag_config`（从 `kb.rag_config` + `DEFAULT_RAG_CONFIG` 合并）
- MMR 优化为批量 embed（O(n) API 调用）+ NumPy 向量化相似度计算
- CrossEncoder 模型缓存（`_cross_encoder_cache`）
- 所有 ChromaDB 调用替换为 `get_vector_store()`
- ContextBuilder 和 RAG_SYSTEM_PROMPT 编码修复
- 元数据 `folder_id` 统一存储为字符串
- `process_document` 改为批量 upsert（性能提升）

### RAG 流水线
```
文档上传 → 文本提取(PDF/DOCX/TXT) → 分块(RecursiveCharacterTextSplitter)
→ 向量化(OpenAI Embeddings) → 存储(VectorStoreManager)
→ 检索(向量+关键词+RRF融合+MMR去重+CrossEncoder重排)
→ 上下文构建 → LLM 生成回答
```

---

## 测试验证

- ✅ 所有 Python 文件语法编译通过
- ✅ 向量存储 CRUD 操作测试通过（upsert/query/delete/delete_collection）
- ✅ 服务层导入测试通过
- ✅ RAG_SYSTEM_PROMPT 编码正确
- ✅ DEFAULT_RAG_CONFIG 配置完整
- ✅ 数据库迁移执行成功（rag_config 列已添加）
- ✅ FastAPI 应用初始化成功（68 条路由，2 条视频路由，14 条知识库路由）
- ✅ 前端 TypeScript 编译无新错误
