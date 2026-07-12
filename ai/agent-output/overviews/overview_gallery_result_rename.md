# 创作结果固定框展示 + 详情名称重命名

## 已完成

1. **创作结果图片**：任务卡片中的图片改为固定高度 `160px` 的舞台框，按自身比例 `contain` 居中展示，不再强制正方形裁切。
2. **详情弹窗**：每张生成图卡片只显示名称（如「首屏视觉图 #1」），移除了类型/模型等元信息。
3. **名称可重命名**：新增后端 `PATCH /api/gallery/records/{record_id}` 接口；前端详情弹窗内联编辑标题，实时更新。

## 修改文件

- **后端**
  - `app/schemas.py`：新增 `GalleryRecordUpdate`。
  - `app/gallery_service.py`：新增 `rename_record`。
  - `app/gallery_routes.py`：新增 `PATCH /api/gallery/records/{record_id}`。
- **前端**
  - `web/src/services/gallery.ts`：新增 `updateRecord`。
  - `web/src/pages/EcommerceGallery/index.tsx`：详情卡片移除 meta、新增内联重命名逻辑。
  - `web/src/pages/EcommerceGallery/gallery.css`：`.task-cell` 固定框 + 详情标题行样式。

## 验证

- `tsc --noEmit` 零错误；`vite build` 成功（4289 模块）。
- 后端语法检查通过，API 重启后真实 PATCH 调用成功。
- Playwright 驱动真实应用：
  - 任务卡片图片高度 = `160px`（固定框）。
  - 详情弹窗 `.detail-meta` 数量 = `0`，只显示名称。
  - 内联重命名成功，自动还原为原始名称「首屏视觉图 #1」。

## 截图与报告

- `ai/agent-output/verify-gallery-rename/detail_before_rename.png`
- `ai/agent-output/verify-gallery-rename/detail_after_rename.png`
- `ai/agent-output/verify-gallery-rename/task_cards.png`
- `ai/agent-output/verify-gallery-rename/report.json`

## 用户操作

- 后端已重启，浏览器需 **Ctrl+F5 硬刷新** 查看新效果。
