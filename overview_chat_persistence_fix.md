# 聊天消息在切换会话 / Tab 时丢失 —— 根因与修复

## 现象
生成图片 / 视频时，切换 Tab 页或切换会话，当轮聊天（用户消息 + 生成结果）丢失。

## 根因（与之前怀疑的不同）
后端**本来就会落库**（`ask_agent` 写 user+assistant；`_handle_image_generation` / `_handle_video_generation` 也写），问题不在"没写"，而在 **"落库那一刻的数据库会话被客户端断开关掉了"**：

- 旧 `chat_stream` 的文本分支用 `temp_db = SessionLocal()`，`finally: temp_db.close()` 在生成器被取消时关闭它；图片/视频分支复用请求级会话（客户端断开时由 FastAPI 关闭）。
- 切换 Tab / 会话 → 前端 `AbortController.abort()` 断开 SSE → 生成器被取消 → 会话被**立即关闭**，而此时 `asyncio.to_thread` 里的生成函数还在 `db.commit()` → 提交被中断 / 会话已死 → **该轮消息写入失败**。
- 重载时 `fetchMessages` 查不到 → 表现为"聊天丢失"。

## 修复
把数据库会话的**生命周期从「HTTP 连接 / 生成器」解耦到「worker 线程」自身**：

1. 新增 `_run_text_chat(...)`：线程内 `SessionLocal()` → `ask_agent(db=...)` → `finally: db.close()`。
2. 新增 `_run_media_chat(media_kind, provider_id, model_name, payload, user_id)`：线程内 `SessionLocal()` → 按 id 重新加载 `Provider`/`User`/`ProviderModel`（避免跨会话传 ORM 对象）→ 调 `_handle_image/_video_generation(db=...)` → `finally: db.close()`。
3. `chat_stream` 文本 / 图片 / 视频三处改为 `await asyncio.to_thread(_run_text_chat / _run_media_chat, ...)`，删除原 `temp_db` 与 `finally: temp_db.close()`。
4. 前端无需改动：断开时不把 assistant 消息加进 React state，但后端已落库；重载即恢复（视频会自动重连 SSE watch）。

## 验证（决定性）
容器内确定性测试：stub 上游为瞬时假数据 → 建 thread → 跑 0.3s 即 `task.cancel()`（模拟 Tab 切换/客户端断开）→ 等 2s 让 worker 线程跑完自己的 commit → 查 DB：

```
persisted messages after disconnect: [('user', ..), ('assistant', blocks)]
VERDICT: PASS — worker-thread session commits independently of client disconnect
```

正面证明：**生成器被取消，worker 线程的会话仍独立把 user + assistant 两条消息提交入库**。

## 附：内存不足 & 轮询疑问
- **内存不足**：是 `uvicorn --reload` 的 watchfiles 文件监视器在容器里把整棵源码树 inotify 撑爆（`Cannot allocate memory`）。已去掉 `--reload` 并重建容器，运行时无文件监视器，内存稳定。
- **轮询损耗性能？** 视频状态用的是 **SSE（服务端推送，非轮询）**：仅对 `status==="processing"` 的视频建一条长连接；完成/失败即关闭；断线指数退避重连（最多 5 次）并清理 timer。无任何 `setInterval` 忙轮询；`fetchMessages` 只在切会话/手动刷新时各跑一次。开销可忽略。

## 涉及文件
- `app/api.py`：`_run_text_chat` / `_run_media_chat` + `chat_stream` 三处调用
- `docker/docker-compose.yml`：api `command` 去 `--reload`（顺带把 Pillow 烘焙进镜像）
