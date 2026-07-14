# 聊天视频"生成不出来" — 排查与修复

## 现象
聊天里只输入提示词、没选参考图，视频生成不出来（前端一直转圈 / 播放不出）。

## 排查（关键结论：与"有无参考图"无关）
1. **纯文本 t2v 本身没问题**：实测用 `agnes-video-v2.0` 提交无参考图的视频，Agnes 正常接受并返回 `task_id`，最终 `status=completed / progress=100`。缺图不是报错原因。
2. **历史视频消息都"完成"了但没有地址**：DB 里 2 条视频消息 `status=completed`、`reference_images=[]`，但 `blocks` 里**根本没有 `video_url` 字段** —— 任务成了，前端却拿不到可播放的地址。
3. **根因定位**：Agnes 视频完成后，真实播放地址藏在响应的 **`metadata.url`** 字段
   （`https://platform-outputs.agnes-ai.space/videos/agnes-video-v2.0/task_xxx.mp4`），
   而 `app/media.py` 的 `get_video_status` 只认顶层 `video_url / output / url / remixed_from_video_id`，
   **完全没读 `metadata.url`** → `video_url` 永远为空 → 前端 `MediaCard` 放不出视频。
4. 已排除的干扰项：nginx SSE 配置（正确）、前端 watch 逻辑（正确传参 + 解析 completed）、SSE 鉴权（`?token=` 兼容）、发送按钮 disabled 逻辑（不校验参考图）。

## 修复（`app/media.py` → `get_video_status`）
两处 URL 提取逻辑都补上 `metadata.url` 候选，并修正一处"把字段名当值"的笔误：
- 顶层归一化：候选改为字段**值** `[data.get("remixed_from_video_id"), data.get("output"), data.get("url"), metadata.get("url")]`
- 下载存储分支：`raw_url` 增加 `(data.get("metadata") or {}).get("url")`

效果：提取 `metadata.url`（Agnes CDN）→ 下载进 MinIO → `video_url` 变为内部代理
`/api/media/assets/by-key/videos/2/...mp4`，浏览器稳定播放（不受 CDN 过期/CORS 影响）。

## 验证
- `py_compile` 通过；容器内实测已完成任务 `video_url` 正确变为 MinIO 内部代理地址，`object_key` 非空。
- `docker restart ai-agent-api` 已生效（加载新代码）。
- 一次性回填脚本：DB 中 `status=completed` 但缺 `video_url` 的视频消息全部补回（MSG 12 / 14 均已 FIXED，旧 CDN 链接未过期、下载成功）。

## 你这边需要做的
- **新生成视频**（有无参考图均可）现在都会正确返回可播放地址。
- **历史已完成的视频消息**已回填 URL，刷新聊天即可播放。
- 无需改动前端，后端修复即时生效。
