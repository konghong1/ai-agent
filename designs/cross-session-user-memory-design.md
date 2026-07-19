# 跨会话用户记忆（Cross-session User Memory）设计

> 设计者：软件架构师（架构通）
> 日期：2026-07-17
> 依赖：承接 `designs/chat-context-compaction-design.md`（会话内压缩 / ContextManager 管线）
> 范围：跨多个会话持久化的用户记忆，重点是**用户偏好（preferences）**，并扩展到事实 / 纠正 / 情景记忆

---

## 1. 定位：这是上一版管线的「另一块注入内容」

上一版把「会话内上下文」收敛为一个预算感知的 `ContextManager` 装配管线：

```
[system] + [session_summary] + [recent K 轮] + [RAG] + [current]
```

跨会话记忆**不是另起一套机制**，而是往同一个 `ContextManager` 里再塞两块受预算约束的内容：

```
[system] + [core memory] + [retrieved episodic] + [session_summary] + [recent K 轮] + [RAG] + [current]
```

好处：记忆与压缩**共享同一套预算、同一套装配、同一套降级**，不引入第二个上下文通道。这就是 Claude Code 的思路延伸——`CLAUDE.md`（常驻记忆）与 auto-compaction（会话内压缩）是同一上下文管理的两面。

---

## 2. 记忆分类法（Memory Taxonomy）

按「稳定性 / 注入方式 / 存储」分四层，越往上越稳定、越该常驻：

| 层级 | 类型 | 内容示例 | 存储 | 注入策略 |
|------|------|----------|------|----------|
| L0 核心/身份 | `identity` | user_id、显示名、语言(zh)、角色/领域 | 关系表 + 永驻 | **始终注入**（小、必带） |
| L1 偏好 | `preference` | 「用中文回答」「输出要 Markdown」「不要自动跨用户降级」 | 关系表 | 高重要度常驻；其余按需检索 |
| L2 事实/纠正 | `fact` / `correction` | 「项目用 MySQL」「用户说过 X 不要做」 | 关系表 | 按相关度检索；纠正类权重最高 |
| L3 情景记忆 | `episodic` | 「上次定了方案 B，因为…」「上周讨论过架构 Y」 | Chroma（每用户） | 每轮按当前 query 向量检索 top-K |

**关键原则**：记忆是「默认偏好」，不是「牢笼」。当前用户当轮指令永远覆盖记忆（见 §6 冲突处理）。

---

## 3. 存储模型（复用现有技术栈，零新依赖）

### 3.1 结构化记忆 → 关系表 `user_memories`

```python
class UserMemory(TimestampMixin, Base):
    __tablename__ = "user_memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))          # identity|preference|fact|correction
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=1)   # 1-3；3=核心常驻
    source: Mapped[str] = mapped_column(String(20), default="explicit")  # explicit|extracted|promotion
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(10), default="active")   # active|archived
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

- 迁移约束（本项目硬规则）：新增列**全部可空 / 可空默认值**；TEXT 列**禁带 `DEFAULT ''`**（MySQL8 报 1101，见项目记忆）；`importance`/`status` 用 INTEGER/VARCHAR 可带默认。
- 删除用户 → 级联删 `user_memories` 行 + 删其 Chroma 集合（隐私硬约束）。

### 3.2 情景记忆 → 复用 `VectorStoreBackend`（Chroma）

- 复用 `app/vector_store.py` 的 `VectorStoreBackend` 与 `services.get_embeddings()`，**不引入新向量库**。
- 每用户一个集合：`user_mem_{user_id}`（与 RAG 的 `kb_{id}` 平级，互不交叉）。
- upsert：`(memory_id, embedding, content, metadata={user_id, type, importance})`。
- 检索：`vs.query("user_mem_{uid}", query_embeddings=[q_emb], n_results=K, where={"user_id": uid})` —— `where` 是**额外保险**，即便集合名被误用也不会跨用户。
- 删除用户 → `vs.delete_collection("user_mem_{uid}")`。

---

## 4. 写入路径（两条，都必须可审计/可管理）

### 4.1 显式写入（Explicit）—— 优先做，风险最低
- 入口：UI「记忆管理」页 + 命令式 API（如 `/memory add "回答用中文"`），或一个轻量 `MemoryTool`（供 Agent 调用）。
- 特征：`source="explicit"`、`confidence=1.0`、`importance` 由用户/系统定。
- 不依赖 LLM 提取，**零幻觉风险**，最适合「用户偏好」这类高价值、低波动的事实。

### 4.2 隐式提取（Extraction）—— 会话末 LLM 提取，必须透明
- 触发：会话结束 / 周期性（参考压缩触发，不每轮跑）。
- 流程：把「本轮 transcript + 现有记忆」交给一个**廉价模型**调用，产出「建议新增/更新/作废」的记忆条目，**不直接落库**，而是：
  1. 与现有记忆做去重/合并（同 type + 语义相近 → 更新而非新增）；
  2. 低于 `confidence` 阈值的只进 L3 情景记忆，不进 L1/L2；
  3. 向用户**透明展示**「已为你记录：… 可在记忆管理页调整/删除」，**提供确认/驳回**。
- 风险与护栏：提取可能把玩笑当真 → 必须有「用户可审阅 + 可一键清除」；提供总开关「自动记忆」默认关，先做显式。

> 参考：Claude Code 的 `CLAUDE.md` = 本设计的 L0/L1 常驻层（用户/系统 authored，always-on）；Claude 消费级的「跨对话记忆」= 本设计的 L2/L3 提取层（观察→提取→透明→可管理）。两者合起来就是完整方案。

---

## 5. 读取与注入（并入 ContextManager 预算）

新增 `MemoryRetriever`，在 `ContextManager.assemble()` 内调用：

```
mem_core   = 取 user_memories WHERE user_id=? AND importance>=2 AND status='active'   # 常驻，小
mem_vec    = Chroma 检索 user_mem_{uid} top-K by 当前 query embedding                  # 情景，按需
# 全部计入 ContextBudget 的「记忆预算切片」（如预留 2k~4k tokens），不挤占对话
```

- 记忆预算切片独立于会话预算，但同属 `ContextBudget.hard_cap`；若记忆本身超限，先裁 L3 检索结果，再裁低 importance 的结构化项——**绝不为了塞记忆而砍掉最近对话轮次**。
- 注入位置：紧跟 system 之后（常驻记忆）→ 检索到的情景记忆作为一段 `user/context` 注入（与 RAG 上下文并列，标注 `<user_memory>` 便于模型区分）。

---

## 6. 冲突与失效处理

- **当前指令优先**：用户当轮说「这次用英文」→ 该轮用英文（即便记忆记 zh）；并可选「更新记忆」或「记一条例外」。记忆是默认值，不是硬约束。
- **纠正类权重最高**：`type=correction` 的记忆在检索与注入时加权，且若与后续提取冲突，保留纠正。
- **失效/陈旧**：每条记忆带 `updated_at` + `last_accessed`；提供「管理页」让用户编辑/归档/删除；长期未访问的低 importance 项可 LRU 归档（不删，仅退出常驻）。
- **防污染**：提取写入前与现有记忆去重合并；提供「清空我的记忆」一键重置。

---

## 7. 隐私与隔离（本项目铁律，必须多层兜底）

- 关系表：`user_memories.user_id` 硬 FK + 应用层校验「只能读写自己的记忆」。
- 向量库：每用户独立集合 `user_mem_{uid}` + 检索 `where={"user_id": uid}` 双保险。
- 注入：`ContextManager` 装配时只取「当前 `user_id`」的记忆，绝不混入他人。
- 清理：删除用户级联清关系表行 + 删 Chroma 集合。

---

## 8. 与上一版压缩设计的衔接：Promotion 管线

会话内压缩产生的 `Thread.summary`（工作记忆）可在会话结束时**提升（promote）为长期记忆**：

```
会话进行中 → 压缩出 Thread.summary（工作/情景）
会话结束   → Extraction Agent 读 summary + transcript
           → 产出 L1/L2/L3 记忆（source='promotion'）
           → 透明展示 / 入库
```

这就形成完整层次：**工作记忆（会话内压缩）→ 情景记忆（Chroma）→ 长期结构化记忆（关系表偏好/事实）**，全部经过同一道「提取 + 透明 + 可管理」闸门。

---

## 9. 落地路线（分阶段，每阶段可独立上线/回滚）

- **P-A（必做·低风险）**：`user_memories` 表 + 显式 `add/get/list/delete` API + UI「记忆管理」页 + L0/L1 **常驻注入**（并入 ContextManager 预算）。无 LLM 提取，零幻觉。
- **P-B（中风险·高价值）**：会话末 Extraction Agent（廉价模型）+ 去重合并 + 「已记录 X」透明提示 + 总开关（默认关）。
- **P-C（扩展）**：Chroma 每用户情景记忆 + 每轮向量检索注入（解决 L3 规模化）。
- **P-D（闭环）**：Promotion 管线（会话摘要 → 长期记忆），打通工作记忆与长期记忆。

回滚：P-A 关掉「记忆注入」开关即回到无记忆；P-B 关「自动记忆」总开关即停提取；清空 `user_memories` + 删集合即归零。全部可逆、无破坏性迁移依赖。

---

## 10. ADR

```markdown
# ADR-022: 引入跨会话用户记忆（偏好为核心）

## Status
Proposed（待评审）

## Context
会话内压缩方案（ADR-021）解决了「单会话超长」问题，但每次新会话都从零开始，
无法利用历史中稳定的用户偏好/事实。用户明确要求「跨会话记忆，特别是用户偏好」。
项目当前无任何用户记忆存储（已确认）；但已有可复用的 VectorStoreBackend(Chroma)
与 get_embeddings()，可零新依赖落地情景记忆。隐私隔离是本项目硬约束。

## Decision
新增独立 bounded context「User Memory」：
1) 结构化记忆（identity/preference/fact/correction）存关系表 user_memories，
   核心/高重要度项常驻注入；
2) 情景记忆复用 VectorStoreBackend，按用户建 user_mem_{uid} 集合，每轮向量检索注入；
3) 两条写入路径：显式（UI/命令，优先、零幻觉）+ 隐式提取（会话末 LLM，透明可驳回）；
4) 记忆经 MemoryRetriever 并入 ContextManager 的同一 ContextBudget（独立记忆预算切片）；
5) 当前用户指令永远覆盖记忆；纠正类权重最高；
6) 多层隐私隔离（FK + 每用户集合 + where + 注入仅取本用户）；
7) 会话摘要可经 Promotion 管线提升为长期记忆。

## Consequences
+ 新会话自带用户偏好/事实，体验连续；偏好类高价值记忆零幻觉（显式优先）。
+ 复用现有向量库与 embedding，无新基础设施；与压缩方案共享预算/装配/降级。
+ 全部可逆：开关/清空即归零；隐私多层兜底。
- 隐式提取有幻觉/污染风险（已用「透明+可驳回+总开关默认关+去重合并」护栏）。
- 每轮多一次向量检索 + 会话末多一次提取 LLM 调用的成本（已用批量/廉价模型/缓存控制）。
- 需维护 user_memories 表迁移与用户删除级联清理。
```

---

## 11. 风险与失败模式（架构视角）

| 风险 | 表现 | 缓解 |
|------|------|------|
| 记忆过拟合 | 模型因「记得太多」变僵硬、反复套用旧偏好 | 核心层保持小；情景层带阈值检索；提供「清空记忆」 |
| 陈旧记忆 | 用户已改偏好但记忆未更新 | `updated_at`+`last_accessed` LRU 归档；管理页可编辑；当前指令覆盖 |
| 提取污染 | 把玩笑/临时说法当真记成偏好 | confidence 阈值；去重合并；用户审阅+驳回；总开关默认关 |
| 跨用户泄漏 | 注入他人记忆 | FK + 每用户集合 + `where` + 注入仅取本用户（四层） |
| 成本 | 每轮检索 + 会话末提取 | 批量提取（非每轮）、廉价模型、embeddings 缓存、检索 K 上限 |
| 与压缩争预算 | 记忆挤掉最近对话 | 记忆独立预算切片，超限先裁记忆本身，不砍对话轮次 |
