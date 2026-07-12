# 创作结果任务卡片统一固定框展示

## 需求
用户反馈：创作结果页面中，一个任务里的多张生成图在卡片里展示得大小不一（有的看着大、有的看着小）。要求改成与「生成结果详情」弹窗一致的展示方式：在统一大小的框内，按图片自身比例居中展示。

## 修改内容

### 前端样式
文件：`web/src/pages/EcommerceGallery/gallery.css`

- `.task-grid` 由 `repeat(auto-fill, minmax(120px, 1fr))` 改为 `repeat(auto-fill, 160px)`，避免列宽被拉伸。
- `.task-cell` 固定为 `160px × 160px`（移动端 `120px × 120px`），不再随网格列宽变化。
- 图片统一使用 `max-width: 100%; max-height: 100%; object-fit: contain` 居中，不裁切、不拉伸。

## 验证结果

- `tsc --noEmit`：零错误
- `vite build`：成功（4289 模块）
- Playwright 驱动真实应用验证：
  - 任务卡片 `.task-cell` 宽度 = 160px，高度 = 160px，全部一致
  - 内部图片 `object-fit: contain`
  - 验证截图：`ai/agent-output/verify-task-fixed/task_cards_fixed.png`

## 用户操作

- 前端已构建到 `web/dist`，Docker web 容器挂载该目录。
- 请在浏览器中按 `Ctrl + F5` 硬刷新查看最新效果。
