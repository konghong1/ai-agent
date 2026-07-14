# 电商套图生成：实现链路 · 问题根因 · 架构优化

> 2026-07-14 由高级开发工程师（吴八哥）整理。回答用户三个核心问题：
> 1) 根据 AI 生成提示词生成图片，现在是怎么实现的？
> 2) 为什么会有 `Can't reconnect` / `GalleryPlanItem detached` 这两个问题？
> 3) 有没有从架构方面优化？

---

## 一、当前实现（AI 提示词 → 出图 的完整链路）

```
前端「立即生成」
   │  POST /api/gallery/tasks
   ▼
GalleryTask(status=pending) 入库
   │  gallery_worker 后台线程 _process(task_id)
   ▼
run_gallery_task(task_id)  ── 单个长生命周期 db 会话
   ├─ 读 task / project / user / plan_items（ORM 对象）
   ├─ 阶段1  AI 生成提示词
   │     _build_prompts_for_plan() ──▶ 调 agnes-2.0-flash 推理模型
   │     每个策划项生成：
   │        prompt_cn   前端展示版（中文）
   │        prompt_en   送图片模型版（英文·零中文，避免扩散模型渲染汉字乱码）
   │        prompt_input / prompt_raw   溯源留痕
   ├─ 阶段1.5 预建 GalleryRecord(pending)
   ├─ 阶段2  并发出图（ThreadPoolExecutor, max_workers=4）
   │     _generate_one(job):
   │        短会话解析图片模型(agnes-image-2.1-flash)
   │        ▶ 长 HTTP 真实出图（数分钟）
   │        ▶ 写回（spec 类型再调 overlay_spec 后端叠加尺码表）
   └─ 回写 task 状态(completed / partial / failed)

前端轮询 task 状态 → 实时展示进度与成图
```

一句话：**先调推理大模型把用户的策划意图翻成中英文提示词，再并发调图片大模型真实出图，spec 类额外后端叠加尺码表（纯视觉图+后端文字，规避汉字乱码）。**

---

## 二、为什么会有这两个问题

根因是同一类架构反模式：**长生命周期 ORM 会话跨长网络 I/O 持有 + ORM 对象跨会话边界传递**。

### 问题1：`Can't reconnect until invalid transaction is rolled back`
- 外层 `db` 会话从 `run_gallery_task` 开头一直开到结尾（≈数分钟）。
- 阶段2 出图是**几分钟的阻塞 HTTP 调用**，期间 `db` 会话空闲但连接被它死死按住。
- MySQL `wait_timeout` / 防火墙把这根空闲连接掐掉。
- 到回写 `db.commit()` 时，想用已失效的连接且事务尚未 rollback → SQLAlchemy 拒绝重连，抛此错。
- 旧 `except` 分支没有先 `rollback()`，连接无法自愈，异常冒泡成 `⚠ worker error`。

### 问题2：`GalleryPlanItem is not bound to a Session`（DetachedInstanceError）
- 为修问题1，把 `db.close()` 提前到出图前。
- 但 `db.close()` 之后，代码仍访问 `item.personal_settings`（`item` 是从外层会话取来的 `GalleryPlanItem` ORM 对象）。
- 会话一关，对象 `detached`；访问其未加载属性时 SQLAlchemy 试图回库刷新 → 对象已无会话 → 抛此错。
- 本质：**ORM 对象被跨会话边界传递/持有**。

> 一句话总结：两个错都是"把数据库会话当传家宝，跨几分钟的 HTTP 调用一直攥着"，区别只是失效后一个在 `commit` 上炸、一个在访问 detached 对象上炸。

---

## 三、架构优化方案

| # | 方案 | 状态 | 说明 |
|---|------|------|------|
| A | **DTO 化**：构建 plan 时把所有 ORM 对象序列化为纯标量 dict，plan 里**完全不含** ORM 对象 | ✅ 本次已做 | 即使以后有人在 close 后误加 `item.xxx`，也因根本没有 item 对象而立即报错，而非静默 detached |
| B | **每步独立会话**（`with Session() as db`）：读/写拆成短事务，绝不在长 I/O 期间持有会话 | ✅ 本次已做 | 外层 db 出图前 close，出图后用 `udb` 新会话回写 |
| C | **真正的异步任务队列解耦**（RQ / Celery / 自研）：web 只 `enqueue(task_id)` 立即返回，独立 worker 进程消费 | 🔲 建议 | 连接池/错误隔离/重试/水平扩展都干净，长 I/O 完全不影响 web |
| D | **出图调用异步化**：图片模型调用放进 `asyncio.to_thread` 或独立 job，DB 写入用独立会话 | 🔲 建议 | 彻底避免阻塞持有连接 |
| E | **连接池标准化**：所有 engine 统一 `pool_pre_ping=True` + `pool_recycle=1800` | ✅ 已做 | 消除失效连接 |
| F | **错误自愈规范**：`except` 必 rollback 再补救；会话用上下文管理器保证关闭 | ✅ 已做 | run_gallery_task / _generate_one 均落实 |
| G | **items_meta 也 DTO 化**：`_build_prompts_for_plan` 改为接收 DTO 而非 ORM 对象 | 🔲 建议 | items_meta 当前在 close 前用、暂时安全，但为彻底一致性建议后续改 |

### 推荐的根治路线（按性价比排序）
1. **先稳**：A+B+E+F 已在本次落地 —— 用「DTO + 短会话 + 连接池标准化 + 错误自愈」把当前架构内的坑填平，足以消除这两个报错。
2. **再解耦**：引入**任务队列（方案 C）**，把"生成"从 web 进程彻底拆出去。这是从架构上根治长 I/O 持有连接的根本手段，也让重试/并发/监控变简单。
3. **最后异步化**：出图 HTTP 调用改为 `asyncio.to_thread`（方案 D），DB 写入独立会话，web/worker 都不被阻塞。

---

## 四、本次修复记录（2026-07-14）

1. 前几轮：删除 `gallery_config.py` `SHOWCASE_SEED`、清理 `gallery_service.py` `write_showcase_svg`/`seed_showcases` 假数据。
2. 修复 `Can't reconnect`：外层 db 出图前 close、出图后开新会话 `udb` 回写；MySQL/PG engine 加 `pool_recycle=1800`。
3. 修复 `GalleryPlanItem detached`：把 `db.close()` 前移到 jobs 预取之前；本次进一步把 `plan.append` 里的 `item` ORM 对象改为纯标量（DTO 化），从根上消除跨边界。
4. 清理 task 38 的 DB 历史残留错误（13:26 旧代码炸的 4 条 orphan processing records + error 字段）。
5. 实弹验证：task 37 用修复+加固后代码跑通（部分成图），全程无 `Can't reconnect` / `GalleryPlanItem` 错误。

> 关键教训（写进团队规范）：**改完后端必须重启容器**，否则用户看到的仍是旧代码的报错；**迁移脚本必须连运行时同一个库**（用 app 的 engine，别用 `normalize_db_url()` 另建）。
