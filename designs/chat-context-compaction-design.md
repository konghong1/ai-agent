# 聊天会话上下文传递机制分析与「超长上下文」处理方案

> 设计者：软件架构师（架构通）
> 日期：2026-07-17
> 范围：AI Agent 平台 · 聊天会话（同一个 Thread 内）的上下文管理与超长处理
> 参考：Claude Code 的上下文压缩（Auto-compaction）思路

---

## 1. 现状诊断（基于真实代码）

### 1.1 上下文是怎么传递的

入口：`app/agent.py` 的 `ask_agent()`，由 `app/api.py` 的 `/chat`（`api.py:669`）与 `/chat-stream`（`api.py:813`）调用。

每次用户发一条消息，流程是：

1. 取出/创建 Thread：`_get_or_create_thread()`（`agent.py:218`）。
2. 落库当前用户消息：`db.add(Message(thread_id=thread.id, role="user", content=message))`（`agent.py:265`）。
3. **一次性加载该 Thread 的全部历史消息**：
   ```python
   stored_messages = list(db.scalars(
       select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
   ))                                                # agent.py:326-328
   ```
   ⚠️ **没有任何 `.limit()`、没有分页、没有 token 计数、没有时间窗。**
4. 把 **每一条** user/assistant 消息原样塞进 `langchain_messages`，前面拼上 system prompt（`agent.py:329-348`）。
5. 如果绑定了知识库，再追加一段 RAG 检索上下文（作为另一条 user 消息，`agent.py:351-355`）。
6. 整段列表直接发给 LLM：`llm.invoke(lc_messages)`（`agent.py:386`）。
7. 把 assistant 回复落库（`agent.py:390-395`）。

存储结构（`app/models.py`）：
- `Thread`（71 行）：会话，含 `title`、`user_id`、`agent_id`。
- `Message`（83 行）：`role` + `content(Text)` + `extra(JSON)`，按 `created_at` 排序，复合索引 `ix_messages_thread_created`（98 行）。
- 历史消息**永久保留**，删除会话时级联删除（`api.py:321`）。

### 1.2 有没有对「上下文超长」的处理？

**结论：对「会话历史」完全没有处理。**

仓库里所有 `max_tokens` / 截断逻辑，经逐行核对，只作用于：

| 位置 | 作用对象 | 与会话历史的关系 |
|------|----------|------------------|
| `agent.py:303` / `services.py:775` `ContextBuilder.max_context_tokens` | **RAG 检索到的知识片段** | 仅限 KB 文本，不计入也不限制聊天历史 |
| `gallery_prompt_ai.py` 系列 | 电商套图「出图提示词」的输出长度 | 完全无关 |
| `chunking/` | 文档切分 | 完全无关 |

并且：
- **没有任何模型 `context_window` 配置**（全局 grep `context_window` 仅命中 RAG 的 `max_context_tokens`，无模型级窗口定义）。
- 没有滑动窗口、没有摘要、没有截断、没有「接近上限时压缩」的逻辑。

**后果（架构风险）**：
- 会话越长，每次请求的 prompt 越大 → 最终超过模型上下文窗口 → 上游返回 `context length exceeded` 类错误，或直接被上游静默截断（用户看不到、也不知道丢了历史）。
- 每次都全量加载+全量发送，**O(N) token 成本随会话线性增长**，长会话既慢又贵。
- 现有分词启发式 `len(content)//3.5`（`services.py:789`）是英文调参，**对中文严重低估约 5 倍**（中文 1 字≈1~2 token），因此即便以后加预算，中文场景的预算也会算错。

---

## 2. Claude Code 是怎么做的（参考）

Claude Code（以及 Anthropic 的会话压缩实践）的核心思想是 **Auto-compaction（自动压缩）**，不是简单砍掉旧消息，而是：

1. **始终保留**：系统提示（ pinned system prompt ）+ 最近若干轮（recent turns）原样。
2. **超出预算时压缩**：当「系统提示 + 历史 + 当前输入 + 预留回复空间」逼近模型窗口上限，触发一次压缩——用 LLM 把 **较旧的轮次** 总结成一段紧凑摘要。
3. **摘要作为前缀持久化**：压缩后的摘要被保存下来，下一轮直接复用，而不是每轮重新从头总结（增量式：只把「上次摘要之后、本次窗口之外」的新旧轮次折叠进已有摘要）。
4. **原始历史不丢**：被压缩的是「发给模型的上下文视图」，原始对话仍完整保留在存储里，可审计、可导出、可随时恢复。
5. **分层记忆**：`CLAUDE.md` 等持久化记忆作为「不需要每轮重新推导」的常驻上下文。

要点：**窗口管理 = 固定预算 + 最近窗口原样 + 旧内容摘要化 + 原始数据永删**，而非「保留最后 N 条」。

---

## 3. 设计方案（适配本项目技术栈）

### 3.1 设计目标与原则

- **数据零丢失**：压缩只改变「喂给 LLM 的视图」，绝不删除/改写 `Message` 原始行。可逆、可审计。
- **预算驱动，而非条数驱动**：用 token 预算判断是否压缩，比「保留最后 10 条」更稳，能自适应长短消息混合。
- **增量压缩**：只总结「新增的、落在窗口外的旧轮次」，成本与质量都更优。
- **中文友好**：分词必须 CJK-aware。
- **可降级、可灰度**：压缩失败不能阻塞用户；新旧逻辑可开关对比。
- **可扩展为独立模块**：把「会话记忆/上下文」作为独立 bounded context，未来多 Agent、多产品复用。

### 3.2 目标架构（上下文装配管线）

```
┌─────────────────────────────────────────────────────────────┐
│  DB: messages(thread_id)  —— 全部原始历史（永不被删）          │
└───────────────────────────┬─────────────────────────────────┘
                            │ 加载
                            ▼
                  ┌──────────────────────┐
                  │   ContextManager     │  ← 新增独立模块 app/context_manager.py
                  │  (预算感知装配)       │
                  └───┬──────────────┬───┘
          预算充足    │              │ 超预算
                      ▼              ▼
            保留最近 K 轮原样    ┌──────────────────────┐
            （含当前轮+图片）    │  Compactor(LLM)      │ 增量折叠旧轮次→摘要
                               └──────────┬───────────┘
                                          │ 写回
                                          ▼
                                  Thread.summary / last_compacted_msg_id
                                          │
                                          ▼
   组装顺序 → [system(pinned)] + [summary(如有)] + [recent K 轮] + [RAG 上下文] + [当前 user(含图)]
                                          │
                                          ▼
                                      LLM invoke
```

### 3.3 数据模型变更（增量、向后兼容）

`app/models.py` 的 `Thread` 增加两列（**可空、可空默认值**，遵循本项目「ALTER 加列必须可空」的硬约束）：

```python
class Thread(TimestampMixin, Base):
    # ... 现有字段 ...
    summary: Mapped[str | None] = mapped_column(Text, default=None)            # 压缩后的历史摘要
    last_compacted_msg_id: Mapped[int | None] = mapped_column(Integer, default=None)  # 已摘要到哪条
    compacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

- `summary` 是**派生产物**，不是真相源；清空即「恢复全量历史」。
- MySQL 迁移注意：TEXT 列**禁止带默认值**（`DEFAULT ''` 在 MySQL8 报 1101，见项目记忆），允许 NULL，应用层兜底。
- 模型级上下文窗口：在 `ProviderModel` 增加 `context_window: int | None`（默认按模型族映射，见 3.5）。

### 3.4 核心组件接口（草图，非最终实现）

```python
# app/context_manager.py
@dataclass
class ContextBudget:
    model_context_window: int       # 如 128_000
    reserve_for_response: int = 8_000   # 留给本次生成的空间
    @property
    def hard_cap(self) -> int:      # 历史+系统+RAG 可用上限
        return self.model_context_window - self.reserve_for_response

@dataclass
class ConversationView:
    system: str
    summary: str | None
    recent_turns: list[Message]
    rag_context: str | None
    current_query: str
    current_images: list

class ContextManager:
    def __init__(self, tokenizer, budget: ContextBudget, compactor: "Compactor"):
        ...
    def assemble(self, db, thread, new_user_msg, system_prompt,
                 rag_context, images) -> tuple[list, dict]:
        """
        返回 (langchain_messages, meta)
        meta 含: used_compaction: bool, estimated_tokens: int, dropped_turn_count: int
        """
        messages = load_all(thread)                       # 仍全量加载（索引已优化），仅装配时裁剪
        est = self._estimate(system_prompt, rag_context, new_user_msg, images)
        # 从最新往最旧贪心保留，直到再加一条会超 hard_cap
        recent, dropped = self._keep_recent_within_budget(messages, est)
        if dropped and self._needs_summary(dropped):
            summary = self.compactor.compact(dropped, thread.summary)  # 增量折叠
            self._persist_summary(thread, summary, dropped[0].id)
        return self._build_messages(system_prompt, thread.summary, recent,
                                    rag_context, new_user_msg, images), meta
```

```python
# app/compactor.py
class Compactor:
    def compact(self, dropped_turns: list[Message], prev_summary: str | None) -> str:
        """
        增量摘要：把 prev_summary + 本次被丢弃的轮次，折叠成一段新摘要。
        用「廉价/快速」模型调用（可复用同一 provider 的 lighter 模型）。
        失败必须抛可控异常，由 ContextManager 降级为「直接丢弃」而非阻塞。
        """
```

```python
# app/tokenizer.py  —— CJK-aware 近似分词
def estimate_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    non_cjk = len(text) - cjk
    return int(cjk * 1.6 + non_cjk / 4)   # 中文≈1.6 token/字，英文≈4 char/token
# 可选升级：tiktoken（cl100k）做更准的英文计数，中文仍走上式兜底
```

### 3.5 预算来源（模型上下文窗口）

- 在 `ProviderModel` 增加 `context_window` 字段；未配置时用「模型名→窗口」映射表（如 `agnes-2.0-flash`→128k、`agnes-image` 不适用等）兜底。
- `ask_agent` 里 `_resolve_llm_config` 解析出模型后，把窗口传给 `ContextBudget`。
- **RAG 的 `max_context_tokens` 必须纳入同一预算**：装配时先扣 RAG 额度，再扣历史，避免「RAG + 历史」叠加爆窗。

### 3.6 压缩触发与降级

- **触发**：`system + 当前输入 + RAG + 最近窗口` 的估算 token > `hard_cap * 0.85` 时，压缩最旧的轮次。
- **降级 1（摘要失败）**：Compactor 抛异常 → 降级为「直接丢弃最旧轮次」（滑动窗口），不阻塞用户，记日志。
- **降级 2（单条消息超大）**：若某条消息单独就超预算（如长文档粘贴）→ 对该条内容硬截断并加 `[内容过长已截断]` 标记（参考现有 `ContextBuilder` 的处理风格，`services.py:791`）。
- **降级 3（极端）**：即便 summary+最近 1 轮+当前输入仍超窗 → 返回明确错误（类比 413），提示用户开新会话，而不是默默丢信息。

### 3.7 UI 透明性（可选但建议）

在 `Message.extra` / 接口返回里加 `meta.used_compaction`（参考现有 `extra={"retrieval":...}` 写法，`agent.py:392`）。前端可显示「（已压缩早期对话）」标签——让用户知道上下文被摘要过，符合 Claude Code 的透明做法。

---

## 4. 方案选型与权衡

| 方案 | 做法 | 优点 | 代价/风险 | 建议 |
|------|------|------|-----------|------|
| **A. 滑动窗口** | 只保留最近 N 条，丢弃其余 | 零 LLM 成本、最简单 | 旧信息**静默丢失**，长程依赖断裂 | 仅作降级兜底 |
| **B. LLM 自动压缩（推荐）** | 超预算时摘要旧轮次，增量持久化 | 保留语义、长会话可用、成本可控（增量） | 每次压缩多一次 LLM 调用（延迟+少量成本）；需分词器；摘要可能失真 | **核心方案** |
| **C. 向量记忆召回** | 把历史 embedding，每轮检索相关旧片段 | 能「回忆」分散在很久以前的具体事实 | 每轮多一次向量检索+库依赖；召回可能漏 | B 之上**可选增强**（知识密集型 Agent） |
| **D. 分层/Map-Reduce 总结** | 多级递归摘要 | 极长文档友好 | 过度设计，当前不需要 | 暂缓 |

**推荐组合**：**B 作为必选核心 + A 作为压缩失败的降级 + C 作为知识型 Agent 的可选增强**。无论哪种，原始 `Message` 永不删。

---

## 5. ADR（架构决策记录）

```markdown
# ADR-021: 聊天会话超长上下文采用「预算感知 + LLM 增量压缩」

## Status
Proposed（待评审）

## Context
当前 ask_agent() 每次把整个 Thread 的全部 Message 原样发给 LLM（agent.py:326-348），
无 token 预算、无窗口、无压缩。会话变长后会超出模型上下文窗口，导致上游报错或静默截断，
且无优雅降级；同时现有分词启发式对中文低估约 5 倍。需要可扩展、可逆、中文友好的上下文管理。

## Decision
引入独立的 ContextManager 模块（app/context_manager.py）：
1) 以「模型上下文窗口 − 预留回复空间」为硬性预算；
2) 始终保留 system(pinned) + 最近 K 轮原样；
3) 超预算时对窗口外旧轮次做 LLM 增量摘要，持久化到 Thread.summary / last_compacted_msg_id；
4) 原始 Message 永不删除，压缩仅改变「发给 LLM 的视图」；
5) 中文-aware 分词；RAG max_context_tokens 纳入同一预算；
6) 压缩失败时降级为滑动窗口丢弃，绝不阻塞用户。

## Consequences
+ 长会话不再爆窗，可无限延续；token 成本从 O(N) 收敛。
+ 原始历史可审计、可恢复（摘要可清）。
+ 新增一次摘要 LLM 调用的延迟与少量成本（用增量折叠控制）。
- 引入新的持久化列与迁移（MySQL TEXT 禁默认值的坑需规避）。
- 摘要可能出现信息失真，需 UI 透明标注 + 必要时允许「展开原始历史」。
- 需为每模型维护 context_window（映射表/字段）。
```

---

## 6. 落地路线（可灰度、可逆）

- **Phase 0 — 基础**：新增 `app/tokenizer.py`（CJK-aware）；为 `ProviderModel` 增加 `context_window`（含迁移，TEXT/INT 可空）；建立「模型名→窗口」兜底映射。
- **Phase 1 — 模块**：实现 `ContextManager` + `Compactor`，**默认关闭**（feature flag `ENABLE_CONTEXT_COMPACTION=false`），`ask_agent` 通过开关在「原全量逻辑」与「新装配」间切换，便于 A/B 对比与即时回滚。
- **Phase 2 — 灰度开启**：开启开关；持久化 `Thread.summary`；接口返回 `used_compaction` 标记；前端展示「已压缩早期对话」。
- **Phase 3 — 可选增强**：知识密集型 Agent 叠加方案 C（向量记忆召回），与 B 并存。

**回滚**：关掉 flag 即回到原全量加载；清空 `Thread.summary` 即恢复全量历史视图。无任何破坏性迁移依赖。

---

## 7. 延伸到整体架构（呼应「大型系统长期规划」）

把「会话记忆 / 上下文管理」作为**独立 bounded context（模块）**，与 `agent`、`rag`、`media` 平级：
- 对外暴露清晰的接口（`assemble()` / `compact()`），未来多 Agent、多端（Web/API/CLI）复用同一套上下文策略；
- 上下文策略（窗口大小、是否启用向量记忆、用哪款摘要模型）作为**可配置策略**，按 Agent / 按用户维度可调；
- 为「长期记忆」预留扩展点：除会话内压缩外，未来可加跨会话的用户级持久记忆（类似 `CLAUDE.md` 的项目/用户常驻上下文），与该模块同一抽象。

> 一句话：**不要让每个 Agent 各自手写「怎么塞历史」，把上下文管理收敛成一个可配置、可观测、可替换的核心能力。**
