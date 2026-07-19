# Task #72: 聊天流式输出 + 切页记录丢失修复 — 完成报告

## 用户诉求
1. 聊天时切换页面，聊天记录丢失
2. 聊天时需要流式输出，页面上实现字一个一个跳出来的感觉

## 修复内容

### 后端修复（2 个 bug）
1. **`app/agent.py` — `logger` 未定义致 NameError**
   - `ask_agent_stream_gen` 函数内调用 `logger.error(...)`，但模块从未定义 `logger` → 异常被 `NameError` 掩盖，流式接口直接返回 ERROR 事件
   - 修复：添加 `logger = logging.getLogger(__name__)`

2. **`app/db/__init__.py` — `IndentationError`（潜在部署炸弹）**
   - `wait_for_database` 的 try 块缩进错误，容器只靠旧 `.pyc` 缓存运行，一次干净重启就会硬挂
   - 修复：修正缩进，`ast.parse` 确认通过，删除旧 `.pyc`

### 前端实现（`ChatInterface/index.tsx`）
3. **打字机动画（字一个一个跳）**
   - 6 个模块级 ref 管理队列/已显示/最终文本/气泡 ID/线程 ID/定时器
   - `typewriterTick`：每 24ms 从队列取 `Math.max(1, ceil(q.length/28))` 字符追加到 assistant 气泡
   - SSE delta → 入队 → `ensureTypewriter` 启动 interval
   - SSE answer → 设 finalRef → 队列空则立即 finalize、否则自然播完

4. **切页记录持久化**
   - `useChatStore`（zustand 模块级）内存缓存 byThread
   - `fetchLatest` 从 DB 重载
   - `active-chat-thread` localStorage 持久化当前 thread
   - 组件 remount 时 hydrate（cache → DB）

### 关键发现
- **agnes-2.0-flash 流式行为**：将整个回答在一个 SSE delta 里一次性返回（非逐 token），首响应延迟 ~16s。因此后端 `llm.stream()` 不产出增量 token，**前端打字机动画是"字一个一个跳"效果的唯一来源**。

## 真机验证结果（Playwright）

### 1. 持久化测试 ✅ PASS
| 步骤 | 气泡数 | hasAgnes | activeThread |
|------|--------|----------|-------------|
| 初始加载 | 20 | true | thread-b69e2e66b8d6 |
| 切到仪表盘 | 0 | false | thread-b69e2e66b8d6（仍在 localStorage）|
| SPA 返回聊天 | 20 | true | ✅ 消息恢复 |
| 全页 reload | 20 | true | ✅ 消息恢复 |
| JS Errors | 0 | — | — |

### 2. 流式+打字机测试 ✅ PASS
发送"请写一段关于秋天的八十个字左右的短文"：
| 时间 | 气泡数 | 最后气泡长度 | 预览 |
|------|--------|-------------|------|
| t=0-10s | 22 | 0 | （等待 LLM 16s 延迟）|
| t=11.5s | 22 | 4 | 秋风送爽 |
| t=12s | 22 | 47 | 秋风送爽，天空变得格外高远湛蓝... |
| t=14s | 22 | 95 | 秋风送爽，天空变得格外高远湛蓝，云朵也显得轻盈洁白... |

**打字机增长检测：YES**（4 → 47 → 95 字符渐进增长）
**JS Errors：0**

### 3. 流式后切页持久化 ✅ PASS
流式发送后切 dashboard → 返回 chat → reload → bubbles > 0、lastLen = 95 持续存在。

## 结论
两个用户诉求均已修复并真机验证通过：
- ✅ **切换页面聊天记录不再丢失**（SPA 导航 + 全页 reload 均保持）
- ✅ **流式输出打字机效果**（字一个一个跳出来，4→47→95 字符渐进可见）
