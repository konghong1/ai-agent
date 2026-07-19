# ADR-024: Workspace Memory Bridge（项目长期记忆跨会话注入聊天）

## Status
Accepted — 2026-07-18

## Context
聊天系统在装配上下文（`ContextService.build()`）时，只使用 `UserMemory` 数据库表 + Chroma 向量库作为长期记忆源。**项目级策展记忆 `.workbuddy/memory/MEMORY.md` 完全未被读取**——该文件由 AI 编码会话在开发过程中沉淀，包含技术栈、最高优先级铁律、架构硬坑、用户协作偏好等高价值信息。

后果：新会话（乃至每次聊天）对模型而言是"失忆"的通用助手。用户说"你好"，模型回"你好！有什么可以帮您的？"，完全无视项目背景。这与团队「用长期记忆做技术指导与质量把控」的诉求直接冲突。

两套记忆源现状对比：

| | 写入方 | 存储 | 运行时是否被读 |
|---|---|---|---|
| MEMORY.md | AI 编码会话（人工策展） | 文件 | **否（断点）** |
| UserMemory + Chroma | 聊天隐式提取 / Reflex / 语义回忆 | DB + 向量库 | 是（受开关控制） |

## Decision
在 `ContextService.build()` 中新增 **Workspace Memory Bridge**：读取 `.workbuddy/memory/MEMORY.md` 内容，作为记忆块的**首位**注入为额外 `system` 消息，跨所有会话常驻生效。

具体改动：
1. **`app/settings.py`**：新增配置项
   - `enable_workspace_memory`（默认 `False`，遵循铁律：所有改动默认关闭）
   - `workspace_memory_max_tokens`（默认 `6000`，token 预算上限）
   - `workspace_memory_path`（默认 `ROOT_DIR / ".workbuddy" / "memory" / "MEMORY.md"`）
2. **`app/context_service.py`**：
   - 新增 `_workspace_memory()`：读文件 → 估算 token → 超预算按字符比例截断（保留文件头部，因铁律/技术栈在开头）→ 失败静默返回 `""`，绝不阻塞聊天主链路。
   - 在 `build()` 步骤 2（记忆召回）首位调用并注入。
3. **配置启用**（三处必须一致，否则 Docker 部署读不到）：
   - 根 `.env`：`ENABLE_WORKSPACE_MEMORY=true`
   - `docker/.env`：`ENABLE_WORKSPACE_MEMORY=true`
   - `docker/docker-compose.yml` api `environment` 段：`ENABLE_WORKSPACE_MEMORY: ${ENABLE_WORKSPACE_MEMORY:-false}`
     - **关键坑**：compose `environment` 注入优先级高于根 `.env` 的 `load_dotenv`，新开关若不在此段显式声明，容器内永远读到默认值 `false`。

## Consequences
**变得更容易**：
- 聊天天然携带项目技术栈、铁律、架构约束、用户偏好——跨会话"失忆"问题消除。
- 等价于让"资深开发者的经验与铁律"在每次对话中持续发挥作用，支撑团队技术指导与代码质量把控。
- 只读不写，不与 `UserMemory` 表耦合，保持人工策展质量，无记忆污染风险。

**变得更难 / 代价**：
- 每轮对话多消耗约 4000–6000 tokens（占 128K 窗口 3%–5%，对当前模型可忽略；小窗口模型需关注预算）。
- 记忆文件膨胀时需人工维护 / 去重（已有维护规则）。
- 新增记忆系统开关时，开发者必须记得同步三处配置（根 .env / docker/.env / compose environment），否则静默不生效。

**验证**（2026-07-18，容器内执行）：
- 逻辑验证：`_workspace_memory()` 返回 6336 字符块（含"铁律""技术栈"）；`build()` 输出 `[1] system | 【项目长期记忆...】` 确认注入。
- 端到端真实 API：`POST /api/chat`「后端技术栈？」→ 模型准确答出 FastAPI / uvicorn:8010 / SQLAlchemy / SQLite+MySQL(`ai_agent`)，与 MEMORY.md 一致。

## 后续（可选）
- 若文件持续膨胀超预算，可考虑按章节语义切片 + 轻量向量召回，替代整文件注入。
- 可在 `preview_memory` 诊断端点补充 workspace 块预览，方便回归验证。
