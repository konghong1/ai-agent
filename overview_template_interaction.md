# 模板保存与已保存模板交互改造说明

## 需求
1. 「另存为模板」改为弹窗：输入模板名称、选择模板封面，点击「保存模板」后才保存。
2. 已保存模板卡片点击即添加到出图规划列表。
3. 鼠标悬停已保存模板卡片时，显示「修改名称」和「删除」两个操作按钮。

## 改动文件

### 后端
- `app/gallery_service.py`
  - `save_template()` 增加 `cover_url` 参数，保存到 `payload.cover_url`。
  - 新增 `update_template()`：支持修改模板名称与封面。
  - 删除 `delete_image()` 中已删除的「重标首张为原图」逻辑（此前改动残留，无影响）。
- `app/gallery_routes.py`
  - `create_template()` 接收顶层 `cover_url` 字段。
  - 新增 `PATCH /api/gallery/templates/{template_id}` 路由。
- `app/schemas.py`
  - `GalleryTemplateRead` 增加 `cover_url` 字段（从 payload 提取）。
  - 新增 `GalleryTemplateCreate.cover_url` 与 `GalleryTemplateUpdate`。

### 前端
- `web/src/services/gallery.ts`
  - `GalleryTemplate` 增加 `cover_url`。
  - `createTemplate()` 增加 `coverUrl` 参数。
  - 新增 `updateTemplate()`。
- `web/src/pages/EcommerceGallery/SaveTemplateModal.tsx`（新增）
  - 模板名称输入、产品图封面选择、取消/保存。
- `web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`
  - 「另存为模板」不再直接保存，改为调用 `onSaveAsTemplate` 打开弹窗。
  - `onSave` 移除 `asTemplate` 参数。
- `web/src/pages/EcommerceGallery/PlannerDrawer.tsx`
  - 模板卡片整体可点击，点击即 `onApplyTemplate`。
  - hover 显示编辑/删除两个图标按钮。
  - 删除增加二次确认。
  - 新增 `onRenameTemplate` prop。
- `web/src/pages/EcommerceGallery/index.tsx`
  - 接入 `SaveTemplateModal`。
  - 新增 `handleSaveAsTemplate`、`handleSaveTemplate`、`handleRenameTemplate`。
  - 模板保存从「保存整个项目」改为「保存当前单个类型」。
- `web/src/pages/EcommerceGallery/gallery.css`
  - 已保存模板卡片 hover 操作区动画。
  - 模板封面缩略图样式。
  - 另存为模板弹窗内样式。

## 验证
- `npm run build` 通过，无 TS/CSS 错误。
- 后端 `py_compile` 通过。
- `docker compose restart api` 后服务正常。

## 后续建议
- 当前封面存在 `payload.cover_url` 中，如需独立字段，可后续给 `gallery_templates` 表加 `cover_url` 列。
- 模板卡片 hover 操作在移动端不可见，可后续为移动端增加长按菜单或固定操作按钮。
