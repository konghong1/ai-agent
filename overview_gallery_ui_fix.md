# 电商套图 UI 展示问题修复 — 概述

## 已修复问题

1. **创作结果「查看详情」/「一键做同款」弹窗：标题展示不全**
   - 原因：`.detail-title` 未处理超长无空格文本的换行；弹窗内容过高时，底部按钮/标题可能被视口裁切。
   - 修复：
     - 为 `.detail-title` 增加 `overflow-wrap: anywhere; word-break: break-word;`，保证任何标题完整换行。
     - 为 `.g-modal.detail-modal .ant-modal-body` 增加 `max-height: calc(100vh - 150px)` + `overflow-y: auto`，确保弹窗整体可滚动，不会裁切底部操作按钮。
     - 移除 `.detail-grid` 的 `max-height: 62vh` 内部滚动，避免双重滚动条。

2. **发布到创作案例后展示图片「超大」/ 不符合比例**
   - 原因：`.case-strip`、`.detail-img`、`.task-cell`、`.pf-pick` 中的图片使用 `width:100%; height:100%; object-fit:cover` 与父容器 `aspect-ratio` 形成高度依赖链；当生成图为竖版（3:4）且真实高度占优时，部分渲染下图片会按天然尺寸撑大单元格，导致溢出或比例失真。
   - 修复：将图片单元格的子图改为 `position: absolute; inset: 0;` 绝对填充，断绝内容与容器尺寸的循环依赖，确保单元格始终按 `aspect-ratio` 渲染，图片严格约束在单元格内并按比例裁切（cover）。

## 改动文件

- `web/src/pages/EcommerceGallery/gallery.css`

## 验证

- `vite build` 成功（4289 modules，0 error）。
- 使用 Playwright + 系统 Chrome 对真实运行环境进行截图验证：
  - 创作案例列表：竖版测试图被正确限制在 1:1 缩略格内，无溢出。
  - 创作案例详情：竖版测试图在 3:4 容器内正常展示，无变形。
  - 作品详情（独立 HTML 测试）：3:4 图片容器正常，超长中英文标题均自动换行、完整展示，底部按钮可见。
- 验证截图已保存至 `ai/agent-output/verify-ui/`。

## 用户操作项

- 前端已重新构建，Docker web 容器挂载的是 `web/dist`，刷新浏览器即可（Ctrl+F5）。
