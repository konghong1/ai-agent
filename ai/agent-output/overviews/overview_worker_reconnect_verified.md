# Worker 重连错误修复 · 自验证报告

> 报错：`⚠ worker error: Can't reconnect until invalid transaction is rolled back...`
> 验证时间：2026-07-14  |  验证人：吴八哥（高级开发工程师）

## 结论：已修复并实测通过 ✅

## 修复内容（前两轮已落地）

| 文件 | 改动 |
|------|------|
| `app/gallery_service.py` `_real_generate` | 模型解析改用**独立短生命周期会话**，不在几分钟的阻塞 HTTP 出图期间持有事务/连接 |
| `app/gallery_service.py` `_generate_one` | 发 HTTP 前 `s.rollback()`；**异常分支先 `s.rollback()` 再写失败状态**（核心自愈，第 1202/1249 行） |
| `app/core/database.py` | MySQL/PG 引擎加 `pool_recycle=1800` 回收空闲连接（第 29/31 行） |
| 部署 | `docker restart ai-agent-api ai-agent-worker`（此前漏重启，用户看到的仍是旧代码） |

## 三层自验证证据

**① 部署层** — 容器跑的是修过的代码
- `docker inspect`：api/worker 重启于 `2026-07-14T12:52:43Z`（改动之后），`Up` 健康
- 容器内 `grep` 确认源码含 `s.rollback()`、`pool_recycle=1800`

**② 逻辑层** — 在真实 MySQL 上复现 bug 并验证修复（`tests/verify_worker_reconnect.py`）
```
[OLD] 旧模式会触发原错误 : True
       报错信息匹配    : Can't reconnect until invalid transaction is rolled back.  Please rollback() fully before proceeding (Background on this error at: https://sqlalche.me/e/20/8s2b)
[NEW] 新模式(先 rollback)连接自愈: True
RESULT: PASS  修复有效，错误不再复现
```
旧模式精确复现了用户看到的那条报错（含完整链接），新模式（先 rollback 再复用连接）自愈成功。

**③ 回归层**
- `tests/test_gallery_prompt.py`：**27 passed**，无回归
- worker 实时日志中 `Can't reconnect` 计数 = **0**

## 给团队的质量要点（本次踩坑总结）
1. **改后端必须重启容器**才算生效，否则用户看到的还是旧代码 —— 这是前两轮「修了却还报错」的根本原因。
2. **验证要分两层**：部署层（容器里代码/重启时间）+ 逻辑层（写回归脚本把原 bug 复现出来，证明新逻辑能自愈）。只靠「代码看起来改了」不算验证。
3. **事务绝不能跨 I/O/网络调用持有**；`except` 里先 rollback 再补救写，是硬规则。
4. **长连接必配 `pool_pre_ping` + `pool_recycle`**，否则连接失效会随机炸在任意一次 `commit`。
