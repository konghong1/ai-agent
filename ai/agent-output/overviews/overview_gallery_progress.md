# 电商套图 · 生成时每张图片展示状态进度（方案A）

## 评估结论（先说能不能做）

图片生成进度分三层，可行性不同：

| 层级 | 可行性 | 说明 |
|---|---|---|
| 任务级进度（done/total + 百分比） | ✅ 已有 | 之前就存在 |
| **每张图状态进度**（排队中 → 生成中·第N张 → 完成 / 失败） | ✅ 本次实现 | 不依赖 AI 服务商，纯 worker + 前端 |
| 单张真实 0%-100% 去噪进度 / 实时模糊预览 | ⚠️ 做不到 | 商业文生图 API 不暴露中间态，除非换支持流式的模型 |

用户选择方案A：在每张图格子上显示**状态进度**，不依赖服务商真实进度。

## 后端改造（`app/gallery_service.py` · `run_gallery_task`）

改为两段式，让前端轮询时立刻看到所有格子的状态：

1. **阶段1 预建**：遍历 plan_items × count，先创建全部 `GalleryRecord(status="pending", prompt=已算好)` 并 commit。
   - 好处：前端一提交任务就能看到全部格子（不再用 `task.total - records.length` 推断缺图）。
   - 附带收益：`prompt` 在生成前就写入，所以「查看提示词」功能在**排队期就能点**。
2. **阶段2 处理**：逐张 `rec.status = "processing"` → 调 `_real_generate` →
   - 成功：写 `result_url` / `provider_*` → `status = "completed"`
   - 失败：写 `status = "failed"`（清空 `result_url`）→ 继续下一张
   - 每完成一张回写 `task.done / task.failed`

## 前端改造（`web/src/pages/EcommerceGallery/index.tsx` + `gallery.css`）

任务卡片网格按 `rec.status` 渲染四种状态：

- `pending` → 灰底「排队中」占位
- `processing` → 「生成中 · 第 N 张」+ 旋转 spinner + 整体脉冲动画
- `completed` + 真图 → `PreviewableImage`（可放大/下载）
- `failed` → 红框「生成失败」占位

`PromptBadge`（查看提示词）在有 `rec.prompt` 时即渲染，覆盖 pending/processing/completed，生成前即可预览将用到的提示词。保留 `task.total - records.length` 兜底骨架（防极端竞态）。

## 验证结果

| 项 | 结果 |
|---|---|
| 后端 py_compile | ✅ |
| 前端 tsc --noEmit | ✅ |
| 前端 vite build（4289 模块） | ✅ |
| 后端状态流转（隔离测试，临时 SQLite 已清理） | ✅ 3 张 record 全部 completed、prompt 预存且含平台词、降级 SVG 正确 |

**关键测试坑**：`generate()` 会 `enqueue_task`，常驻 worker 线程也会消费同一 task 并执行 `run_gallery_task`；若在测试里既 `generate()` 又手动 `run_gallery_task`，两者并发各预建一批 record，会出现数量翻倍/状态错乱。验证 worker 逻辑时必须**直接构造 `GalleryTask` 调 `run_gallery_task`，绕过 `generate()`**。

## 生效方式

改了后端 + 前端，重启 FastAPI 服务并浏览器 `Ctrl+F5` 即可看到效果。状态进度本身始终开启（非可配置项，与「查看提示词」开关相互独立）。
