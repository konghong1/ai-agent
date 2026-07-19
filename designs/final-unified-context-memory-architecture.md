# 最终架构方案：统一上下文与长期记忆子系统（ADR-023）

> 融合三份输入：
> 1. 现状诊断：本项目 `app/agent.py::ask_agent` 全量加载会话历史、无超长处理。
> 2. ADR-021（会话内压缩）：预算感知 + 增量 LLM 摘要 + 滑动窗口降级。
> 3. ADR-022（跨会话记忆）：L0–L3 分层 + 关系表 + 每用户 Chroma 集合 + Promotion 闭环。
> 4. **gbrain（garrytan/gbrain）思路**：brain-first lookup、Retrieval Reflex、signal capture/write、auto-link 图谱、cron 富集、schema packs、gap analysis。
>
> 本文是这三者的**收敛版**，给出可直接落地的统一设计，并明确哪些 gbrain 机制我们**采纳 / 改编 / 暂不采纳**及理由。

---

## 0. 一句话定位

把「上下文窗口管理」从一个被忽略的细节，升级为系统的一等子系统：**ContextService**。它在一个统一预算下，装配三类内容——

```
[system + pinned] + [长期记忆召回：Retrieval Reflex 指针 + 语义回忆] + [会话内摘要] + [最近 K 轮原样] + [RAG 知识] + [当前轮]
```

记忆与压缩共享同一套预算、装配、降级逻辑；gbrain 的贡献是给「记忆召回」这一格补上了**确定性的、零 LLM 开销的指针层**，让上下文窗口始终精简。

---

## 1. gbrain 给了我们什么（采纳 / 改编 / 暂不采纳）

| gbrain 机制 | 我们的取舍 | 理由 |
|---|---|---|
| **Brain-first lookup**（任何外部调用前先查记忆） | ✅ 采纳，作为 `ContextService.build()` 第一步 | 最廉价、最快、最个性化的源，应优先于 RAG/工具调用 |
| **Retrieval Reflex**（确定性、零 LLM、precision-biased 扫描实体→注入紧凑指针 `name→slug→synopsis`） | ✅ 采纳为核心召回层 | 解决 ADR-022 原方案「向量召回易灌满上下文」的痛点；「指针不转储」纪律让窗口可控 |
| **Signal detector / write path**（每轮提取实体/事实/待办写回记忆） | 🟡 改编：拆为「显式优先 + 隐式候选队列」 | gbrain 全自动写入适合个人知识库；我们是多用户 Agent，需防污染 → 隐式提取默认关、需确认 |
| **Auto-link 图谱**（零 LLM 建实体边） | 🟡 改编为「实体归一（entity resolution）」 | 完整图谱对聊天 Agent 过重；但「把『Bob』解析到同一记忆页」避免记忆碎片化，值得做（轻量版） |
| **Cron-driven enrichment**（夜间去重/矛盾检测/显著性衰减） | ✅ 采纳，接入现有后台 worker | 复用 gallery worker 的「startup 启动、不联网」模式，零新基础设施 |
| **Schema packs**（typed memory：person/company/meeting/...） | ✅ 采纳 → 映射为 ADR-022 的 L0–L3 + 记忆类型枚举 | 类型化记忆更易查询、审批、展示 |
| **Hybrid search**（向量+BM25+RRF+重排） | 🟡 改编：v1 仅向量+关键词；RRF/重排为增强 | 我们已有 Chroma；BM25 可后续加。先跑通再优化 |
| **Gap analysis**（告诉模型「记忆库不知道 X」） | 🟡 采纳为可选小注入 | 提升诚实度，但需控制不污染；默认关 |
| **MCP 暴露 30+ 工具** | ⏸ 暂不采纳 | 当前是单体 FastAPI 服务，MCP 是后续「Agent 平台化」的事，见 §7 |
| **PGLite/Postgres 双引擎、markdown brain repo** | ❌ 不采纳 | 我们用 SQLAlchemy+Chroma，已有栈，不引入新存储范式 |

**关键改编点（必须记住）**：gbrain 是单人知识库，写入几乎无治理成本；我们是**多用户生产 Agent**，
所以「自动写入」必须加**透明 + 可驳回 + 总开关默认关**的护栏（与 ADR-022 一致），否则会污染他人上下文。

---

## 2. 最终架构（C4 上下文层）

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Chat API (/chat, /chat-stream)                │
│                                  │                                     │
│                                  ▼                                     │
│                    ┌──────────────────────────┐                       │
│                    │     ContextService        │  ← 统一预算 & 装配     │
│                    │  (app/context_service.py) │                       │
│                    └──────────────────────────┘                       │
│         build() 按以下顺序拼装（均在 model_ctx_budget 内）：             │
│                                                                       │
│   1) system + pinned            （常驻，不可压缩）                      │
│   2) memory recall:                                                        │
│        a. RetrievalReflex       （零 LLM：扫当前轮实体→指针）   ← gbrain │
│        b. semantic recall       （Chroma 向量召回 L2/L3 情景记忆）      │
│   3) session summary            （ADR-021 增量摘要）                    │
│   4) recent K turns (原样)       （含图片，最近窗口）                    │
│   5) RAG knowledge chunks       （已有 ContextBuilder，纳入同一预算）   │
│   6) current user turn                                                  │
└──────────────────────────────────────────────────────────────────────┘
        │                                          │
   写入路径（异步/后台）                      读取路径（每轮）
        ▼                                          ▲
┌──────────────────────┐              ┌──────────────────────────────┐
│ MemoryWriter          │              │ user_memories (SQL)          │
│ - 显式命令/UI         │──写──▶       │ + Chroma user_mem_{uid}       │
│ - 隐式候选队列(默认关) │              │ + Thread.summary (会话摘要)   │
└──────────────────────┘              └──────────────────────────────┘
        │
        ▼
┌──────────────────────┐
│ MemoryEnricher (cron) │  ← 复用 gallery worker 启动模式
│ - 去重 / 矛盾检测      │
│ - 显著性衰减           │
│ - 会话摘要 Promotion   │
└──────────────────────┘
```

---

## 3. 组件规格

### 3.1 Session Compaction（ADR-021，精炼）

- `ContextService` 持有 `model_ctx_budget = context_window − reserved_completion`（预留 ~25% 给回复）。
- 始终保留 `system + pinned` + 最近 K 轮原样。
- 超预算时，对窗口外旧轮做**增量 LLM 摘要**：仅折叠「上次 `last_compacted_msg_id` 之后、本次窗口之外」的轮次，append 到 `Thread.summary`；`Message` 原始行**永不删除**（清空 summary 即可恢复，完全可逆）。
- **降级**：压缩失败 → 滑动窗口丢弃最旧轮（仍保留 summary 若已有），绝不阻塞用户。
- **中文-aware 分词**：替换 `services.py:789` 的 `len//3.5`（对中文低估 ~5×）。v1 用 `tiktoken` 的 `cl100k_base` 近似；若无该包，用启发式 `max(len(c)//4 for cjk, len//3.5 for ascii)` 并按实测校准。

### 3.2 Long-term Memory Store（ADR-022，精炼 + gbrain schema packs）

**结构化记忆** → `user_memories` 表（SQLAlchemy），字段：

```python
class UserMemory(Base):
    __tablename__ = "user_memories"
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    layer         = Column(Integer)          # 0 身份 / 1 偏好 / 2 事实纠正 / 3 情景
    mem_type      = Column(String(32))        # preference | fact | correction | identity | entity
    key           = Column(String(128))       # 归一化实体键，如 "name: Bob"
    value         = Column(Text)              # 记忆内容；TEXT 禁默认值(MySQL硬约束)
    importance    = Column(Float, default=0.5)
    confidence    = Column(Float, default=1.0)
    status        = Column(String(16), default="active")  # active|archived|rejected
    source        = Column(String(16))        # explicit | extracted | promoted
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())
    last_accessed = Column(DateTime(timezone=True))
```

> MySQL 约束：所有 `Text` 列**不写 `DEFAULT ''`/`server_default`**，允许 NULL，应用层兜底（来自项目铁律）。

**情景记忆** → 复用 `app/vector_store.py::VectorStoreBackend`（Chroma），每用户集合 `user_mem_{uid}`，
embedding 复用 `services.py:121` 的 `get_embeddings()`（OpenAI `text-embedding-3-small`）。零新基础设施。

**写入双路径（显式优先）**：
- 显式：`记住：我喜欢中文回复` / UI 记忆管理面板 → 直接落库，**零幻觉，优先做**。
- 隐式提取：`MemoryWriter` 在会话末（或定时）用 LLM 从对话提取候选 → 进**待确认队列** → UI 透明展示、可驳回 → 确认后才入库。**总开关默认关**。

**当前指令永远覆盖记忆**：记忆是「默认偏好」不是牢笼；`correction` 类 `importance` 最高。

### 3.3 Retrieval Reflex（gbrain 核心，新增的召回层）

> gbrain 原话："Deterministic per-turn pointer layer ... zero-LLM, precision-biased scan resolves salient entities to existing brain pages and injects compact pointers (name → slug → safe synopsis). Detect + point, never auto-dump. Fail-open, capped."

我们的实现 `RetrievalReflex`（放在 `context_service.py` 内，零 LLM 调用）：

```python
def retrieval_reflex(user_text: str, user_id: int, cap: int = 6) -> list[Pointer]:
    # 1. 轻量实体抽取：v1 用正则/词典（人名、@handle、"我喜欢X"等偏好短语）；
    #    增强版可接一个小 LLM 抽取，但默认走零 LLM 以保低延迟与可控成本。
    entities = extract_entities_zero_llm(user_text)          # ["Bob", "我的语言偏好"]
    if not entities:
        return []
    pointers = []
    for ent in entities:
        page = resolve_memory_page(user_id, ent)             # 实体归一 → 单页
        if page:
            pointers.append(Pointer(
                name=page.key,
                slug=page.id,
                synopsis=truncate(page.value, 120)           # 紧凑摘要，非全文
            ))
        if len(pointers) >= cap:
        break
    return pointers   # fail-open：解析失败/超 cap 直接返回已得，绝不抛错阻断对话
```

注入格式（进 LLM 的紧凑指针，不转储全文）：

```
[记忆] Bob（人物）: 用户同事，负责后端；上次讨论了他写的支付服务。
[记忆] 语言偏好: 用户希望用简体中文回复。
```

**纪律**：只检测并指向，绝不把整个记忆页灌进上下文；有上限（cap）；仅对先前上下文做抑制（避免重复注入已在 recent K 里的信息）。

### 3.4 Signal Capture & Write Path（gbrain，改编）

- 每轮对话后，`MemoryWriter.enqueue(turn)` 把（用户开启隐式提取时的）候选记忆放进 `pending_memories` 队列表。
- 后台 worker 周期性或会话末触发「提取 → 去重 → 入待确认队列」。
- 用户在前端「记忆面板」看到候选，一键采纳/驳回。采纳 → 写 `user_memories` + 必要时 embed 进 Chroma。
- **实体归一（轻量 auto-link）**：写入前用 `resolve_memory_page` 把同名实体合并到同一 `key`，避免「Bob」「老鲍」「Bob 哥」裂成三条。

### 3.5 Background Enrichment Cron（gbrain cron，接入现有 worker）

复用 gallery worker 的启动范式（`server.py::startup` 启线程，startup 不联网）：

- **去重**：合并语义相近的 `user_memories` 行。
- **矛盾检测**：同一 `key` 出现新旧冲突值（如语言偏好从英文变中文）→ 保留新值，旧值 `status=archived` 并留 audit。
- **显著性衰减**：`importance` 随时间缓慢下降，长期未访问的低价值记忆自然沉底（不被召回）。
- **Promotion**：把 `Thread.summary`（工作记忆）在会话结束时提升为 L3 情景记忆，形成「工作 → 情景 → 长期」完整层次（ADR-022 闭环）。

---

## 4. 统一预算与装配（ContextService v2）

```python
class ContextService:
    def build(self, thread, user, current_turn) -> list[Message]:
        budget = self.model_ctx_budget(user.model)          # context_window - 预留
        parts = []
        parts += self.pinned(user)                           # system + 身份(L0)，不计压缩
        budget -= tok(pinned)

        # 记忆召回（gbrain: brain-first + reflex）
        reflex = self.retrieval_reflex(current_turn.text, user.id)   # 零 LLM
        recall = self.semantic_recall(thread, user, k=4)            # Chroma
        mem_block = render_memory(reflex, recall)
        budget -= tok(mem_block); parts += mem_block

        # 会话内压缩（ADR-021）
        summary, recent = self.compact(thread, budget)
        budget -= tok(summary); parts += summary
        budget -= tok(recent); parts += recent

        # RAG（已有 ContextBuilder，纳入同一预算）
        rag = self.context_builder.build(thread, budget)
        parts += rag

        parts += [current_turn]
        return parts
```

> 所有块的 token 估算走**中文-aware** 统一函数；任意块超支时按优先级（pinned > reflex/recall > summary > recent > rag）裁剪，绝不整体失败。

---

## 5. 与现有代码的对接点（不重写，只插入）

| 现有代码 | 改动 |
|---|---|
| `app/agent.py::ask_agent`（~264–348） | 把「全量 `select(Message)` 拼 prompt」替换为 `ContextService.build()` |
| `app/services.py::ContextBuilder.max_context_tokens`（775） | 保留，但预算改由 `ContextService` 统一下发 |
| `app/vector_store.py::VectorStoreBackend` | 新增 `get_user_memory_store(user_id)` 封装每用户集合 |
| `app/services.py::get_embeddings`（121） | 记忆 embedding 直接复用 |
| `app/models.py` | 新增 `UserMemory` / `PendingMemory` / `Thread.summary` 列 |
| `server.py::startup` | 启动 `MemoryEnricher` 守护线程（同 gallery worker 模式，不联网） |
| 前端 | 新增「记忆面板」（查看/编辑/驳回）+ 压缩提示「已压缩早期对话」|

**零新外部依赖**：Chroma 已用、SQLAlchemy 已用、embeddings 已用。gbrain 的 PGLite/Postgres/markdown repo 不引入。

---

## 6. 权衡矩阵

| 决策 | 得到 | 放弃 |
|---|---|---|
| Retrieval Reflex 零 LLM 指针层 | 低延迟、零成本、可控、fail-open | 漏掉未在词典/实体库里的隐含偏好 |
| 隐式提取默认关 + 需确认 | 防记忆污染、用户信任 | 自动化程度低于 gbrain 个人知识库 |
| 记忆永不硬删（软状态） | 可审计、可恢复、合规 | 存储缓慢增长（靠 cron 衰减/归档缓解） |
| 复用 Chroma 而非新图库 | 零新设施、快上线 | 无原生多跳图谱（auto-link 仅做实体归一） |
| 单体内部 ContextService 而非独立微服务 | 简单、易维护、无分布式一致性坑 | 记忆服务不能独立伸缩（当前用户规模不需要）|

---

## 7. 在更大架构里的位置（回应「整体架构」诉求）

`ContextService` 是「Agent 能力层」的一个 bounded context。更大系统的演化路径（沿用我们之前的框架）：

```
现在：模块化单体（FastAPI 内多个 context/service 模块，清晰边界）
  └─ 当用户/租户规模与团队扩大 → 抽离「记忆服务」「检索服务」为独立部署
       └─ 暴露 MCP/内部 API（对应 gbrain 的 MCP 30+ 工具思路，但那是后话）
```

**现在不要微服务**：小团队、边界尚在演化，模块化单体 + 清晰模块依赖方向（api → context_service → memory_store / vector_store）最稳。gbrain 的 MCP 化是「平台化」阶段的事，此刻不碰。

---

## 8. 分阶段落地（合并 ADR-021/022 + gbrain）

| 阶段 | 内容 | 可独立上线/回滚 |
|---|---|---|
| **P0** | 中文-aware tokenizer + `model.context_window` 字段 + `ContextService` 骨架（仅 pinned + recent K，无压缩） | ✅ 开关 `ENABLE_CONTEXT_SERVICE` 默认关 |
| **P1** | ADR-021 会话内增量压缩 + 滑动窗口降级 | ✅ 仅压缩开关 |
| **P2** | ADR-022 结构化记忆 `user_memories` + 显式记忆 API/UI（零幻觉路径） | ✅ 记忆开关 |
| **P3** | **gbrain Retrieval Reflex** 指针层接入 `ContextService.build` | ✅ reflex 开关 |
| **P4** | Chroma 情景记忆 `user_mem_{uid}` + 语义回忆 | ✅ recall 开关 |
| **P5** | 隐式提取候选队列 + 记忆面板驳回 | ✅ 默认关 |
| **P6** | `MemoryEnricher` cron（去重/矛盾/衰减/Promotion），接 startup worker | ✅ 后台开关 |
| **P7** | Gap analysis 可选注入 + RRF/重排增强 | ✅ 可选 |

每个开关独立，出问题即关对应层，不影响对话主链路。

---

## 9. ADR-023（决策记录）

```markdown
# ADR-023: 统一上下文与长期记忆子系统

## Status
Proposed

## Context
现状：ask_agent 全量加载会话历史、无超长处理；长会话会超窗失败。
已有两份设计：ADR-021（会话内压缩）、ADR-022（跨会话记忆）。
gbrain 提供了「brain-first + Retrieval Reflex 零 LLM 指针 + signal capture + cron 富集」的成熟范式。
需要一个统一子系统，而不是压缩与记忆各搞一套。

## Decision
设立 ContextService 作为一等上下文管理模块，在统一模型窗口预算下装配：
[pinned] + [记忆召回：Retrieval Reflex 指针 + Chroma 语义回忆] + [会话摘要] + [最近K轮] + [RAG] + [当前轮]。
记忆与压缩共享预算/装配/降级；记忆写入显式优先 + 隐式候选需确认（默认关）；
复用现有 Chroma + SQLAlchemy + embeddings，零新基础设施；
后台富集接入已有 worker 启动范式。

## Consequences
+ 长会话可优雅降级，不再超窗失败
+ 跨会话用户偏好/事实被结构化记住，且可控、可审计、可恢复
+ 每轮召回成本低（零 LLM reflex）、上下文窗口精简
- 增加模块复杂度（需开关灰度、预算核算）
- 隐式记忆需治理护栏，否则污染上下文
- 记忆存储随使用增长（靠 cron 衰减/归档缓解）
```

---

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 记忆污染（隐式提取幻觉） | 默认关 + 待确认 + 总开关；显式路径零幻觉优先 |
| 预算算错（中文低估） | 中文-aware 分词；实测校准；超支按优先级裁剪不整体失败 |
| Chroma 集合膨胀/维度不符 | 复用现有 `get_embeddings` 维度；`doctor` 类自检；按用户隔离 |
| 后台 worker 阻塞启动 | 同 gallery worker：startup 仅启线程、不联网 |
| 跨用户泄漏 | `user_id` FK + 每用户集合 + 检索 `where` 过滤 + 注入仅本用户；删用户级联清 |
| MySQL TEXT 默认值崩溃 | 所有 Text 列禁默认值，应用层兜底（项目铁律）|
```
