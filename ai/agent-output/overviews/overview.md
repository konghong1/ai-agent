# 电商套图 · 下载/重命名/时间/提示词优化

## 修复内容

1. **图片下载真正保存到本地**
   - 问题：点击下载只是放大预览，或浏览器因跨域忽略 `a.download`。
   - 解决：`PreviewableImage` 改为 `fetch(url) → blob → URL.createObjectURL → <a download>`；下载按钮加 loading 状态，避免重复点击。
   - 附加：后端 `_real_generate` 现在把 AI 返回的远程图下载到 `uploads/gallery/results/`，返回本地 `/api/gallery/files/...` URL，预览与下载均同源，不再受跨域限制。

2. **防止提示词被直接绘制到图片上**
   - 问题：生成的图片上出现文字/水印/LOGO。
   - 解决：`_build_prompt` 固定追加反文字指令：「画面中不要出现任何文字、水印、标语、LOGO 或直接把文案绘制到图片上；只根据上述描述生成场景与构图。」

3. **任务支持重命名**
   - 后端：`GalleryTask` 新增可空 `name` 列（`sync_model_columns` 自动迁移旧库）；新增 `PATCH /api/gallery/tasks/{id}`。
   - 前端：任务卡片标题区域点击即可行内编辑，回车/失焦保存，ESC 取消；同时提供铅笔图标按钮。

4. **任务卡片显示创建时间（精确到秒）**
   - 移除 `任务 #{id}` 标签，改为 `YYYY-MM-DD HH:mm:ss` 格式的时间戳。
   - 新增 `formatTaskTime` 工具函数统一格式化。

## 修改文件

- `app/models.py` — `GalleryTask.name` 字段
- `app/schemas.py` — `GalleryTaskRead.name`、`GalleryTaskUpdate`
- `app/gallery_service.py` — `rename_task`、`_save_generated_image`、`_real_generate` 下载持久化、`_build_prompt` 反文字指令、默认任务名
- `app/gallery_routes.py` — `PATCH /api/gallery/tasks/{task_id}`
- `web/src/services/gallery.ts` — `updateTask`、接口类型
- `web/src/pages/EcommerceGallery/index.tsx` — `PreviewableImage` 下载逻辑、任务重命名/时间展示
- `web/src/pages/EcommerceGallery/gallery.css` — 下载 loading、任务时间、重命名输入样式
- `tests/test_gallery_e2e.py` — 新增 task name / rename / prompt / polling 断言，同步 types 数量与 showcases 关闭 seed 的现状

## 验证结果

- `py_compile`：通过
- `tsc --noEmit`：通过
- `vite build`：通过
- `tests/test_gallery_e2e.py`：**24 项全部通过**

## 启动提示

修改后端后请重新启动 FastAPI 服务（入口为 `uvicorn app.server:app --port 8010`），并刷新浏览器（Ctrl+F5）使前端生效。
