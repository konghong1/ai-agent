# 参考图生成 `do_request_failed` + 上传落盘 问题修复概览

## 结论速览
- **`do_request_failed` 真凶 = 参考图太大**：手机原图内联成 base64 后请求体过大，上游图像模型处理不过来 → 稳定失败/挂死。已在**唯一内联入口**加 Pillow 缩放根治。
- **「图没进 minio」是看错桶**：上传落在独立桶 `chat-uploads`（与生成图桶 `ai-agent-minio` 分离），图一直在，只是不在你盯着的那个桶。
- 上一轮你看到的**原始 JSON 错误**是旧代码未重载；现已清洗为可读文案 + request id。

## 修改点
1. **`app/storage/__init__.py`** — `inline_reference_image` 取回原图后先用 `_downscale_image_bytes()` 把长边压到 ≤1280px 并转 JPEG，再 base64。
   - 该入口被 chat LLM 路径 (`agent.py`) 与图片/视频生成路径 (`media.py`) 复用，一处修复全覆盖。
   - fail-safe：Pillow 缺失或解码失败则原样返回，绝不阻断内联。
   - 实测：4.7MB 手机原图 → 内联压到 **1MB**。
2. **`app/media_retry.py`** — `is_transient_response()` 把 `model_not_found`/`no available channel`（上游常返回 503）判为**永久错误、不重试**（原先被 5xx 短路误判瞬时，白等 ~16s）。
3. **`requirements.txt`** — 加 `Pillow>=10.0.0`（容器内已 `pip install`，重建镜像自动带）。

## 验证结果
- 缩放：4695KB → 1009KB（稳定复现）。
- 错误清洗：强制失败返回纯文本、不含 JSON 括号。
- `model_not_found`：1 次即返回（日志 `permanent error (HTTP 503)`），不再重试 3 次。
- 上传落盘：`chat-uploads` 桶对象含你 05:11:39 的真实上传图。
- `docker compose restart api worker` 已重载，`startup complete` 无报错。

## 诚实边界
若 AgnesAI 上游**自身拥堵**（实测某窗口 img2img 即便 1MB 图也 >150s 超时，但无参考图 45s 成功），属服务端瞬时问题，超出代码可控范围；`300s×3` 重试+退避已尽量兜住，且错误文案现已可读、带 request id，可直接拿去问 AgnesAI。

## 你这边怎么验证
直接重传那张参考图再生成一次即可。绝大多数情况下大图已被自动缩放、上游抖动被重试消化，不再报错。
