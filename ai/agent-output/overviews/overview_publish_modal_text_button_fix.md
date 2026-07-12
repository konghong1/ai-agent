# 发布到创作案例弹窗：文字与按钮截断修复

## 问题
用户反馈：发布弹窗图片排列已符合预期，但 label 文字（“选择要发布的成图…”）和底部按钮（“取消 / 发布到创作案例”）展示不全，被弹窗底部截断。

## 根因
发布弹窗没有限制整体高度，当内容较多时 Modal body 向下撑开，导致整个弹窗超出视口，footer 按钮被推出可视区域。

## 修改

### 前端 `web/src/pages/EcommerceGallery/index.tsx`
- 给发布 Modal 增加 `styles`：
  - `content.maxHeight: 85vh` 限制整个弹窗高度。
  - `body.maxHeight: calc(85vh - 132px)` + `overflow-y: auto`，让中间表单项可滚动，footer 始终固定可见。

### 前端 `web/src/pages/EcommerceGallery/gallery.css`
- `.publish-modal .ant-modal-content`：加 `max-height: 85vh; display: flex; flex-direction: column;`。
- `.publish-modal .ant-modal-body`：加 `flex: 1 1 auto; overflow-y: auto;`。

## 验证
- `tsc --noEmit`：零错误。
- `vite build`：成功。
- Playwright 驱动真实应用：
  - 在 1366×768 和 1440×900 两种视口下打开弹窗。
  - 弹窗 content 高度约 472px，footer 完整位于视口可见区域。
  - label 文字“选择要发布的成图（默认已勾选真实成图，示例占位图不可选）”完整可读。
  - 按钮“取消 / 发布到创作案例”完整显示。

## 操作
- 后端无需改动，无需重启。
- 浏览器按 `Ctrl + F5` 硬刷新即可看到新效果。
- 验证截图与报告：`ai/agent-output/verify-publish-modal-v2/`。
