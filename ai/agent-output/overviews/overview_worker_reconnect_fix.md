# 修复：图片生成失败（worker "Can't reconnect until invalid transaction is rolled back"）

## 现象
点击「立即生成」后，后台 worker 抛出
`⚠ worker error: Can't reconnect until invalid transaction is rolled back. Please rollback() fully before proceeding`
导致整批图片生成失败。

## 根因
`run_gallery_task → _generate_one` 在子线程打开会话 `s`：

1. 先 `s.get(rec)` / `s.get(user)` **开启事务**；
2. 调 `_real_generate(s, user, ...)`，内部 `_resolve_image_model(s, ...)` 又查库 → 事务**持续保持打开**；
3. 紧接着是**数分钟的阻塞 HTTP 出图调用**（`MediaService.generate_image` 超时 300s + 重试）。

若此连接在长 HTTP 期间被 MySQL `wait_timeout`、防火墙或瞬时 DBAPI 错误 `invalidate()`，
回到 `s.commit()` 即抛「事务未回滚、无法重连」。原 `except` 分支直接 `s.get`+`s.commit`
而不先 `s.rollback()`，无法自愈，异常经 `f.result()` 冒泡成 `⚠ worker error`。

## 改动
| 文件 | 改动 |
|------|------|
| `app/gallery_service.py` `_real_generate` | 签名 `(db, user, ...)` → `(user_id, ...)`；模型解析改用**独立短生命周期会话** `with Session(engine) as rs:`，解析后立即关闭，绝不跨长 HTTP 持有事务/连接 |
| `app/gallery_service.py` `_resolve_image_model` | 参数 `user: models.User` → `user_id: int`（仅用 `user.id`，无跨会话 lazy-load 风险） |
| `app/gallery_service.py` `_generate_one` | 读取 `rec`/`user` 后先 `s.rollback()` 再发起 HTTP；`except` 分支先 `s.rollback()` 再重连写失败状态（核心自愈） |
| `app/core/database.py` | MySQL / PostgreSQL 引擎加 `pool_recycle=1800`（Docker 部署回收空闲连接，源头减少失效连接） |

## 验证
- `py_compile` 两文件通过；`import app.gallery_service` / `import app.core.database` 通过。
- `tests/test_gallery_prompt.py`：**27 passed**。
- 唯一调用点 `_generate_one` 已同步新签名；`_resolve_image_model` 仅被 `_real_generate` 调用。

## 生效方式
Docker 栈：`docker restart ai-agent-api`（bind mount 免 rebuild）。
本地：重启 FastAPI 进程。

## 团队代码质量要点（资深开发视角）
1. **会话事务绝不能跨 I/O / 网络调用持有**——解析类查询用短会话，写结果时再开会话。
2. **`except` 里要先 `rollback` 再补救写**，不要把 `commit` 当 fallback；否则失效连接无法自愈。
3. **长连接（Docker / 云数据库）必配 `pool_pre_ping` + `pool_recycle`**，否则静默连接失效会随机炸在任意一次 commit 上。
4. 后台 worker 的事务边界要显式，不要依赖「函数返回就会自动关闭」的侥幸心理。
