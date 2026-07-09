# 出网代理宕机导致视频生成失败 — 根因复盘与修复

> 资深开发工程师（Senior Developer）技术复盘 · 2026-07-09

## 1. 问题现象

视频生成提交后一直"打不开"，后端日志每 ~3 秒刷一条：

```
ERROR app.media: Video status check failed: ... ProxyError('Unable to connect to proxy',
NewConnectionError("HTTPSConnection(host='host.docker.internal', port=33210):
Failed to establish a new connection: [Errno 111] Connection refused"))
```

## 2. 根因（团队要理解的本质）

不是视频生成逻辑有 bug，而是**"出网强依赖一个会挂的代理，且没有任何直连兜底"**这条架构脆弱点被触发了：

- `docker-compose.yml` 给 `api` / `worker` 注入了
  `HTTPS_PROXY=http://host.docker.internal:33210`（WorkBuddy 沙箱代理）。
- `requests` / `httpx` / `openai` SDK **默认读取这个环境变量**作为出网通道。
- 该代理是宿主机侧的"可选基础设施"，会随时拒绝连接（`Errno 111`）。
- 一旦代理挂掉：`get_video_status` 轮询、`generate_image/video` 提交、CDN 下载、甚至 **LLM 聊天**全部 `ProxyError` 硬失败；而且视频轮询是 3 秒一次，于是出现"刷屏式"报错。

**关键事实（已实测）**：本部署的宿主机**本身可以直接访问外网**
（`curl https://apihub.agnes-ai.com` → `401`，1.3s），代理 `33210` 当前是拒绝连接的。
所以"代理不可达时回退直连"是**真正能自愈**的修复，而非仅仅报错更优雅。

## 3. 修复方案：`app/http_client.py` 出网韧性层

两层防护，覆盖所有出网路径：

1. **启动探针 `ensure_proxy_strategy()`**（模块导入即执行，幂等）
   - 用 2s 超时探测配置的代理是否可达；
   - 不可达 → **清除本进程的 `HTTPS_PROXY`/`HTTP_PROXY`**，让 requests / httpx / openai 全部自动走直连；
   - api 与 worker 是两个独立进程，各自导入时各清各的，互不干扰。
2. **每次出网调用带直连兜底**
   - `request_with_fallback(method, url, ...)`：先走代理，遇 `ProxyError` 立即重试直连；
   - `download_bytes_with_fallback(url, ...)`：httpx(代理) → httpx(直连) → requests(直连)；
   - 还有 **30 秒"代理已宕"缓存**，避免 3 秒一次的轮询反复去撞死代理（顺带消除日志刷屏）。

## 4. 改动清单

| 文件 | 改动 |
|------|------|
| `app/http_client.py` | **新增**：代理探测 + 直连兜底的统一出网客户端 |
| `app/media_retry.py` | `post_with_retry` 的 `requests.post` → `request_with_fallback` |
| `app/media.py`（线上实际版本） | `get_video_status` 与 `_download_and_store` 接入兜底 |
| `app/media_new.py`（平行文件，同隐患） | 同上，保持一致 |
| `app/llm/openai_compat.py`、`app/llm/qwen.py` | `AsyncOpenAI(..., http_client=httpx.AsyncClient(proxy=None))` 强制直连，聊天也对代理宕机免疫 |
| `app/worker/media_worker.py` | 下载 `AsyncClient(proxy=None)` 强制直连 |

## 5. 验证结果

- 全部改动 `py_compile` 通过，所有模块 `import` 正常；
- 功能验证：故意把 `HTTPS_PROXY` 指向死地址 → 导入时探针自动清 env →
  `request_with_fallback` 直连 `apihub.agnes-ai.com` 返回 `401`（连接成功，
  此前必是 `ProxyError`）。**代理挂掉时视频轮询会自动走直连并成功。**

## 6. 运维与团队提质建议

- **应急**：若视频/图片又打不开，先看日志是不是 `ProxyError` 到 `33210`——
  现在代码会自动回退直连，正常情况下不应再出现；若仍失败，说明是真正的上游错误（非代理）。
- **开关**：设 `DISABLE_PROXY_AUTOFALLBACK=1` 可保留"强制走代理"
  （仅在"只能经代理出网"的部署环境才需要；这种环境要反过来保证代理高可用）。
- **设计原则（给团队）**：任何"外部依赖"都该当作**可选/会失败**来编码——
  出网代理、第三方 API、对象存储都应具备超时 + 退避 + 兜底通道，
  而不是把成功建立在某个单点永远在线上。这次的 `app/http_client.py`
  就是把这条原则落地成了可复用的基础设施，后续新增出网调用请统一走它。
