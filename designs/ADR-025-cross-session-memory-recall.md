# ADR-025: 用户长期记忆跨会话召回（Always-on Profile 层）

## Status
Accepted

## Context（动机）

用户反馈：**同一用户跨会话聊天时，模型无法获取已存储的长期记忆（用户偏好/事实）作为参考**；而"聊天过程中能提取用户偏好并存进长期记忆"这一侧本身是工作的（`ENABLE_IMPLICIT_EXTRACTION=true`，候选入 `pending_memories`，用户确认后落入 `user_memories` 且 `status='active'`）。

经代码追踪，根因在**召回侧（read path）**，不在存储侧（write path）：

`ContextService.build()`（`app/context_service.py`）的"长期记忆"注入只有两条路径，且都**依赖当前轮消息文本**或**依赖未启用的基础设施**：

1. `_core_memory(user_id)` —— 仅加载 `layer == 0`（身份）的记忆。用户偏好默认 `layer == 1`，**永远不会被这一层加载**。
2. `_retrieval_reflex(user_id, current_text, ...)` —— 先用 `_extract_entities(current_text)` 从**当前消息**抽取实体；只有命中 `我喜欢 / 我的 / 记住： / @handle` 这类触发词，才去 `user_memories` 里 bigram 匹配。**新会话第一句若不含触发词（如"帮我写个前端组件"），返回空 → 不注入任何记忆。**
3. `_semantic_recall`（Chroma 语义回忆）—— 唯一能"脱离触发词、按语义跨会话召回"的路径，但生产环境 `ENABLE_MEMORY_RECALL` 被注释关闭（docker/.env 注明"未配 embedding 端点"），且其 `MemoryStore` 依赖 embedding，不可用时 fail-open 返回空。

结论：**系统没有"会话开始即无条件加载该用户已知偏好"的基线路径**。偏好存得进库，却几乎无法在新会话中被召回 —— 这正是"跨会话失忆"的现象。

### 生产环境相关开关现状（docker/.env）
- `ENABLE_CONTEXT_SERVICE=true` → `build()` 被调用
- `ENABLE_RETRIEVAL_REFLEX=true` → 触发器门控召回（有缺陷）
- `ENABLE_MEMORY_RECALL` → 注释关闭（无 embedding）
- `ENABLE_IMPLICIT_EXTRACTION=true` / `ENABLE_MEMORY_ENRICHER=true` → 写入与治理正常
- `ENABLE_GAP_ANALYSIS=true` → 召回为空时仅注入"无已知偏好"提示（不解决问题）

## Decision（决策）

采用 **两层级长期记忆召回（Two-tier Long-term Memory）**：

### Tier 1 — Always-on 用户画像注入（本次必做，零新基础设施）
在 `ContextService.build()` 中新增 `_user_profile_memory(user_id, max_tokens)`，与新会话消息内容**无关**，无条件加载该用户 `status='active'` 且 `layer >= 1`（偏好/事实/纠正）的记忆，按 `importance desc` 排序，token 上限截断，作为 system 记忆块注入。保证跨会话召回**始终生效**。

- 新增开关 `enable_user_profile_memory`（默认 `False`，遵循"改动默认关闭"铁律），`docker/.env` 置 `true` 启用。
- 预算感知：画像块上限取 `min(count_cap, token_cap)`，token_cap 建议 `int(window * 0.15)`，绝不挤占对话与回复预算。
- 容错：DB 异常 → 返回空串，绝不阻塞主链路（与现有 `_core_memory` 一致）。
- 多租户：已按 `user_id` 隔离，无跨用户泄漏风险。

### Tier 2 — 语义回忆（可选增强，需 embedding 可用时启用）
当部署配置了 embedding 端点后，开启 `ENABLE_MEMORY_RECALL` + `ENABLE_RRF`，让"未直接提及但与当前话题语义相关"的记忆也能被召回（模糊补充）。属增强项，不在本次强制范围。

## Consequences（后果）

### Tier 1 收益 / 代价
| 维度 | 获得 | 付出 |
|------|------|------|
| 跨会话召回 | 新会话任意首句都能带上用户偏好/事实 | 每轮多消耗 ~N tokens（受 cap 限制，通常 < 2K） |
| 可靠性 | 不依赖触发词 / embedding，确定性强 | 仅注入高 importance 的记忆，低权重记忆可能不出现 |
| 复杂度 | 仅新增一个无副作用的查询方法 | 需在 build() 预算计算中为画像预留空间 |

### Tier 2 收益 / 代价
| 维度 | 获得 | 付出 |
|------|------|------|
| 召回覆盖 | 语义相关、未显式提及的记忆也能召回 | 需 embedding 端点 + 向量库运维；embedding 不可用时降级为空 |

### 不做的选择（及原因）
- **只靠"修触发词正则"**：治标不治本，仍要求用户在新会话重复提及关键词，跨会话体验无本质改善。
- **直接把 `_core_memory` 改成加载全部 layer**：语义混淆（身份 vs 偏好），且缺少 token 预算控制，可能在大记忆量下挤占上下文。保留独立方法更清晰。

## 实现要点（供落地参考）
- 新增 `app/settings.py`：`enable_user_profile_memory: bool = Field(default=False, alias="ENABLE_USER_PROFILE_MEMORY")`、`user_profile_max_tokens`、`user_profile_count_cap`。
- `app/context_service.py`：
  - 新增 `_user_profile_memory(self, user_id, max_tokens)`：查 `user_memories`（`status='active'`, `layer>=1`, `mem_type in (preference,fact,correction)`）按 `importance desc` limit `count_cap`，逐条累加 token 至 `max_tokens` 截断，返回 `"用户长期偏好与事实（跨会话常驻）：\n- {key}: {value}"` 块；异常返回 `""`。
  - `build()` 中在 workspace memory 之后、`_core_memory` 之前（或紧随其后）注入画像块（受 `enable_user_profile_memory` 开关控制）。
  - 可选：命中后 `UPDATE user_memories SET last_accessed=now()`，供 enricher 做衰减（P6）。
- `docker/.env` + `docker-compose.yml`：`ENABLE_USER_PROFILE_MEMORY=true`（注意 compose `environment` 注入优先级 > 根 `.env`，需两端都补）。

## 验证
1. 单元/容器内：`cs._user_profile_memory(uid, cap)` 返回非空且含铁律/偏好类记忆；`build()` 输出含 `[system] 用户长期偏好与事实...`。
2. 真实 API 端到端：新会话首句不含任何触发词（如"帮我写个 Python 脚本"），模型回复能体现已存偏好（如"用 TypeScript"被尊重）。

### 实现与验证记录（2026-07-18，已落地）
- **改动文件**：`app/settings.py`（3 个开关/参数）、`app/context_service.py`（`_user_profile_memory()` + `build()` 注入点）、`docker/.env`（`ENABLE_USER_PROFILE_MEMORY=true`）、`docker-compose.yml` api `environment` 段（补注入，因 compose 注入优先级 > 根 `.env`）。
- **开关生效**：容器内 `os.environ['ENABLE_USER_PROFILE_MEMORY']='true'`、`settings.enable_user_profile_memory=True`。
- **逻辑验证**：`_user_profile_memory(1)` 返回 725 字符块（含 `语言偏好` 等真实偏好）；`build()` 以无触发词消息「帮我写一段 Python 代码」为 `current_text`，输出 `[1] system | ...用户长期偏好与事实...` 确认无条件注入。
- **真实端到端**：`POST /api/chat` 新线程（thread-dd042028be77），首句「我们平时交流，你一般该怎么跟我开场？」无任何触发词；模型回复「根据我们的长期记忆设定，我平时跟你交流时的固定开场白是：**"你好，小花生"**」——精确命中最独特的已存偏好 `开场白要求=你好，小花生`，并明确引用"长期记忆设定"。跨会话召回确认生效。
- **预算/容错**：token 上限 2000、条数上限 30、异常 fail-open 返回空串（与 `_core_memory` 一致），不挤占对话窗口、不阻塞主链路。
- **Tier2（语义回忆）**：未做，因生产无 embedding 端点（`ENABLE_MEMORY_RECALL` 仍关）。待配置 embedding 后可开启作模糊补充。
- **遗留噪声**：admin 记忆库含若干早期 MemoryPanel 测试产生的 `确定性验证键…` / `标记：Z…` 行（属 layer2 fact），非本次引入，未擅自删除（硬删须谨慎）。如需清理可单独处理。
