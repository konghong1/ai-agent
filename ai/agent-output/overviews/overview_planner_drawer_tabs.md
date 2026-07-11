# AI 智能策划台新增「自定义子任务」与「已保存模板」Tab

## 需求
用户按参考图要求，在 AI 智能策划台抽屉里实现两个新 Tab 的页面样式：
1. **自定义子任务** —— 任务名称、需求描述、参考图片、模型/分辨率/比例/数量、确认添加任务。
2. **已保存模板** —— 模板卡片：标题、包含类型数、选用该任务按钮。

## 改动文件

### 后端
- `app/gallery_config.py`
  - `PLAN_TYPES` 新增 `{"id": "custom", "title": "自定义子任务", ...}`，让 `createPlanItem` 的 `type_id` 校验通过。

### 前端
- `web/src/pages/EcommerceGallery/PlannerDrawer.tsx`
  - 新增 `options` 与 `onCreateCustomTask` props。
  - 自定义子任务 tab：完整表单 + 本地上传预览 + 模型/分辨率/比例/数量 + 确认按钮。
  - 已保存模板 tab：新卡片样式。
  - 底部操作栏仅在「推荐类型」tab 显示。
- `web/src/pages/EcommerceGallery/index.tsx`
  - 实现 `createCustomTask`：上传参考图 → 创建 `type_id: 'custom'` 的 plan item。
  - 规划列表中 custom 项显示自定义名称，隐藏设置按钮。
  - 抽屉调用传入 `options` 与 `onCreateCustomTask`。
- `web/src/pages/EcommerceGallery/gallery.css`
  - 新增 `.custom-task-form`、`.ctf-*`、`.template-card`、`.template-use` 等样式。

## 验证
- `npm run build` 通过，CSS 90.39 kB，无 TypeScript 错误。
- Headless Chrome + CDP 截图：打开抽屉并切换三个 tab。
- 为展示模板卡片，临时创建示例模板「核心款全景展示」后截图。

## 截图
- `drawer_recommended.png` — 推荐类型 tab
- `drawer_custom_task.png` — 自定义子任务 tab
- `drawer_templates.png` — 已保存模板 tab
